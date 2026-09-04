import hikari
import lightbulb

from ..archon_api import ApiResult, ArchonAPI


async def fetch_userinfo(
    api: ArchonAPI,
    ctx: lightbulb.Context,
    discord_id: str,
    tournament_uid: str,
    *,
    account: str = "account",
) -> ApiResult | None:
    """None means the caller bails: the ephemeral error is already sent."""
    info = await api.get_userinfo(discord_id, tournament_uid)
    if not info.ok:
        await ctx.respond(
            f"Could not verify your {account}: {info.error}",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return None
    return info
