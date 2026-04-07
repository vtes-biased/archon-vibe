"""Discord Linked Roles integration.

Pushes user metadata to Discord so server admins can create
auto-assigned roles based on Archon organization/judge/playtest levels.
"""

import logging
import os

import aiohttp

from ..db import get_transient_token, store_transient_token, delete_transient_token
from ..models import Role

logger = logging.getLogger(__name__)

# Discord metadata field definitions (max 5, we use 3)
METADATA = [
    {
        "key": "organization",
        "name": "VEKN Role",
        "description": "VEKN organization level (1: Member, 2: Prince, 3: National Coordinator, 4: Inner Circle)",
        "type": 2,  # INTEGER_GREATER_THAN_OR_EQUAL
    },
    {
        "key": "judge",
        "name": "Judge Level",
        "description": "VEKN judge certification (1: Judgekin, 2: Judge, 3: Rulemonger)",
        "type": 2,
    },
    {
        "key": "playtest",
        "name": "Playtest Role",
        "description": "VEKN playtest participation (1: Playtester, 2: Playtest Coordinator)",
        "type": 2,
    },
]

# Role to integer level mappings
_ORG_LEVELS = {Role.PRINCE: 2, Role.NC: 3, Role.IC: 4}
_JUDGE_LEVELS = {Role.JUDGEKIN: 1, Role.JUDGE: 2, Role.RULEMONGER: 3}
_PT_LEVELS = {Role.PT: 1, Role.PTC: 2}


def build_metadata(user) -> dict[str, int]:
    """Convert User roles to integer metadata levels."""
    roles = set(user.roles)
    org = max((_ORG_LEVELS.get(r, 0) for r in roles), default=0)
    if org == 0 and getattr(user, "vekn_id", None):
        org = 1
    judge = max((_JUDGE_LEVELS.get(r, 0) for r in roles), default=0)
    playtest = max((_PT_LEVELS.get(r, 0) for r in roles), default=0)
    return {"organization": org, "judge": judge, "playtest": playtest}


def build_platform_info(user) -> tuple[str, str]:
    """Return (platform_name, platform_username) for Discord profile display."""
    username = user.vekn_id if getattr(user, "vekn_id", None) else (user.name or "")
    return ("Archon", username)


async def register_metadata() -> None:
    """Register role connection metadata with Discord (idempotent PUT on startup)."""
    client_id = os.getenv("DISCORD_CLIENTID", "")
    bot_token = os.getenv("DISCORD_BOT_TOKEN", "")
    if not client_id or not bot_token:
        logger.info("Discord Linked Roles: skipped (DISCORD_CLIENTID or DISCORD_BOT_TOKEN not set)")
        return

    url = f"https://discord.com/api/v10/applications/{client_id}/role-connections/metadata"
    headers = {"Authorization": f"Bot {bot_token}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.put(url, json=METADATA, headers=headers) as resp:
            if resp.status == 200:
                logger.info("Discord Linked Roles: metadata registered successfully")
            else:
                text = await resp.text()
                logger.error(f"Discord Linked Roles: metadata registration failed ({resp.status}): {text}")


async def push_role_metadata(user, access_token: str) -> bool:
    """Push role metadata to Discord for a user using their OAuth access token."""
    client_id = os.getenv("DISCORD_CLIENTID", "")
    if not client_id:
        return False

    metadata = build_metadata(user)
    platform_name, platform_username = build_platform_info(user)

    url = f"https://discord.com/api/v10/users/@me/applications/{client_id}/role-connection"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    body = {
        "platform_name": platform_name,
        "platform_username": platform_username,
        "metadata": metadata,
    }

    async with aiohttp.ClientSession() as session:
        async with session.put(url, json=body, headers=headers) as resp:
            if resp.status == 200:
                logger.info(f"Discord Linked Roles: pushed metadata for user {user.uid}")
                return True
            text = await resp.text()
            logger.error(f"Discord Linked Roles: push failed ({resp.status}): {text}")
            return False


async def refresh_discord_token(refresh_token: str) -> dict | None:
    """Refresh an expired Discord OAuth token. Returns new token dict or None."""
    client_id = os.getenv("DISCORD_CLIENTID", "")
    client_secret = os.getenv("DISCORD_SECRET", "")
    if not client_id or not client_secret:
        return None

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.warning(f"Discord token refresh failed ({resp.status})")
            return None


async def sync_user_discord_roles(user_uid: str) -> None:
    """High-level: refresh stored token and push updated metadata. Fire-and-forget safe."""
    try:
        from ..db import get_user_by_uid

        stored = await get_transient_token(f"discord_rc:{user_uid}")
        if not stored:
            return  # User has no stored Discord token

        user = await get_user_by_uid(user_uid)
        if not user:
            return

        access_token = stored.get("access_token", "")
        rt = stored.get("refresh_token", "")

        # Try push with current token
        ok = await push_role_metadata(user, access_token)
        if ok:
            return

        # Token likely expired — refresh
        if not rt:
            await delete_transient_token(f"discord_rc:{user_uid}")
            return

        new_tokens = await refresh_discord_token(rt)
        if not new_tokens:
            await delete_transient_token(f"discord_rc:{user_uid}")
            return

        # Store refreshed tokens
        from datetime import UTC, datetime, timedelta

        await store_transient_token(
            f"discord_rc:{user_uid}",
            {"access_token": new_tokens["access_token"], "refresh_token": new_tokens.get("refresh_token", rt)},
            datetime.now(UTC) + timedelta(days=365),
        )

        await push_role_metadata(user, new_tokens["access_token"])
    except Exception:
        logger.exception(f"Discord Linked Roles: sync failed for user {user_uid}")
