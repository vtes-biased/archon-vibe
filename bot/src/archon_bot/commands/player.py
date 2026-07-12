"""Player commands: /register, /checkin, /report, /judge."""

import logging
import secrets

import hikari
import lightbulb
import miru

from .. import config
from ..archon_api import ArchonAPI
from ..oauth_utils import generate_pkce, make_oauth_url
from ..token_store import TokenStore
from ..tournament_resolver import resolve_tournament
from ._common import fetch_userinfo

logger = logging.getLogger(__name__)


async def _ensure_auth(ctx: lightbulb.Context, store: TokenStore) -> dict | None:
    """Ensure the user is authenticated. Returns tokens or sends OAuth link."""
    discord_id = str(ctx.user.id)
    tokens = await store.get_tokens(discord_id)
    if tokens:
        return tokens

    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce()
    await store.store_pending_oauth(
        state=state,
        discord_id=discord_id,
        code_verifier=code_verifier,
    )
    url = make_oauth_url(state, code_challenge)
    await ctx.respond(
        f"**Connect your Archon account**\n"
        f"Click the link below to authenticate:\n{url}\n\n"
        f"After authentication, run the command again.",
        flags=hikari.MessageFlag.EPHEMERAL,
    )
    return None


# --- VEKN ID Modal ---


class VeknIdModal(miru.Modal, title="Enter your VEKN ID"):
    vekn_id = miru.TextInput(
        label="VEKN ID",
        placeholder="e.g., 1234567",
        required=True,
        min_length=1,
        max_length=20,
    )

    def __init__(
        self, store: TokenStore, api: ArchonAPI, tournament_uid: str, action: str
    ) -> None:
        super().__init__()
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid
        self._action = action

    async def callback(self, ctx: miru.ModalContext) -> None:
        discord_id = str(ctx.user.id)
        claim = await self._api.claim_vekn_id(discord_id, self.vekn_id.value.strip())
        if not claim.ok:
            await ctx.respond(
                f"Could not claim VEKN ID: {claim.error}",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        # The claim MERGES the bot-linked account into the VEKN one and
        # tombstones the old uid — the stored OAuth tokens now authenticate a
        # dead account (refresh keeps "succeeding" but every call 401s), so drop
        # them; the next command re-links cleanly. The claim response carries a
        # fresh first-party token pair for the merged account: use its access
        # token once for the immediate follow-up action (it can't be stored —
        # it's not an OAuth-client token and can't be refreshed as one).
        await self._store.remove_tokens(discord_id)

        # Mirror the has-VEKN mapping: Register during Registration, CheckIn
        # during check-in — the engine rejects the wrong event for the phase.
        display_name = _get_display_name(ctx)
        merged = claim.data.get("user", {})
        event_name = "CheckIn" if self._action == "checkin" else "Register"
        reg = await self._api.tournament_action_with_token(
            claim.data.get("access_token", ""),
            self._tournament_uid,
            event_name,
            player_uid=merged.get("uid") if event_name == "CheckIn" else None,
            user_uid=merged.get("uid") if event_name == "Register" else None,
            vekn_id=merged.get("vekn_id"),
            display_name=display_name,
        )
        if reg.ok:
            verb = "checked in" if self._action == "checkin" else "registered"
            await ctx.respond(
                f"VEKN ID claimed and you're {verb}!",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
        else:
            noun = "check-in" if self._action == "checkin" else "registration"
            await ctx.respond(
                f"VEKN ID claimed, but {noun} failed: {reg.error}\n"
                f"Run `/{self._action}` again.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )


# --- VEKN ID Claim Button ---


class VeknChoiceView(miru.View):
    def __init__(
        self, store: TokenStore, api: ArchonAPI, tournament_uid: str, action: str
    ) -> None:
        super().__init__(timeout=300)
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid
        self._action = action

    @miru.button(label="I have a VEKN ID", style=hikari.ButtonStyle.PRIMARY)
    async def has_vekn(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        modal = VeknIdModal(self._store, self._api, self._tournament_uid, self._action)
        await ctx.respond_with_modal(modal)
        self.stop()


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
    miru_client: miru.Client,
    tournament_uid: str,
    action: str,
) -> None:
    """Shared pipeline for /register and /checkin."""
    discord_id = str(ctx.user.id)

    # Step 1: Check authentication
    tokens = await _ensure_auth(ctx, store)
    if not tokens:
        return

    # Step 2: Check VEKN ID
    info = await fetch_userinfo(api, ctx, discord_id)
    if info is None:
        return

    vekn_id = info.data.get("vekn_id")
    archon_uid = info.data["sub"]

    if vekn_id:
        # Has VEKN ID → register/checkin directly
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

            # Check for missing decklist warning
            player_entry = next(
                (
                    p
                    for p in result.data.get("players", [])
                    if p.get("user_uid") == archon_uid
                ),
                None,
            )
            if player_entry and player_entry.get("missing_decklist"):
                msg += (
                    f"\n\n**Warning:** This tournament requires a decklist. "
                    f"Upload yours before the round starts:\n"
                    f"{config.ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"
                )
            elif result.data.get("decklist_required"):
                msg += (
                    f"\n\nThis tournament requires a decklist. "
                    f"Don't forget to upload yours:\n"
                    f"{config.ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"
                )

            await ctx.respond(msg, flags=hikari.MessageFlag.EPHEMERAL)
        else:
            await ctx.respond(
                f"{'Check-in' if action == 'checkin' else 'Registration'} failed: {result.error}",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
    else:
        # No VEKN ID linked. If they already have one, let them claim it here;
        # new players are created at the door by an official (sponsorship is no
        # longer a bot flow — the desk curates the member list).
        view = VeknChoiceView(store, api, tournament_uid, action)
        await ctx.respond(
            "**You need a VEKN ID to play.**\n"
            "If you already have one, tap the button below to link it.\n"
            "If you're new to VTES, see a tournament official at the "
            "check-in desk — they'll register you.",
            components=view,
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        miru_client.start_view(view)


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
        miru_client: miru.Client,
    ) -> None:
        tournament_uid = await resolve_tournament(ctx, store)
        if not tournament_uid:
            return

        await _handle_registration_pipeline(
            ctx, store, api, miru_client, tournament_uid, "register"
        )


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
        miru_client: miru.Client,
    ) -> None:
        tournament_uid = await resolve_tournament(ctx, store)
        if not tournament_uid:
            return

        await _handle_registration_pipeline(
            ctx, store, api, miru_client, tournament_uid, "checkin"
        )


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

        # Check authentication
        tokens = await _ensure_auth(ctx, store)
        if not tokens:
            return

        # Get user info for archon_uid
        info = await fetch_userinfo(api, ctx, discord_id)
        if info is None:
            return

        archon_uid = info.data["sub"]
        guild_id = str(ctx.guild_id)

        # Find player's table from cached tournament data
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
                "Tournament configuration not found. Ask an organizer to run `/setup` again.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        judges_id = int(link["judges_channel_id"])
        display_name = _get_display_name(ctx) or ctx.user.username

        # Use the channel name as table context
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
