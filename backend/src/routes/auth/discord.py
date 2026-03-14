"""Discord OAuth authentication endpoints."""

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import aiohttp
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from uuid6 import uuid7

from ...db import (
    delete_transient_token,
    get_auth_method_by_identifier,
    get_transient_token,
    get_user_by_uid,
    insert_auth_method,
    insert_user,
    merge_users,
    store_transient_token,
    update_auth_method,
    update_user,
)
from ...models import AuthMethod, AuthMethodType, User
from ._tokens import create_access_token, create_refresh_token, verify_token

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_discord_config() -> tuple[str, str, str, str]:
    """Get Discord OAuth config lazily (after dotenv is loaded)."""
    return (
        os.getenv("DISCORD_CLIENTID", ""),
        os.getenv("DISCORD_SECRET", ""),
        os.getenv(
            "DISCORD_REDIRECT_URI", "http://localhost:8000/auth/discord/callback"
        ),
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
    )


@router.get("/discord/authorize")
async def discord_authorize(
    link: bool = Query(
        False, description="Set to true to link Discord to existing account"
    ),
    redirect: str = Query(
        "/profile", description="Frontend path to redirect after OAuth"
    ),
    token: str | None = Query(
        None,
        description="Access token for link mode (since headers can't be sent during redirect)",
    ),
    authorization: str | None = Header(default=None),
) -> RedirectResponse:
    """Initiate Discord OAuth flow.

    If link=true and user is authenticated, links Discord to their account.
    Otherwise, creates a new account or logs in with Discord.
    """
    client_id, client_secret, redirect_uri, frontend_url = _get_discord_config()

    if not client_id:
        raise HTTPException(status_code=500, detail="Discord OAuth not configured")

    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state with optional user_uid for linking
    state_data: dict = {
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        "link_mode": link,
        "redirect": redirect,
    }

    # If linking, verify user is authenticated (accept token from query param or header)
    if link:
        auth_token = token
        if not auth_token and authorization and authorization.startswith("Bearer "):
            auth_token = authorization[7:]

        if not auth_token:
            raise HTTPException(
                status_code=401,
                detail="Must be authenticated to link Discord account",
            )
        user_uid = verify_token(auth_token, expected_type="access")
        state_data["user_uid"] = user_uid

    expires_at = state_data.pop("expires_at", datetime.now(UTC) + timedelta(minutes=5))
    await store_transient_token(f"discord:{state}", state_data, expires_at)

    # Build Discord OAuth URL
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify email",
        "state": state,
    }
    discord_auth_url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"

    return RedirectResponse(url=discord_auth_url, status_code=302)


@router.get("/discord/callback")
async def discord_callback(
    code: str = Query(..., description="Authorization code from Discord"),
    state: str = Query(..., description="CSRF state token"),
) -> RedirectResponse:
    """Handle Discord OAuth callback.

    Exchanges code for tokens, fetches user info, and either:
    - Links Discord to existing account (if link mode)
    - Logs in existing user (if Discord ID found)
    - Creates new account (if Discord ID not found)
    """
    client_id, client_secret, redirect_uri, frontend_url = _get_discord_config()

    # Validate state
    stored = await get_transient_token(f"discord:{state}")
    if not stored:
        return RedirectResponse(
            url=f"{frontend_url}/login?error=invalid_state", status_code=302
        )

    # Clean up state (single use)
    await delete_transient_token(f"discord:{state}")

    link_mode = stored.get("link_mode", False)
    user_uid_from_state = stored.get("user_uid")
    redirect_path = stored.get("redirect", "/profile" if link_mode else "/")

    # Exchange code for Discord tokens
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            ) as token_response:
                if token_response.status != 200:
                    error_text = await token_response.text()
                    logger.error(f"Discord token exchange failed: {error_text}")
                    return RedirectResponse(
                        url=f"{frontend_url}/login?error=discord_token_failed",
                        status_code=302,
                    )
                discord_tokens = await token_response.json()
        except Exception as e:
            logger.error(f"Discord token exchange error: {e}")
            return RedirectResponse(
                url=f"{frontend_url}/login?error=discord_error", status_code=302
            )

        # Fetch Discord user info
        try:
            async with session.get(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {discord_tokens['access_token']}"},
            ) as user_response:
                if user_response.status != 200:
                    error_text = await user_response.text()
                    logger.error(f"Discord user fetch failed: {error_text}")
                    return RedirectResponse(
                        url=f"{frontend_url}/login?error=discord_user_failed",
                        status_code=302,
                    )
                discord_user = await user_response.json()
        except Exception as e:
            logger.error(f"Discord user fetch error: {e}")
            return RedirectResponse(
                url=f"{frontend_url}/login?error=discord_error", status_code=302
            )

    discord_id = discord_user["id"]
    discord_username = discord_user.get("username", "")
    discord_global_name = discord_user.get("global_name")  # Display name, may be None
    # Only use Discord email if verified
    discord_email_verified = discord_user.get("verified", False)
    discord_email = discord_user.get("email") if discord_email_verified else None

    # Check if Discord ID is already linked to an account
    existing_auth = await get_auth_method_by_identifier("discord", discord_id)

    if link_mode and user_uid_from_state:
        # === LINK MODE ===
        if existing_auth:
            if existing_auth.user_uid == user_uid_from_state:
                # Already linked to this user
                return RedirectResponse(
                    url=f"{frontend_url}{redirect_path}?discord_linked=already",
                    status_code=302,
                )
            else:
                # Discord is linked to another account - merge accounts
                # This reassigns all auth methods (including Discord) to keep_uid
                merged = await merge_users(user_uid_from_state, existing_auth.user_uid)
                if not merged:
                    return RedirectResponse(
                        url=f"{frontend_url}{redirect_path}?error=merge_failed",
                        status_code=302,
                    )
                # Auth method already reassigned by merge - don't create new one
        else:
            # No existing auth - create new auth method linking Discord to this user
            now = datetime.now(UTC)
            auth_method = AuthMethod(
                uid=str(uuid7()),
                modified=now,
                user_uid=user_uid_from_state,
                method_type=AuthMethodType.DISCORD,
                identifier=discord_id,
                credential_hash=None,
                verified=True,
                created_at=now,
                last_used_at=now,
            )
            await insert_auth_method(auth_method)

        # Update user's contact_discord and nickname from Discord
        user = await get_user_by_uid(user_uid_from_state)
        if user:
            changed = False
            if not user.contact_discord:
                user.contact_discord = discord_username
                changed = True
            if not user.nickname and discord_global_name:
                user.nickname = discord_global_name
                changed = True
            if changed:
                user.modified = datetime.now(UTC)
                await update_user(user)

        return RedirectResponse(
            url=f"{frontend_url}{redirect_path}?discord_linked=success",
            status_code=302,
        )

    else:
        # === LOGIN/SIGNUP MODE ===
        if existing_auth:
            # Login to existing account
            user_uid = existing_auth.user_uid

            # Update last_used_at
            now = datetime.now(UTC)
            updated_auth = AuthMethod(
                uid=existing_auth.uid,
                modified=now,
                user_uid=existing_auth.user_uid,
                method_type=existing_auth.method_type,
                identifier=existing_auth.identifier,
                credential_hash=existing_auth.credential_hash,
                verified=existing_auth.verified,
                created_at=existing_auth.created_at,
                last_used_at=now,
            )
            await update_auth_method(updated_auth)
        else:
            # Check if verified email matches an existing EMAIL auth user
            email_auth_user_uid = None
            if discord_email:
                email_auth = await get_auth_method_by_identifier(
                    "email", discord_email.lower()
                )
                if email_auth:
                    # Merge Discord into existing email user
                    email_auth_user_uid = email_auth.user_uid

            now = datetime.now(UTC)

            if email_auth_user_uid:
                # Add Discord auth to existing email user
                user_uid = email_auth_user_uid
                auth_method = AuthMethod(
                    uid=str(uuid7()),
                    modified=now,
                    user_uid=user_uid,
                    method_type=AuthMethodType.DISCORD,
                    identifier=discord_id,
                    credential_hash=None,
                    verified=True,
                    created_at=now,
                    last_used_at=now,
                )
                await insert_auth_method(auth_method)

                # Update user's contact_discord and nickname if not set
                user = await get_user_by_uid(user_uid)
                if user:
                    changed = False
                    if not user.contact_discord:
                        user.contact_discord = discord_username
                        changed = True
                    if not user.nickname and discord_global_name:
                        user.nickname = discord_global_name
                        changed = True
                    if changed:
                        user.modified = now
                        await update_user(user)
            else:
                # Create new account
                user = User(
                    uid=str(uuid7()),
                    modified=now,
                    name=discord_username or "",
                    nickname=discord_global_name,
                    contact_discord=discord_username,
                    contact_email=discord_email,
                )
                await insert_user(user)
                user_uid = user.uid

                # Create Discord auth method
                auth_method = AuthMethod(
                    uid=str(uuid7()),
                    modified=now,
                    user_uid=user_uid,
                    method_type=AuthMethodType.DISCORD,
                    identifier=discord_id,
                    credential_hash=None,
                    verified=True,
                    created_at=now,
                    last_used_at=now,
                )
                await insert_auth_method(auth_method)

        # Generate tokens
        access_token, _ = create_access_token(user_uid)
        refresh_token = create_refresh_token(user_uid)

        # Redirect to frontend with tokens
        params = urlencode({"token": access_token, "refresh": refresh_token})
        return RedirectResponse(
            url=f"{frontend_url}/login?{params}",
            status_code=302,
        )
