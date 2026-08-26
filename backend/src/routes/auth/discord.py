"""Discord OAuth authentication endpoints."""

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid7

import aiohttp
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import RedirectResponse

from ...accounts import merge_users
from ...broadcast import broadcast_precomputed
from ...db import (
    delete_transient_token,
    get_auth_method_by_identifier,
    get_transient_token,
    get_user_by_uid,
    insert_auth_method,
    save_user,
    store_transient_token,
    update_auth_method,
)
from ...models import AuthMethod, AuthMethodType, User
from ...roles_hook import discord_api_base
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
    redirect: str | None = Query(
        None,
        description="Frontend path to redirect after OAuth (same-origin path only)",
    ),
    token: str | None = Query(
        None,
        description="Access token for link mode (since headers can't be sent during redirect)",
    ),
    authorization: str | None = Header(default=None),
) -> RedirectResponse:
    client_id, client_secret, redirect_uri, frontend_url = _get_discord_config()

    if not client_id:
        raise HTTPException(status_code=500, detail="Discord OAuth not configured")

    # Same-origin paths only — a full URL or "//host" here would become an open
    # redirect via the callback (frontend successTarget() applies the same rule).
    if redirect and not (redirect.startswith("/") and not redirect.startswith("//")):
        redirect = None

    state = secrets.token_urlsafe(32)

    state_data: dict = {
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        "link_mode": link,
        "redirect": redirect,
    }

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

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify email role_connections.write",
        "state": state,
    }
    discord_auth_url = f"{discord_api_base()}/oauth2/authorize?{urlencode(params)}"

    return RedirectResponse(url=discord_auth_url, status_code=302)


@router.get("/discord/callback")
async def discord_callback(
    code: str = Query(..., description="Authorization code from Discord"),
    state: str = Query(..., description="CSRF state token"),
) -> RedirectResponse:
    client_id, client_secret, redirect_uri, frontend_url = _get_discord_config()

    stored = await get_transient_token(f"discord:{state}")
    if not stored:
        return RedirectResponse(
            url=f"{frontend_url}/login?error=invalid_state", status_code=302
        )

    await delete_transient_token(f"discord:{state}")

    link_mode = stored.get("link_mode", False)
    user_uid_from_state = stored.get("user_uid")
    redirect_path = stored.get("redirect") or ("/profile" if link_mode else "/")

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{discord_api_base()}/oauth2/token",
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

        try:
            async with session.get(
                f"{discord_api_base()}/users/@me",
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
    discord_global_name = discord_user.get("global_name")
    # Only use Discord email if verified.
    discord_email_verified = discord_user.get("verified", False)
    discord_email = discord_user.get("email") if discord_email_verified else None

    existing_auth = await get_auth_method_by_identifier("discord", discord_id)

    if link_mode and user_uid_from_state:
        if existing_auth:
            if existing_auth.user_uid == user_uid_from_state:
                return RedirectResponse(
                    url=f"{frontend_url}{redirect_path}?discord_linked=already",
                    status_code=302,
                )
            else:
                # merge_users refuses to absorb a VEKN-bearing account — re-linking
                # Discord must not swallow another account's VEKN identity.
                try:
                    merge_result = await merge_users(
                        user_uid_from_state, existing_auth.user_uid
                    )
                except ValueError:
                    merge_result = None
                if not merge_result:
                    return RedirectResponse(
                        url=f"{frontend_url}{redirect_path}?error=merge_failed",
                        status_code=302,
                    )
                # Push the merge to other clients' caches live; the
                # survivor's discord-field update broadcasts again below.
                _merged, merge_bds = merge_result
                for bd in merge_bds:
                    broadcast_precomputed(bd)
                # Auth method already reassigned by merge.
        else:
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

        # Pin in local_modifications: these fields are in the legacy merge's
        # ARCHON_USER_FIELDS, so untracked values get reverted by the nightly merge.
        user = await get_user_by_uid(user_uid_from_state)
        if user:
            changed = False
            local_mods = set(user.local_modifications)
            if user.discord_id != discord_id:
                user.discord_id = discord_id
                local_mods.add("discord_id")
                changed = True
            if not user.contact_discord:
                user.contact_discord = discord_username
                local_mods.add("contact_discord")
                changed = True
            if not user.nickname and discord_global_name:
                user.nickname = discord_global_name
                local_mods.add("nickname")
                changed = True
            if changed:
                user.local_modifications = local_mods
                user.modified = datetime.now(UTC)
                broadcast_precomputed(await save_user(user))

        await _store_and_push_discord_roles(user_uid_from_state, discord_tokens)

        return RedirectResponse(
            url=f"{frontend_url}{redirect_path}?discord_linked=success",
            status_code=302,
        )

    else:
        if existing_auth:
            user_uid = existing_auth.user_uid

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

            # Pin discord_id (in ARCHON_USER_FIELDS) so the nightly merge won't revert it.
            user = await get_user_by_uid(user_uid)
            if user and user.discord_id != discord_id:
                user.discord_id = discord_id
                user.local_modifications = set(user.local_modifications) | {
                    "discord_id"
                }
                user.modified = now
                await save_user(user)
        else:
            email_auth_user_uid = None
            if discord_email:
                email_auth = await get_auth_method_by_identifier(
                    "email", discord_email.lower()
                )
                if email_auth:
                    email_auth_user_uid = email_auth.user_uid

            now = datetime.now(UTC)

            if email_auth_user_uid:
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

                # Pin in local_modifications (fields in ARCHON_USER_FIELDS) so the
                # nightly merge won't revert them.
                user = await get_user_by_uid(user_uid)
                if user:
                    changed = False
                    local_mods = set(user.local_modifications)
                    if user.discord_id != discord_id:
                        user.discord_id = discord_id
                        local_mods.add("discord_id")
                        changed = True
                    if not user.contact_discord:
                        user.contact_discord = discord_username
                        local_mods.add("contact_discord")
                        changed = True
                    if not user.nickname and discord_global_name:
                        user.nickname = discord_global_name
                        local_mods.add("nickname")
                        changed = True
                    if changed:
                        user.local_modifications = local_mods
                        user.modified = now
                        await save_user(user)
            else:
                user = User(
                    uid=str(uuid7()),
                    modified=now,
                    name=discord_username or "",
                    nickname=discord_global_name,
                    discord_id=discord_id,
                    contact_discord=discord_username,
                    contact_email=discord_email,
                )
                await save_user(user)
                user_uid = user.uid

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

        await _store_and_push_discord_roles(user_uid, discord_tokens)

        # A tombstoned (IC-deleted) account keeps its Discord auth method — block a
        # fresh login from re-minting for it (a new signup has a live uid, passes).
        login_user = await get_user_by_uid(user_uid)
        if not login_user or login_user.deleted_at:
            return RedirectResponse(
                url=f"{frontend_url}/login?error=account_deleted", status_code=302
            )

        access_token, _ = create_access_token(user_uid)
        refresh_token = create_refresh_token(user_uid)

        token_params = {"token": access_token, "refresh": refresh_token}
        if stored.get("redirect"):
            token_params["redirect"] = stored["redirect"]
        params = urlencode(token_params)
        return RedirectResponse(
            url=f"{frontend_url}/login?{params}",
            status_code=302,
        )


async def _store_and_push_discord_roles(user_uid: str, discord_tokens: dict) -> None:
    try:
        from ...roles_hook import push_role_metadata

        await store_transient_token(
            f"discord_rc:{user_uid}",
            {
                "access_token": discord_tokens["access_token"],
                "refresh_token": discord_tokens.get("refresh_token", ""),
            },
            datetime.now(UTC) + timedelta(days=365),
        )

        user = await get_user_by_uid(user_uid)
        if user:
            await push_role_metadata(user, discord_tokens["access_token"])
    except Exception:
        logger.warning(
            f"Failed to push Discord Linked Roles for {user_uid}", exc_info=True
        )
