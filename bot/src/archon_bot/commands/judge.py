import logging
from dataclasses import dataclass, replace

import hikari
import lightbulb
import miru

from ..archon_api import ArchonAPI
from ..command_mentions import command_mention
from ..token_store import TokenStore
from ..tournament_resolver import resolve_tournament
from ._common import fetch_userinfo

logger = logging.getLogger(__name__)

# Owned by the Rust engine, never hand-copied here.
_TABLES: dict | None = None


async def get_sanction_tables(api: ArchonAPI) -> dict:
    """Cached penalty tables: categories, subcategories (by category), levels
    (all key → English label) and baselines (subcategory key → level key)."""
    global _TABLES
    if _TABLES is None:
        ref = await api.get_sanction_reference()
        _TABLES = {
            "categories": {c["key"]: c["label"] for c in ref["categories"]},
            "subcategories": {
                c["key"]: {s["key"]: s["label"] for s in c["subcategories"]}
                for c in ref["categories"]
            },
            "levels": {lv["key"]: lv["label"] for lv in ref["levels"]},
            "baselines": {
                s["key"]: s["baseline"]
                for c in ref["categories"]
                for s in c["subcategories"]
            },
        }
    return _TABLES


@dataclass(frozen=True)
class _Draft:
    """The sanction under construction, carried from step to step."""

    api: ArchonAPI
    tournament_uid: str
    target_uid: str
    target_display: str
    tables: dict
    category: str = ""
    subcategory: str | None = None


class _CategorySelect(miru.TextSelect):
    def __init__(self, categories: dict[str, str]) -> None:
        super().__init__(
            placeholder="Select infraction category...",
            options=[
                miru.SelectOption(label=v, value=k) for k, v in categories.items()
            ],
        )

    async def callback(self, ctx: miru.ViewContext) -> None:
        view: CategorySelectView = self.view  # type: ignore
        draft = replace(view.draft, category=self.values[0])
        next_view = SubcategorySelectView(draft)
        await ctx.edit_response(
            f"**Sanction for {draft.target_display}**\n"
            f"Category: {draft.tables['categories'][draft.category]}\n"
            f"Select subcategory:",
            components=next_view,
        )
        ctx.client.start_view(next_view)
        view.stop()


class CategorySelectView(miru.View):
    def __init__(self, draft: _Draft) -> None:
        super().__init__(timeout=300)
        self.draft = draft
        self.add_item(_CategorySelect(draft.tables["categories"]))


class _SubcategorySelect(miru.TextSelect):
    def __init__(self, options: list) -> None:
        super().__init__(placeholder="Select subcategory...", options=options)

    async def callback(self, ctx: miru.ViewContext) -> None:
        view: SubcategorySelectView = self.view  # type: ignore
        subcategory = self.values[0]
        baseline = view.draft.tables["baselines"].get(subcategory, "")
        await _open_level_select(ctx, view, subcategory, baseline)


class SubcategorySelectView(miru.View):
    def __init__(self, draft: _Draft) -> None:
        super().__init__(timeout=300)
        self.draft = draft
        subs = draft.tables["subcategories"].get(draft.category, {})
        options = [miru.SelectOption(label=v, value=k) for k, v in subs.items()] or [
            miru.SelectOption(label="(none)", value="none")
        ]
        self.add_item(_SubcategorySelect(options))

    @miru.button(label="Skip subcategory", style=hikari.ButtonStyle.SECONDARY, row=1)
    async def skip_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        await _open_level_select(ctx, self, None, "")


class _LevelSelect(miru.TextSelect):
    def __init__(self, baseline: str, levels: dict[str, str]) -> None:
        super().__init__(
            placeholder="Select penalty level...",
            options=[
                miru.SelectOption(
                    label=label, value=value, is_default=value == baseline
                )
                for value, label in levels.items()
            ],
        )

    async def callback(self, ctx: miru.ViewContext) -> None:
        view: LevelSelectView = self.view  # type: ignore
        level = self.values[0]
        await ctx.respond_with_modal(SanctionDetailsModal(view.draft, level))
        view.stop()


class LevelSelectView(miru.View):
    def __init__(self, draft: _Draft, baseline: str) -> None:
        super().__init__(timeout=300)
        self.draft = draft
        self.add_item(_LevelSelect(baseline, draft.tables["levels"]))


async def _open_level_select(
    ctx: miru.ViewContext,
    prev: SubcategorySelectView,
    subcategory: str | None,
    baseline: str,
) -> None:
    draft = replace(prev.draft, subcategory=subcategory)
    level_view = LevelSelectView(draft, baseline)
    await ctx.edit_response(
        f"**Sanction for {draft.target_display}**\nSelect penalty level:",
        components=level_view,
    )
    ctx.client.start_view(level_view)
    prev.stop()


class SanctionDetailsModal(miru.Modal, title="Issue Sanction"):
    def __init__(self, draft: _Draft, level: str) -> None:
        super().__init__()
        self._draft = draft
        self._level = level
        self._round_input: miru.TextInput | None = None
        if level == "standings_adjustment":
            self._round_input = miru.TextInput(
                label="Round number", placeholder="1", required=True
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
        draft = self._draft
        round_num = None
        if self._round_input is not None:
            try:
                round_num = int(self._round_input.value.strip()) - 1
                if round_num < 0:
                    raise ValueError
            except ValueError:
                await ctx.respond(
                    "Invalid round number. Use a positive integer (1 = first round).",
                    flags=hikari.MessageFlag.EPHEMERAL,
                )
                return

        result = await draft.api.create_sanction(
            discord_id=str(ctx.user.id),
            user_uid=draft.target_uid,
            tournament_uid=draft.tournament_uid,
            level=self._level,
            category=draft.category,
            description=self._description_input.value.strip(),
            subcategory=draft.subcategory,
            round_number=round_num,
        )
        level_label = draft.tables["levels"].get(self._level, self._level)
        if result.ok:
            await ctx.respond(
                f"**{level_label}** issued to {draft.target_display}.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
        else:
            await ctx.respond(
                f"Failed to issue sanction: {result.error}",
                flags=hikari.MessageFlag.EPHEMERAL,
            )


class SanctionCommand(
    lightbulb.SlashCommand,
    name="sanction",
    description="Issue a sanction to a tournament player (organizer/judge)",
):
    player = lightbulb.user("player", "The player to sanction")

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

        discord_id = str(ctx.user.id)

        tokens = await store.get_tokens(discord_id, tournament_uid)
        if not tokens:
            await ctx.respond(
                "You need to connect your Archon account to this event first. "
                f"Run {command_mention('register')} in a tournament channel to get started.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        info = await fetch_userinfo(api, ctx, discord_id, tournament_uid)
        if info is None:
            return

        target_discord_id = str(self.player.id)
        target_tokens = await store.get_tokens(target_discord_id, tournament_uid)
        if not target_tokens:
            await ctx.respond(
                f"{self.player.mention} hasn't connected their Archon account to this event. "
                f"Issue the sanction via the webapp instead.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        try:
            tables = await get_sanction_tables(api)
        except Exception:
            logger.exception("Failed to fetch the sanction reference")
            await ctx.respond(
                "Could not load the sanction reference from the backend. "
                "Try again in a moment.",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        draft = _Draft(
            api=api,
            tournament_uid=tournament_uid,
            target_uid=target_tokens["archon_uid"],
            target_display=self.player.username,
            tables=tables,
        )
        view = CategorySelectView(draft)
        await ctx.respond(
            f"**Sanction for {draft.target_display}**\nSelect infraction category:",
            components=view,
            flags=hikari.MessageFlag.EPHEMERAL,
        )
        miru_client.start_view(view)
