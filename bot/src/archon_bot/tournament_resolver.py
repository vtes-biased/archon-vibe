"""Resolve which tournament a command targets based on the channel's category."""

import logging

import hikari
import lightbulb

from .token_store import TokenStore

logger = logging.getLogger(__name__)


async def resolve_tournament(
    ctx: lightbulb.Context, store: TokenStore
) -> str | None:
    """Resolve the tournament UID for a command based on channel category.

    The command must be run inside a tournament channel (one whose parent category
    matches a linked tournament). If not, responds with an error listing the
    available tournament lobbies.

    Returns tournament_uid or None (with error response sent).
    """
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
            "No tournament is linked to this server. Ask an organizer to run `/setup`.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        return None

    # Find the category of the current channel
    category_id = await _find_category_id(ctx)

    if category_id:
        match = await store.get_tournament_by_category(guild_id, str(category_id))
        if match:
            return match["tournament_uid"]

    # Command run outside any tournament channel — list lobbies
    lines = ["Run this command in a tournament channel. Active tournaments:"]
    for t in tournaments:
        link = await store.get_tournament_link(guild_id, t["tournament_uid"])
        if link:
            lobby_id = link["lobby_channel_id"]
            lines.append(f"  <#{lobby_id}>")

    await ctx.respond("\n".join(lines), flags=hikari.MessageFlag.EPHEMERAL)
    return None


async def _find_category_id(ctx: lightbulb.Context) -> int | None:
    """Walk up the channel hierarchy to find the category ID."""
    # Try cache first (requires GUILDS intent, which we have)
    channel = ctx.client.app.cache.get_guild_channel(ctx.channel_id)
    if channel is None:
        # Fallback to REST if not cached
        try:
            channel = await ctx.client.app.rest.fetch_channel(ctx.channel_id)
        except Exception:
            return None

    # If the channel itself is a category
    if isinstance(channel, hikari.GuildCategory):
        return channel.id

    # If the channel has a parent (category)
    parent_id = getattr(channel, "parent_id", None)
    if parent_id:
        return parent_id

    return None
