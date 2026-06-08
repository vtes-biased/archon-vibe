"""Judge commands: /sanction."""

import logging

import hikari
import lightbulb
import miru

from .. import config
from ..archon_api import ArchonAPI
from ..token_store import TokenStore
from ..tournament_resolver import resolve_tournament
from ._common import fetch_userinfo

logger = logging.getLogger(__name__)

ORGANIZER_ROLES = config.SANCTION_ROLES

# Sanction categories and subcategories (mirrors VEKN Judges Guide v2)
CATEGORIES = {
    "procedural_error": "Procedural Error",
    "tournament_error": "Tournament Error",
    "unsportsmanlike_conduct": "Unsportsmanlike Conduct",
}

SUBCATEGORIES = {
    "procedural_error": {
        "missed_mandatory_effect": "Missed Mandatory Effect",
        "card_access_error": "Card Access Error",
        "game_rule_violation": "Game Rule Violation",
        "failure_to_maintain_game_state": "Failure to Maintain Game State",
    },
    "tournament_error": {
        "illegal_decklist": "Illegal Decklist",
        "illegal_main_deck_legal_decklist": "Illegal Main Deck (Legal Decklist)",
        "illegal_main_deck_no_decklist": "Illegal Main Deck (No Decklist)",
        "outside_assistance": "Outside Assistance",
        "slow_play": "Slow Play",
        "limited_procedure_violation": "Limited Procedure Violation",
        "public_info_miscommunication": "Public Info Miscommunication",
        "obscuring_game_state": "Obscuring Game State",
        "marked_cards": "Marked Cards",
        "insufficient_shuffling": "Insufficient Shuffling",
    },
    "unsportsmanlike_conduct": {
        "minor": "Minor",
        "major": "Major",
        "aggressive_behaviour": "Aggressive Behaviour",
        "bribery_and_wagering": "Bribery and Wagering",
        "theft_of_tournament_material": "Theft of Tournament Material",
        "stalling": "Stalling",
        "cheating": "Cheating",
        "fraud": "Fraud",
        "collusion": "Collusion",
        "health_and_safety_disruption": "Health and Safety Disruption",
        "rage_quitting": "Rage Quitting",
        "failure_to_play_to_win": "Failure to Play to Win",
    },
}

LEVELS = {
    "caution": "Caution",
    "warning": "Warning",
    "standings_adjustment": "Standings Adjustment",
    "disqualification": "Disqualification",
}

# Baseline penalties per subcategory
BASELINE_PENALTIES = {
    "missed_mandatory_effect": "caution",
    "card_access_error": "caution",
    "game_rule_violation": "caution",
    "failure_to_maintain_game_state": "standings_adjustment",
    "illegal_decklist": "warning",
    "illegal_main_deck_legal_decklist": "standings_adjustment",
    "illegal_main_deck_no_decklist": "standings_adjustment",
    "outside_assistance": "standings_adjustment",
    "slow_play": "caution",
    "limited_procedure_violation": "caution",
    "public_info_miscommunication": "warning",
    "obscuring_game_state": "caution",
    "marked_cards": "warning",
    "insufficient_shuffling": "warning",
    "minor": "warning",
    "major": "standings_adjustment",
    "aggressive_behaviour": "disqualification",
    "bribery_and_wagering": "disqualification",
    "theft_of_tournament_material": "disqualification",
    "stalling": "disqualification",
    "cheating": "disqualification",
    "fraud": "disqualification",
    "collusion": "disqualification",
    "health_and_safety_disruption": "warning",
    "rage_quitting": "disqualification",
    "failure_to_play_to_win": "warning",
}


# --- Step 1: Category select ---


class CategorySelectView(miru.View):
    """First step: pick category, then show the sanction modal."""

    def __init__(
        self,
        store: TokenStore,
        api: ArchonAPI,
        tournament_uid: str,
        target_archon_uid: str,
        target_display: str,
    ) -> None:
        super().__init__(timeout=300)
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid
        self._target_uid = target_archon_uid
        self._target_display = target_display

    @miru.text_select(
        placeholder="Select infraction category...",
        options=[miru.SelectOption(label=v, value=k) for k, v in CATEGORIES.items()],
    )
    async def category_select(
        self, ctx: miru.ViewContext, select: miru.TextSelect
    ) -> None:
        category = select.values[0]

        # Build subcategory options for the modal
        subs = SUBCATEGORIES.get(category, {})
        sub_options = [miru.SelectOption(label=v, value=k) for k, v in subs.items()]

        view = SubcategorySelectView(
            self._store,
            self._api,
            self._tournament_uid,
            self._target_uid,
            self._target_display,
            category,
            sub_options,
        )
        await ctx.edit_response(
            f"**Sanction for {self._target_display}**\n"
            f"Category: {CATEGORIES[category]}\n"
            f"Select subcategory:",
            components=view,
        )
        miru_client = ctx.client
        miru_client.start_view(view)
        self.stop()


# --- Step 2: Subcategory select ---


class _SubcategorySelect(miru.TextSelect):
    """Dynamic subcategory select that opens the sanction details modal."""

    def __init__(self, options: list, **kwargs) -> None:
        super().__init__(placeholder="Select subcategory...", options=options, **kwargs)

    async def callback(self, ctx: miru.ViewContext) -> None:
        view: SubcategorySelectView = self.view  # type: ignore
        subcategory = self.values[0]
        baseline = BASELINE_PENALTIES.get(subcategory, "")
        await _open_level_select(ctx, view, subcategory, baseline)


class SubcategorySelectView(miru.View):
    def __init__(
        self,
        store: TokenStore,
        api: ArchonAPI,
        tournament_uid: str,
        target_uid: str,
        target_display: str,
        category: str,
        sub_options: list,
    ) -> None:
        super().__init__(timeout=300)
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid
        self._target_uid = target_uid
        self._target_display = target_display
        self._category = category
        options = sub_options or [miru.SelectOption(label="(none)", value="none")]
        self.add_item(_SubcategorySelect(options))

    @miru.button(label="Skip subcategory", style=hikari.ButtonStyle.SECONDARY, row=1)
    async def skip_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        await _open_level_select(ctx, self, None, "")


# --- Step 3: Penalty level select ---


class _LevelSelect(miru.TextSelect):
    """Penalty-level select; opens the details modal once a level is chosen."""

    def __init__(self, baseline: str, **kwargs) -> None:
        options = [
            miru.SelectOption(label=label, value=value, is_default=(value == baseline))
            for value, label in LEVELS.items()
        ]
        super().__init__(
            placeholder="Select penalty level...", options=options, **kwargs
        )

    async def callback(self, ctx: miru.ViewContext) -> None:
        view: LevelSelectView = self.view  # type: ignore
        modal = SanctionDetailsModal(
            view._store,
            view._api,
            view._tournament_uid,
            view._target_uid,
            view._target_display,
            view._category,
            view._subcategory,
            self.values[0],
        )
        await ctx.respond_with_modal(modal)
        view.stop()


class LevelSelectView(miru.View):
    def __init__(
        self,
        store: TokenStore,
        api: ArchonAPI,
        tournament_uid: str,
        target_uid: str,
        target_display: str,
        category: str,
        subcategory: str | None,
        baseline: str,
    ) -> None:
        super().__init__(timeout=300)
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid
        self._target_uid = target_uid
        self._target_display = target_display
        self._category = category
        self._subcategory = subcategory
        self.add_item(_LevelSelect(baseline))


async def _open_level_select(
    ctx: miru.ViewContext,
    prev: SubcategorySelectView,
    subcategory: str | None,
    baseline: str,
) -> None:
    """Transition from the subcategory step to the penalty-level select."""
    level_view = LevelSelectView(
        prev._store,
        prev._api,
        prev._tournament_uid,
        prev._target_uid,
        prev._target_display,
        prev._category,
        subcategory,
        baseline,
    )
    await ctx.edit_response(
        f"**Sanction for {prev._target_display}**\nSelect penalty level:",
        components=level_view,
    )
    ctx.client.start_view(level_view)
    prev.stop()


# --- Step 4: Details modal (description + conditional round) ---


class SanctionDetailsModal(miru.Modal, title="Issue Sanction"):
    def __init__(
        self,
        store: TokenStore,
        api: ArchonAPI,
        tournament_uid: str,
        target_uid: str,
        target_display: str,
        category: str,
        subcategory: str | None,
        level: str,
    ) -> None:
        super().__init__()
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid
        self._target_uid = target_uid
        self._target_display = target_display
        self._category = category
        self._subcategory = subcategory
        self._level = level
        # Round only applies to standings adjustments — show the field solely then.
        self._round_input: miru.TextInput | None = None
        if level == "standings_adjustment":
            self._round_input = miru.TextInput(
                label="Round number",
                placeholder="1",
                required=True,
            )
            self.add_item(self._round_input)
        self._description_input = miru.TextInput(
            label="Description",
            placeholder="Describe the infraction",
            style=hikari.TextInputStyle.PARAGRAPH,
            required=True,
        )
        self.add_item(self._description_input)

    async def callback(self, ctx: miru.ModalContext) -> None:
        discord_id = str(ctx.author.id)

        round_num = None
        if self._round_input is not None:
            try:
                round_num = (
                    int(self._round_input.value.strip()) - 1
                )  # Convert 1-indexed to 0-indexed
                if round_num < 0:
                    raise ValueError
            except ValueError:
                await ctx.respond(
                    "Invalid round number. Use a positive integer (1 = first round).",
                    flags=hikari.MessageFlag.EPHEMERAL,
                )
                return

        result = await self._api.create_sanction(
            discord_id=discord_id,
            user_uid=self._target_uid,
            tournament_uid=self._tournament_uid,
            level=self._level,
            category=self._category,
            description=self._description_input.value.strip(),
            subcategory=self._subcategory,
            round_number=round_num,
        )

        if result.ok:
            level_label = LEVELS.get(self._level, self._level)
            await ctx.respond(
                f"**{level_label}** issued to {self._target_display}.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
        else:
            await ctx.respond(
                f"Failed to issue sanction: {result.error}",
                flags=hikari.MessageFlag.EPHEMERAL,
            )


# --- /sanction command ---


class SanctionCommand(
    lightbulb.SlashCommand,
    name="sanction",
    description="Issue a sanction to a tournament player (organizer/judge)",
):
    player = lightbulb.user("player", "The player to sanction")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        store: TokenStore = ctx.client.d["store"]
        api: ArchonAPI = ctx.client.d["api"]

        tournament_uid = await resolve_tournament(ctx, store)
        if not tournament_uid:
            return

        discord_id = str(ctx.author.id)

        # Verify issuer is authenticated
        tokens = await store.get_tokens(discord_id)
        if not tokens:
            await ctx.respond(
                "You need to connect your Archon account first. "
                "Run `/register` in a tournament channel to get started.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        # Verify issuer account
        info = await fetch_userinfo(api, ctx, discord_id)
        if info is None:
            return

        # Find target player's Archon UID
        target_discord_id = str(self.player.id)
        target_tokens = await store.get_tokens(target_discord_id)
        if not target_tokens:
            await ctx.respond(
                f"{self.player.mention} hasn't connected their Archon account to the bot. "
                f"Issue the sanction via the webapp instead.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        target_uid = target_tokens["archon_uid"]
        target_display = self.player.username

        # Show category selection (step 1 of the flow)
        view = CategorySelectView(
            store, api, tournament_uid, target_uid, target_display
        )
        await ctx.respond(
            f"**Sanction for {target_display}**\nSelect infraction category:",
            components=view,
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        miru_client: miru.Client = ctx.client.d["miru"]
        miru_client.start_view(view)
