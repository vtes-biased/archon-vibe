"""Judge commands: /sanction."""

import logging

import hikari
import lightbulb
import miru

from .. import config
from ..archon_api import ArchonAPI
from ..token_store import TokenStore
from ..tournament_resolver import resolve_tournament

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
        options=[
            miru.SelectOption(label=v, value=k) for k, v in CATEGORIES.items()
        ],
    )
    async def category_select(self, ctx: miru.ViewContext, select: miru.TextSelect) -> None:
        category = select.values[0]

        # Build subcategory options for the modal
        subs = SUBCATEGORIES.get(category, {})
        sub_options = [miru.SelectOption(label=v, value=k) for k, v in subs.items()]

        view = SubcategorySelectView(
            self._store, self._api, self._tournament_uid,
            self._target_uid, self._target_display,
            category, sub_options,
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
        modal = SanctionDetailsModal(
            view._store, view._api, view._tournament_uid,
            view._target_uid, view._target_display,
            view._category, subcategory, baseline,
        )
        await ctx.respond_with_modal(modal)
        view.stop()


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
        modal = SanctionDetailsModal(
            self._store, self._api, self._tournament_uid,
            self._target_uid, self._target_display,
            self._category, None, "",
        )
        await ctx.respond_with_modal(modal)
        self.stop()


# --- Step 3: Details modal (level, round, description) ---

class SanctionDetailsModal(miru.Modal, title="Issue Sanction"):
    level = miru.TextInput(
        label="Level (caution / warning / standings_adjustment / disqualification)",
        placeholder="warning",
        required=True,
    )
    round_number = miru.TextInput(
        label="Round number (required for standings_adjustment)",
        placeholder="1",
        required=False,
    )
    description = miru.TextInput(
        label="Description",
        placeholder="Describe the infraction",
        style=hikari.TextInputStyle.PARAGRAPH,
        required=True,
    )

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
        super().__init__()
        self._store = store
        self._api = api
        self._tournament_uid = tournament_uid
        self._target_uid = target_uid
        self._target_display = target_display
        self._category = category
        self._subcategory = subcategory
        # Pre-fill level with baseline penalty
        if baseline:
            self.level.value = baseline

    async def callback(self, ctx: miru.ModalContext) -> None:
        discord_id = str(ctx.author.id)
        level_val = self.level.value.strip().lower()

        if level_val not in LEVELS:
            await ctx.respond(
                f"Invalid level: `{level_val}`. Use: caution, warning, standings_adjustment, or disqualification.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        round_num = None
        if self.round_number.value and self.round_number.value.strip():
            try:
                round_num = int(self.round_number.value.strip()) - 1  # Convert 1-indexed to 0-indexed
                if round_num < 0:
                    raise ValueError
            except ValueError:
                await ctx.respond(
                    "Invalid round number. Use a positive integer (1 = first round).",
                    flags=hikari.MessageFlag.EPHEMERAL,
                )
                return

        if level_val == "standings_adjustment" and round_num is None:
            await ctx.respond(
                "Standings adjustment requires a round number.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        result = await self._api.create_sanction(
            discord_id=discord_id,
            user_uid=self._target_uid,
            tournament_uid=self._tournament_uid,
            level=level_val,
            category=self._category,
            description=self.description.value.strip(),
            subcategory=self._subcategory,
            round_number=round_num,
        )

        if result.ok:
            level_label = LEVELS.get(level_val, level_val)
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
        info = await api.get_userinfo(discord_id)
        if not info.ok:
            await ctx.respond(
                f"Could not verify your account: {info.error}",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
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
        view = CategorySelectView(store, api, tournament_uid, target_uid, target_display)
        resp = await ctx.respond(
            f"**Sanction for {target_display}**\nSelect infraction category:",
            components=view,
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        miru_client: miru.Client = ctx.client.d["miru"]
        miru_client.start_view(view)
