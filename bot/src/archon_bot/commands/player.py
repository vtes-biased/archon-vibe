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


async def _ensure_auth(
    ctx: lightbulb.Context, store: TokenStore, action: str, extra: str = ""
) -> dict | None:
    """Ensure the user is authenticated. Returns tokens or sends OAuth link."""
    discord_id = str(ctx.author.id)
    tokens = await store.get_tokens(discord_id)
    if tokens:
        return tokens

    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = generate_pkce()
    await store.store_pending_oauth(
        state=state,
        discord_id=discord_id,
        guild_id=str(ctx.guild_id or 0),
        channel_id=str(ctx.channel_id),
        action=action,
        extra=extra,
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

    def __init__(self, store: TokenStore, api: ArchonAPI, tournament_uid: str) -> None:
        super().__init__()
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid

    async def callback(self, ctx: miru.ModalContext) -> None:
        discord_id = str(ctx.author.id)
        claim = await self._api.claim_vekn_id(discord_id, self.vekn_id.value.strip())
        if not claim.ok:
            await ctx.respond(
                f"Could not claim VEKN ID: {claim.error}",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        # Now try to check in
        display_name = _get_display_name(ctx)
        archon_uid = claim.data.get("user", {}).get("uid", "")
        reg = await self._api.tournament_action(
            discord_id,
            self._tournament_uid,
            "CheckIn",
            player_uid=archon_uid,
            display_name=display_name,
        )
        if reg.ok:
            await ctx.respond(
                "VEKN ID claimed and you're checked in!",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
        else:
            await ctx.respond(
                f"VEKN ID claimed, but check-in failed: {reg.error}\n"
                f"Try `/checkin` again.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )


# --- Sponsorship Modal ---


class SponsorshipModal(miru.Modal, title="New Player Registration"):
    country = miru.TextInput(
        label="Country (ISO code, e.g., US, FR, DE)",
        placeholder="US",
        required=True,
        min_length=2,
        max_length=2,
    )
    city = miru.TextInput(
        label="City (optional)",
        placeholder="New York",
        required=False,
    )

    def __init__(
        self, store: TokenStore, api: ArchonAPI, tournament_uid: str, guild_id: str
    ) -> None:
        super().__init__()
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid
        self._guild_id = guild_id

    async def callback(self, ctx: miru.ModalContext) -> None:
        discord_id = str(ctx.author.id)
        info = await fetch_userinfo(self._api, ctx, discord_id)
        if info is None:
            return

        link = await self._store.get_tournament_link(
            self._guild_id, self._tournament_uid
        )
        if not link:
            await ctx.respond(
                "Tournament configuration not found. Ask an organizer to run `/setup` again.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        judges_id = int(link["judges_channel_id"])

        view = SponsorshipView(
            self._store,
            self._api,
            self._tournament_uid,
            player_discord_id=discord_id,
            player_uid=info.data["sub"],
            country=self.country.value.strip().upper(),
            city=self.city.value.strip() if self.city.value else "",
        )

        try:
            await ctx.client.app.rest.create_message(
                judges_id,
                f"**New player sponsorship request**\n"
                f"Player: <@{discord_id}>\n"
                f"Country: {self.country.value.strip().upper()}\n"
                f"City: {self.city.value.strip() or 'N/A'}",
                components=view,
            )
        except hikari.ForbiddenError:
            await ctx.respond(
                "Cannot post to the judges channel. The bot may be missing permissions.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        await ctx.respond(
            "Your sponsorship request has been sent to the judges. Please wait for approval.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )


# --- Sponsorship Approve/Deny Buttons ---


class SponsorshipView(miru.View):
    def __init__(
        self,
        store: TokenStore,
        api: ArchonAPI,
        tournament_uid: str,
        player_discord_id: str,
        player_uid: str,
        country: str,
        city: str,
    ) -> None:
        super().__init__(timeout=3600)
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid
        self._player_discord_id = player_discord_id
        self._player_uid = player_uid
        self._country = country
        self._city = city

    @miru.button(label="Approve", style=hikari.ButtonStyle.SUCCESS)
    async def approve(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        organizer_discord_id = str(ctx.author.id)

        info = await fetch_userinfo(self._api, ctx, organizer_discord_id)
        if info is None:
            return

        roles = set(info.data.get("roles", []))
        if not roles & {"IC", "NC", "Prince"}:
            await ctx.respond(
                "You need NC, Prince, or IC rights to sponsor players.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        sponsor = await self._api.sponsor_player(
            organizer_discord_id, self._player_uid, self._country, self._city
        )
        if not sponsor.ok:
            await ctx.respond(
                f"Sponsorship failed: {sponsor.error}",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        # Auto check-in the player
        reg = await self._api.tournament_action(
            self._player_discord_id,
            self._tournament_uid,
            "CheckIn",
            player_uid=self._player_uid,
        )
        status = (
            "Sponsored and checked in!"
            if reg.ok
            else f"Sponsored, but check-in failed: {reg.error}"
        )
        await ctx.edit_response(
            f"**Approved** by <@{organizer_discord_id}>. {status}",
            components=[],
        )
        self.stop()

    @miru.button(label="Deny", style=hikari.ButtonStyle.DANGER)
    async def deny(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        await ctx.edit_response(
            f"**Denied** by <@{ctx.author.id}>.",
            components=[],
        )
        self.stop()

    async def on_timeout(self) -> None:
        try:
            if self.message:
                await self.message.edit(
                    "**Sponsorship request expired** (1 hour timeout).",
                    components=[],
                )
        except Exception:
            pass


# --- VEKN Choice Buttons ---


class VeknChoiceView(miru.View):
    def __init__(
        self, store: TokenStore, api: ArchonAPI, tournament_uid: str, guild_id: str
    ) -> None:
        super().__init__(timeout=300)
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid
        self._guild_id = guild_id

    @miru.button(label="I have a VEKN ID", style=hikari.ButtonStyle.PRIMARY)
    async def has_vekn(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        modal = VeknIdModal(self._store, self._api, self._tournament_uid)
        await ctx.respond_with_modal(modal)
        self.stop()

    @miru.button(label="I'm new", style=hikari.ButtonStyle.SECONDARY)
    async def is_new(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        modal = SponsorshipModal(
            self._store, self._api, self._tournament_uid, self._guild_id
        )
        await ctx.respond_with_modal(modal)
        self.stop()


def _get_display_name(ctx) -> str | None:
    """Get Discord guild nickname for use as display_name (snapshot)."""
    member = getattr(ctx, "member", None)
    if member:
        return (
            member.nickname
            or getattr(member, "display_name", None)
            or ctx.author.username
        )
    return ctx.author.username


async def _handle_registration_pipeline(
    ctx: lightbulb.Context,
    store: TokenStore,
    api: ArchonAPI,
    miru_client: miru.Client,
    tournament_uid: str,
    action: str,
) -> None:
    """Shared pipeline for /register and /checkin."""
    discord_id = str(ctx.author.id)

    # Step 1: Check authentication
    tokens = await _ensure_auth(ctx, store, action, tournament_uid)
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
        # No VEKN ID → show choice buttons
        guild_id = str(ctx.guild_id) if ctx.guild_id else "0"
        view = VeknChoiceView(store, api, tournament_uid, guild_id)
        await ctx.respond(
            "**You need a VEKN ID to play.**\n"
            "Do you already have one, or are you a new player?",
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

        discord_id = str(ctx.author.id)

        # Check authentication
        tokens = await _ensure_auth(ctx, store, "report", tournament_uid)
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
        display_name = _get_display_name(ctx) or ctx.author.username

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
