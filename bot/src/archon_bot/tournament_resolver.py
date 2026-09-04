import logging

import hikari
import lightbulb

from .command_mentions import command_mention
from .token_store import TokenStore

logger = logging.getLogger(__name__)


async def resolve_tournament(ctx: lightbulb.Context, store: TokenStore) -> str | None:
    if not ctx.guild_id:
        await ctx.respond(
            "This command must be used in a server.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return None

    guild_id = str(ctx.guild_id)
    tournaments = await store.get_guild_tournaments(guild_id)

    if not tournaments:
        await ctx.respond(
            f"No tournament is linked to this server. Ask an organizer to run {command_mention('setup')}.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return None

    category_id = await _find_category_id(ctx)

    if category_id:
        match = await store.get_tournament_by_category(guild_id, str(category_id))
        if match:
            return match["tournament_uid"]

    lines = ["Run this command in a tournament channel. Active tournaments:"]
    for t in tournaments:
        lines.append(f"  <#{t['lobby_channel_id']}>")

    await ctx.respond("\n".join(lines), flags=hikari.MessageFlag.EPHEMERAL)
    return None


async def _find_category_id(ctx: lightbulb.Context) -> int | None:
    channel = ctx.client.app.cache.get_guild_channel(ctx.channel_id)
    if channel is None:
        try:
            channel = await ctx.client.app.rest.fetch_channel(ctx.channel_id)
        except Exception:
            return None

    if isinstance(channel, hikari.GuildCategory):
        return channel.id

    parent_id = getattr(channel, "parent_id", None)
    if parent_id:
        return parent_id

    return None
