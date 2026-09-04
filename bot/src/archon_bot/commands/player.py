import logging

import hikari
import lightbulb
from hikari.impl import MessageActionRowBuilder

from .. import config
from ..archon_api import ArchonAPI
from ..command_mentions import command_mention
from ..oauth_utils import (
    generate_pkce,
    generate_state,
    make_oauth_url,
)
from ..token_store import TokenStore
from ..tournament_resolver import resolve_tournament
from ._common import fetch_userinfo

logger = logging.getLogger(__name__)


async def _ensure_auth(
    ctx: lightbulb.Context, store: TokenStore, tournament_uid: str
) -> dict | None:
    discord_id = str(ctx.user.id)
    tokens = await store.get_tokens(discord_id, tournament_uid)
    if tokens:
        return tokens

    state = generate_state()
    code_verifier, code_challenge = generate_pkce()
    await store.store_pending_oauth(
        state=state,
        discord_id=discord_id,
        tournament_uid=tournament_uid,
        code_verifier=code_verifier,
    )
    url = make_oauth_url(state, code_challenge, tournament_uid)
    await ctx.respond(
        "**Connect your Archon account**\n"
        "Use the button below to authenticate, then run the command again.",
        component=MessageActionRowBuilder().add_link_button(
            url, label="Connect Archon account"
        ),
        flags=hikari.MessageFlag.EPHEMERAL,
    )
    return None


def _get_display_name(ctx) -> str | None:
    """Get Discord guild nickname for use as display_name (snapshot)."""
    member = getattr(ctx, "member", None)
    if member:
        return (
            member.nickname
            or getattr(member, "display_name", None)
            or ctx.user.username
        )
    return ctx.user.username


async def _handle_registration_pipeline(
    ctx: lightbulb.Context,
    store: TokenStore,
    api: ArchonAPI,
    tournament_uid: str,
    action: str,
) -> None:
    """Shared pipeline for /register and /checkin."""
    discord_id = str(ctx.user.id)

    tokens = await _ensure_auth(ctx, store, tournament_uid)
    if not tokens:
        return

    info = await fetch_userinfo(api, ctx, discord_id, tournament_uid)
    if info is None:
        return

    vekn_id = info.data.get("vekn_id")
    archon_uid = info.data["sub"]

    if vekn_id:
        display_name = _get_display_name(ctx)
        event_name = "CheckIn" if action == "checkin" else "Register"

        result = await api.tournament_action(
            discord_id,
            tournament_uid,
            event_name,
            player_uid=archon_uid if event_name == "CheckIn" else None,
            user_uid=archon_uid if event_name == "Register" else None,
            vekn_id=vekn_id,
            display_name=display_name,
        )
        if result.ok:
            msg = f"You're {'checked in' if action == 'checkin' else 'registered'}!"

            player_entry = next(
                (
                    p
                    for p in result.data.get("players", [])
                    if p.get("user_uid") == archon_uid
                ),
                None,
            )
            if player_entry and player_entry.get("waitlisted"):
                msg = (
                    "You're on the **waitlist** — the event is at its "
                    "registration cap. An organizer will promote you if a seat "
                    "opens; you cannot check in until they do."
                )
            if (
                action == "checkin"
                and player_entry
                and player_entry.get("missing_decklist")
            ):
                msg += (
                    "\n\n**Warning:** This tournament requires a decklist and "
                    "none of yours is on record. Upload it before the round "
                    "starts:\n" + config.event_url(result.data, tournament_uid)
                )
            elif action == "register" and result.data.get("decklist_required"):
                msg += (
                    "\n\nThis tournament requires a decklist. "
                    "Don't forget to upload yours:\n"
                    + config.event_url(result.data, tournament_uid)
                )

            await ctx.respond(msg, flags=hikari.MessageFlag.EPHEMERAL)
        else:
            await ctx.respond(
                f"{'Check-in' if action == 'checkin' else 'Registration'} failed: {result.error}",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
    else:
        # Sponsorship is no longer a bot flow — new players are created at the
        # door by an official, who curates the member list. Claiming an existing
        # VEKN ID merges two accounts, which a per-event grant cannot reach.
        await ctx.respond(
            "**You need a VEKN ID to play.**\n"
            f"If you already have one, link it on your Archon profile — "
            f"{config.ARCHON_FRONTEND_URL}/profile — then run the command again.\n"
            "If you're new to VTES, see a tournament official at the "
            "check-in desk — they'll register you.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )


class RegisterCommand(
    lightbulb.SlashCommand, name="register", description="Register for the tournament"
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

        await _handle_registration_pipeline(ctx, store, api, tournament_uid, "register")


class CheckinCommand(
    lightbulb.SlashCommand, name="checkin", description="Check in for the tournament"
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

        await _handle_registration_pipeline(ctx, store, api, tournament_uid, "checkin")


_VP_CHOICES = [
    lightbulb.Choice(str(v), v) for v in [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5]
]


class ReportCommand(
    lightbulb.SlashCommand,
    name="report",
    description="Report your VP for the current round",
):
    vp = lightbulb.number("vp", "Your victory points", choices=_VP_CHOICES)

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

        discord_id = str(ctx.user.id)

        tokens = await _ensure_auth(ctx, store, tournament_uid)
        if not tokens:
            return

        info = await fetch_userinfo(api, ctx, discord_id, tournament_uid)
        if info is None:
            return

        archon_uid = info.data["sub"]
        guild_id = str(ctx.guild_id)

        from ..sse_listener import find_player_table

        location = find_player_table(guild_id, tournament_uid, archon_uid)
        if not location:
            await ctx.respond(
                "Could not find your table. Are you seated in the current round?",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        round_idx, table_idx = location

        result = await api.tournament_action(
            discord_id,
            tournament_uid,
            "SetScore",
            round=round_idx,
            table=table_idx,
            scores=[{"player_uid": archon_uid, "vp": self.vp}],
        )
        if result.ok:
            await ctx.respond(
                f"Reported **{self.vp} VP** for this round.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
        else:
            await ctx.respond(
                f"Failed to report VP: {result.error}",
                flags=hikari.MessageFlag.EPHEMERAL,
            )


class JudgeCommand(
    lightbulb.SlashCommand, name="judge", description="Call a judge to your table"
):
    @lightbulb.invoke
    async def invoke(
        self,
        ctx: lightbulb.Context,
        *,
        store: TokenStore,
    ) -> None:
        tournament_uid = await resolve_tournament(ctx, store)
        if not tournament_uid:
            return

        guild_id = str(ctx.guild_id)
        link = await store.get_tournament_link(guild_id, tournament_uid)
        if not link:
            await ctx.respond(
                f"Tournament configuration not found. Ask an organizer to run {command_mention('setup')} again.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        judges_id = int(link["judges_channel_id"])
        display_name = _get_display_name(ctx) or ctx.user.username

        table_info = "unknown location"
        try:
            channel = await ctx.client.app.rest.fetch_channel(ctx.channel_id)
            if hasattr(channel, "name") and channel.name:
                table_info = channel.name
        except Exception:
            pass

        try:
            await ctx.client.app.rest.create_message(
                judges_id,
                f"**Judge call!** {table_info} — {display_name} needs a judge",
            )
            await ctx.respond(
                "Judge has been called!", flags=hikari.MessageFlag.EPHEMERAL
            )
        except hikari.ForbiddenError:
            await ctx.respond(
                "Cannot reach the judges channel. The bot may be missing permissions.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
        except Exception as e:
            await ctx.respond(
                f"Failed to call judge: {e}",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
