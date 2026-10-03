"""Discord OAuth authentication endpoints."""

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode
from uuid import uuid7

import msgspec
from litestar import get
from litestar.exceptions import HTTPException
from litestar.params import FromHeader, FromQuery, QueryParameter
from litestar.response import Redirect

from ... import http_client
from ...accounts import merge_users
from ...broadcast import broadcast_precomputed
from ...db import (
    delete_transient_token,
    get_auth_method_by_identifier,
    get_transient_token,
    get_user_by_email,
    get_user_by_uid,
    insert_auth_method,
    save_user,
    store_transient_token,
    update_auth_method,
)
from ...models import AuthMethod, AuthMethodType, User, is_active_account
from ...roles_hook import discord_api_base, push_role_metadata
from ._tokens import create_access_token, create_refresh_token, verify_token

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


@get("/discord/authorize")
async def discord_authorize(
    link: FromQuery[bool] = False,
    redirect: FromQuery[str | None] = None,
    token: FromQuery[str | None] = None,
    authorization: FromHeader[str | None] = None,
) -> Redirect:
    client_id, client_secret, redirect_uri, frontend_url = _get_discord_config()

    if not client_id:
        raise HTTPException(status_code=500, detail="Discord OAuth not configured")

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

    return Redirect(discord_auth_url, status_code=302)


@get("/discord/callback")
async def discord_callback(
    code: FromQuery[str],
    oauth_state: Annotated[str, QueryParameter(name="state")],
) -> Redirect:
    client_id, client_secret, redirect_uri, frontend_url = _get_discord_config()

    stored = await get_transient_token(f"discord:{oauth_state}")
    if not stored:
        return Redirect(f"{frontend_url}/login?error=invalid_state", status_code=302)

    await delete_transient_token(f"discord:{oauth_state}")

    link_mode = stored.get("link_mode", False)
    user_uid_from_state = stored.get("user_uid")

    session = http_client.session()
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
                return Redirect(
                    f"{frontend_url}/login?error=discord_token_failed",
                    status_code=302,
                )
            discord_tokens = await token_response.json()
    except Exception as e:
        logger.error(f"Discord token exchange error: {e}")
        return Redirect(f"{frontend_url}/login?error=discord_error", status_code=302)

    try:
        async with session.get(
            f"{discord_api_base()}/users/@me",
            headers={"Authorization": f"Bearer {discord_tokens['access_token']}"},
        ) as user_response:
            if user_response.status != 200:
                error_text = await user_response.text()
                logger.error(f"Discord user fetch failed: {error_text}")
                return Redirect(
                    f"{frontend_url}/login?error=discord_user_failed",
                    status_code=302,
                )
            discord_user = await user_response.json()
    except Exception as e:
        logger.error(f"Discord user fetch error: {e}")
        return Redirect(f"{frontend_url}/login?error=discord_error", status_code=302)

    discord_id = discord_user["id"]
    discord_username = discord_user.get("username", "")
    discord_global_name = discord_user.get("global_name")
    # Only use Discord email if verified.
    discord_email_verified = discord_user.get("verified", False)
    discord_email = discord_user.get("email") if discord_email_verified else None

    existing_auth = await get_auth_method_by_identifier("discord", discord_id)
    now = datetime.now(UTC)

    if link_mode and user_uid_from_state:
        user_uid = user_uid_from_state
        redirect_path = stored.get("redirect") or "/profile"
        if not is_active_account(await get_user_by_uid(user_uid)):
            return Redirect(
                f"{frontend_url}/login?error=account_deleted", status_code=302
            )
        outcome = "success"
        if existing_auth and existing_auth.user_uid == user_uid:
            outcome = "already"
        elif existing_auth:
            # merge_users refuses to absorb a VEKN-bearing account — re-linking
            # Discord must not swallow another account's VEKN identity.
            try:
                merge_result = await merge_users(user_uid, existing_auth.user_uid)
            except ValueError:
                merge_result = None
            if not merge_result:
                return Redirect(
                    f"{frontend_url}{redirect_path}?error=merge_failed",
                    status_code=302,
                )
            _merged, merge_bds = merge_result
            for bd in merge_bds:
                broadcast_precomputed(bd)
        else:
            await insert_auth_method(_new_discord_method(user_uid, discord_id, now))

        await _record_discord_sign_in(
            user_uid, discord_id, discord_username, discord_global_name, discord_email
        )
        await _store_and_push_discord_roles(user_uid, discord_id, discord_tokens)

        return Redirect(
            f"{frontend_url}{redirect_path}?discord_linked={outcome}",
            status_code=302,
        )

    if existing_auth:
        user_uid = existing_auth.user_uid
    else:
        user = await get_user_by_email(discord_email) if discord_email else None
        if not user:
            user = User(
                uid=str(uuid7()),
                modified=now,
                name=discord_username or "",
                contact_email=discord_email,
            )
            await save_user(user)
        user_uid = user.uid
        await insert_auth_method(_new_discord_method(user_uid, discord_id, now))

    # A tombstoned (IC-deleted) account keeps its Discord auth method — block a
    # fresh login from re-minting for it (a new signup has a live uid, passes).
    if not is_active_account(await get_user_by_uid(user_uid)):
        return Redirect(f"{frontend_url}/login?error=account_deleted", status_code=302)

    await _record_discord_sign_in(
        user_uid, discord_id, discord_username, discord_global_name, discord_email
    )
    await _store_and_push_discord_roles(user_uid, discord_id, discord_tokens)

    access_token, _ = create_access_token(user_uid)
    refresh_token = create_refresh_token(user_uid)

    token_params = {"token": access_token, "refresh": refresh_token}
    if stored.get("redirect"):
        token_params["redirect"] = stored["redirect"]
    params = urlencode(token_params)
    return Redirect(f"{frontend_url}/login?{params}", status_code=302)


def _new_discord_method(user_uid: str, discord_id: str, now: datetime) -> AuthMethod:
    return AuthMethod(
        uid=str(uuid7()),
        modified=now,
        user_uid=user_uid,
        method_type=AuthMethodType.DISCORD,
        identifier=discord_id,
        verified=True,
        created_at=now,
    )


async def _record_discord_sign_in(
    user_uid: str,
    discord_id: str,
    username: str,
    global_name: str | None,
    email: str | None,
) -> None:
    now = datetime.now(UTC)
    method = await get_auth_method_by_identifier("discord", discord_id)
    if method:
        await update_auth_method(
            msgspec.structs.replace(
                method, modified=now, last_used_at=now, email=email, username=username
            )
        )
    user = await get_user_by_uid(user_uid)
    if not user:
        return
    # Pinned: these are in the legacy merge's ARCHON_USER_FIELDS, which reverts
    # untracked values nightly.
    fields = {"discord_id": discord_id, "contact_discord": username or None}
    if not user.nickname and global_name:
        fields["nickname"] = global_name
    if all(getattr(user, k) == v for k, v in fields.items()):
        return
    updated = msgspec.structs.replace(
        user,
        modified=now,
        local_modifications=set(user.local_modifications) | fields.keys(),
        **fields,
    )
    broadcast_precomputed(await save_user(updated))


async def _store_and_push_discord_roles(
    user_uid: str, discord_id: str, discord_tokens: dict
) -> None:
    try:
        await store_transient_token(
            f"discord_rc:{user_uid}",
            {
                "access_token": discord_tokens["access_token"],
                "refresh_token": discord_tokens.get("refresh_token", ""),
                "discord_id": discord_id,
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


handlers = [discord_authorize, discord_callback]
