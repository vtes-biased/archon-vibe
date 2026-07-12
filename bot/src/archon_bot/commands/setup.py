"""Organizer commands: /setup, /teardown, /announce."""

import logging
import secrets

import hikari
import lightbulb

from .. import config
from ..archon_api import ArchonAPI
from ..channel_manager import create_tournament_channels, teardown_tournament
from ..oauth_utils import generate_pkce, make_oauth_url
from ..scheduled_events import delete_scheduled_event
from ..sse_listener import (
    probe_tournament,
    start_sse,
    stop_sse,
    structural_lock,
    sync_now,
    tracked_table_channels,
)
from ..token_store import TokenStore
from ..tournament_resolver import resolve_tournament
from ._common import fetch_userinfo

logger = logging.getLogger(__name__)

ORGANIZER_ROLES = config.SETUP_ROLES


def extract_tournament_uid(url: str) -> str | None:
    """Extract tournament UID from Archon URL like /tournaments/<uid>."""
    parts = url.rstrip("/").split("/")
    for i, part in enumerate(parts):
        if part == "tournaments" and i + 1 < len(parts):
            return parts[i + 1]
    return None


class SetupCommand(
    lightbulb.SlashCommand,
    name="setup",
    description="Link a tournament to this Discord server",
):
    url = lightbulb.string("url", "Archon tournament URL")

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        *,
        store: TokenStore,
        api: ArchonAPI,
    ) -> None:
        if not ctx.guild_id:
            await ctx.respond(
                "This command must be used in a server.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        tournament_uid = extract_tournament_uid(self.url)
        if not tournament_uid:
            await ctx.respond(
                "Invalid tournament URL. Use the full URL from Archon (e.g., https://archon.example/tournaments/abc123).",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        discord_id = str(ctx.user.id)

        # Check if user has tokens
        tokens = await store.get_tokens(discord_id)
        if not tokens:
            state = secrets.token_urlsafe(32)
            code_verifier, code_challenge = generate_pkce()
            await store.store_pending_oauth(
                state=state,
                discord_id=discord_id,
                code_verifier=code_verifier,
            )
            url = make_oauth_url(state, code_challenge)
            await ctx.respond(
                f"**Authorize Archon Bot**\nClick the link below to connect your Archon account:\n{url}\n\n"
                f"After authorization, run `/setup {self.url}` again.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        # Check user has NC/Prince/IC role
        info = await fetch_userinfo(api, ctx, discord_id, account="Archon account")
        if info is None:
            return

        roles = set(info.data.get("roles", []))
        if not roles & ORGANIZER_ROLES:
            await ctx.respond(
                "Only NC, Prince, or IC members can set up tournament channels.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        # Check if already linked
        existing = await store.get_tournament_link(str(ctx.guild_id), tournament_uid)
        if existing:
            await ctx.respond(
                "This tournament is already linked to this server. Use `/teardown` first to unlink.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        # Probe BEFORE any side effect: a typo'd or inaccessible uid must not
        # leave a dead category plus a listener reconnecting forever. Also the
        # only way the bot learns the tournament's real name and state.
        tournament = await probe_tournament(api, store, discord_id, tournament_uid)
        if tournament is None:
            await ctx.respond(
                "Tournament not found or no access — check the URL (and that "
                "Archon is reachable), then try again.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return
        if tournament.get("state") == "Finished":
            await ctx.respond(
                "This tournament is already finished — nothing to set up.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        await ctx.respond(
            "Setting up tournament channels...", flags=hikari.MessageFlag.EPHEMERAL
        )

        # Create channels
        try:
            channels = await create_tournament_channels(
                ctx.client.app,
                ctx.guild_id,
                tournament.get("name") or tournament_uid[:8],
                int(discord_id),
            )
        except Exception as e:
            await ctx.respond(
                f"Failed to create channels: {e}", flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        # Store link
        await store.link_tournament(
            guild_id=str(ctx.guild_id),
            tournament_uid=tournament_uid,
            organizer_discord_id=discord_id,
            **channels,
        )

        # Start SSE listener
        await start_sse(
            ctx.client.app,
            api,
            store,
            str(ctx.guild_id),
            tournament_uid,
            discord_id,
        )

        # Post welcome messages
        webapp_url = f"{config.ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"
        ann_id = int(channels["announcement_channel_id"])
        lobby_id = int(channels["lobby_channel_id"])
        judges_id = int(channels["judges_channel_id"])

        try:
            await ctx.client.app.rest.create_message(
                ann_id,
                "**Tournament linked!**\n"
                "This channel will post seatings, results, and announcements.\n"
                "Registration is not open yet — watch this space.",
            )
            await ctx.client.app.rest.create_message(
                lobby_id,
                f"Welcome! This is the tournament lobby.\n"
                f"When registration opens, use `/register` here to sign up.\n"
                f"Tournament details: {webapp_url}",
            )
            await ctx.client.app.rest.create_message(
                judges_id,
                f"**Tournament linked by <@{discord_id}>**\n"
                f"Open registration from the webapp when ready.\n"
                f"This channel will receive judge calls, sanctions, and organizer guidance.\n"
                f"{webapp_url}",
            )
        except Exception as e:
            logger.warning("Failed to post welcome messages: %s", e)

        await ctx.respond(
            f"Tournament linked! Channels created.\n"
            f"Announcement: <#{channels['announcement_channel_id']}>\n"
            f"Lobby: <#{channels['lobby_channel_id']}>\n"
            f"Judges: <#{channels['judges_channel_id']}>",
            flags=hikari.MessageFlag.EPHEMERAL,
        )


class TeardownCommand(
    lightbulb.SlashCommand,
    name="teardown",
    description="Remove all bot-created channels for a tournament",
):
    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        *,
        store: TokenStore,
        api: ArchonAPI,
    ) -> None:
        tournament_uid = await resolve_tournament(ctx, store)
        if not tournament_uid:
            return

        guild_id = str(ctx.guild_id)
        discord_id = str(ctx.user.id)

        link = await store.get_tournament_link(guild_id, tournament_uid)
        if not link:
            await ctx.respond(
                "Tournament link not found.", flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        # Verify the user has organizer rights
        is_archon_organizer = False
        info = await api.get_userinfo(discord_id)
        if info.ok:
            roles = set(info.data.get("roles", []))
            is_archon_organizer = bool(roles & ORGANIZER_ROLES)

        if link["organizer_discord_id"] != discord_id and not is_archon_organizer:
            await ctx.respond(
                "You don't have permission to teardown. Only the setup organizer or NC/Prince/IC can do this.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        await ctx.respond(
            "Removing tournament channels...", flags=hikari.MessageFlag.EPHEMERAL
        )

        # Hold the structural lock for the whole delete and unlink FIRST, so a
        # reconcile queued behind us re-reads a gone link and no-ops (teardown wins).
        failed: list[int] = []
        async with structural_lock(guild_id, tournament_uid):
            # Snapshot tracked table/finals channels BEFORE stop_sse clears the map;
            # teardown then also reaches channels that drifted out of the category.
            extra_ids = [
                int(link[k])
                for k in (
                    "announcement_channel_id",
                    "lobby_channel_id",
                    "judges_channel_id",
                )
                if link.get(k)
            ]
            extra_ids += tracked_table_channels(guild_id, tournament_uid)

            # Remove the Discord scheduled event before the link row is dropped.
            try:
                await delete_scheduled_event(
                    ctx.client.app, store, guild_id, tournament_uid
                )
            except Exception as e:
                logger.warning("Failed to delete scheduled event on teardown: %s", e)

            await stop_sse(guild_id, tournament_uid)
            await store.unlink_tournament(guild_id, tournament_uid)

            try:
                failed = await teardown_tournament(
                    ctx.client.app,
                    ctx.guild_id,
                    int(link["category_id"]),
                    extra_ids,
                )
            except Exception as e:
                logger.warning("Teardown error: %s", e)
        msg = (
            f"Removed tournament channels, but {len(failed)} could not be deleted "
            "— check my **Manage Channels** permission and remove any leftovers "
            "manually."
            if failed
            else "Tournament channels removed."
        )
        try:
            await ctx.respond(msg, flags=hikari.MessageFlag.EPHEMERAL)
        except (hikari.NotFoundError, hikari.BadRequestError):
            # /teardown is usually run from a channel inside the category it just
            # deleted, so this follow-up targets a gone channel (10003 Unknown
            # Channel). The teardown already completed — nothing left to report.
            logger.info("Teardown done; status reply skipped (invoking channel gone)")


class AnnounceCommand(
    lightbulb.SlashCommand,
    name="announce",
    description="Post a message to the announcement channel",
):
    message = lightbulb.string("message", "Message to announce")

    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        *,
        store: TokenStore,
        api: ArchonAPI,
    ) -> None:
        tournament_uid = await resolve_tournament(ctx, store)
        if not tournament_uid:
            return

        guild_id = str(ctx.guild_id)
        discord_id = str(ctx.user.id)

        link = await store.get_tournament_link(guild_id, tournament_uid)
        if not link:
            await ctx.respond(
                "Tournament link not found.", flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        # Verify organizer permissions
        is_organizer = link["organizer_discord_id"] == discord_id
        if not is_organizer:
            info = await api.get_userinfo(discord_id)
            if not info.ok or not set(info.data.get("roles", [])) & ORGANIZER_ROLES:
                await ctx.respond(
                    "Only the setup organizer or NC/Prince/IC can post announcements.",
                    flags=hikari.MessageFlag.EPHEMERAL,
                )
                return

        try:
            await ctx.client.app.rest.create_message(
                int(link["announcement_channel_id"]),
                f"**Announcement:** {self.message}",
            )
            await ctx.respond(
                "Announcement posted!", flags=hikari.MessageFlag.EPHEMERAL
            )
        except Exception as e:
            await ctx.respond(
                f"Failed to post announcement: {e}", flags=hikari.MessageFlag.EPHEMERAL
            )


class SyncCommand(
    lightbulb.SlashCommand,
    name="sync",
    description="Repair this tournament's voice channels to match its current state",
):
    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        *,
        store: TokenStore,
        api: ArchonAPI,
    ) -> None:
        tournament_uid = await resolve_tournament(ctx, store)
        if not tournament_uid:
            return

        guild_id = str(ctx.guild_id)
        discord_id = str(ctx.user.id)

        link = await store.get_tournament_link(guild_id, tournament_uid)
        if not link:
            await ctx.respond(
                "Tournament link not found.", flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        # Same organizer gate as /announce and /teardown.
        is_organizer = link["organizer_discord_id"] == discord_id
        if not is_organizer:
            info = await api.get_userinfo(discord_id)
            if not info.ok or not set(info.data.get("roles", [])) & ORGANIZER_ROLES:
                await ctx.respond(
                    "Only the setup organizer or NC/Prince/IC can sync channels.",
                    flags=hikari.MessageFlag.EPHEMERAL,
                )
                return

        # Already deferred ephemerally by the PRE_INVOKE hook, so one respond after
        # the reconcile's REST work delivers the result (no interim message needed).
        summary = await sync_now(ctx.client.app, store, guild_id, tournament_uid)
        if summary is None:
            await ctx.respond(
                "No live tournament state yet — the bot may still be connecting. "
                "Try again in a moment.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return
        if summary.aborted:
            await ctx.respond(
                "Sync aborted: the tournament category is missing. See "
                f"<#{link['judges_channel_id']}> — recreate it, or `/teardown` "
                "then `/setup`.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        parts = []
        if summary.created:
            parts.append(f"created {len(summary.created)}")
        if summary.deleted:
            parts.append(f"removed {len(summary.deleted)}")
        if summary.synced:
            parts.append(f"updated {len(summary.synced)}")
        detail = ", ".join(parts) if parts else "no changes — already in sync"
        await ctx.respond(
            f"Voice channels synced ({detail}).",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
