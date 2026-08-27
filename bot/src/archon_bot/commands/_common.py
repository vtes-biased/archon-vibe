"""Shared helpers for slash-command and component callbacks."""

from typing import Protocol

import hikari

from ..archon_api import ApiResult, ArchonAPI


class _Responder(Protocol):
    """Anything with an ephemeral-capable `respond` (lightbulb/miru contexts)."""

    async def respond(
        self, content: str, *, flags: hikari.MessageFlag = ...
    ) -> object: ...


async def fetch_userinfo(
    api: ArchonAPI,
    ctx: _Responder,
    discord_id: str,
    tournament_uid: str,
    *,
    account: str = "account",
) -> ApiResult | None:
    """Fetch /oauth/userinfo; on failure respond ephemerally and return None.

    Folds the get_userinfo + `not info.ok` + ephemeral error-respond block shared
    by every verify-and-bail command. Caller bails on None, otherwise reads
    info.data. Role gating stays at the call site (it varies per command).
    """
    info = await api.get_userinfo(discord_id, tournament_uid)
    if not info.ok:
        await ctx.respond(
            f"Could not verify your {account}: {info.error}",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return None
    return info
