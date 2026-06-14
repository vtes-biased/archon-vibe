"""Idempotency hinge for round-channel reconciliation (regression: SSE wedge fix).

``fetch_round_channel_ids`` is the sole gate that lets a (re)connect tell which
``Table N``/``Finals`` voice channels already exist, so it can recreate only the
missing ones. If it miscounts or misorders, the bot either re-creates DUPLICATE
table channels on every reconnect or fails to detect a genuinely-missing round —
both the user-visible failures the wedge/reconcile fix was meant to end.

This pins the return contract ``(ordered_table_ids, finals_id)``:
  - only GUILD_VOICE channels under the given category are considered;
  - ``Table N`` channels are returned ordered by N numerically (not lexically,
    so "Table 10" sorts after "Table 2");
  - the per-tournament ``judges`` voice channel and any text channel are ignored;
  - ``Finals`` is detected separately.

Real ``hikari.ChannelType`` enum members are used (the function compares against
them); the only injected fake is the single ``fetch_guild_channels`` REST call,
which returns duck-typed channel objects — the same four attributes the function
reads off real hikari channels.

Run from bot/:
    DISCORD_BOT_TOKEN=x OAUTH_CLIENT_ID=x OAUTH_CLIENT_SECRET=x \
        uv run --with pytest --with pytest-asyncio pytest -q
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import hikari
import pytest

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot.channel_manager import fetch_round_channel_ids  # noqa: E402

CATEGORY_ID = 100
OTHER_CATEGORY_ID = 999


@dataclass
class FakeChannel:
    """Duck-types the hikari channel attrs the parser reads: id/name/type/parent_id."""

    id: int
    name: str
    type: hikari.ChannelType
    parent_id: int | None


class FakeRest:
    def __init__(self, channels: list[FakeChannel]) -> None:
        self._channels = channels

    async def fetch_guild_channels(self, guild_id: int) -> list[FakeChannel]:
        return self._channels


class FakeBot:
    def __init__(self, channels: list[FakeChannel]) -> None:
        self.rest = FakeRest(channels)


@pytest.mark.asyncio
async def test_orders_tables_numerically_finds_finals_ignores_noise() -> None:
    channels = [
        # Out of order + double-digit to catch lexical sorting ("Table 10" < "Table 2").
        FakeChannel(2, "Table 2", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(10, "Table 10", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(1, "Table 1", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(50, "Finals", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        # Noise that must NOT be counted as tables:
        FakeChannel(60, "judges", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(61, "lobby", hikari.ChannelType.GUILD_TEXT, CATEGORY_ID),
        # A Table channel under a DIFFERENT category (another tournament).
        FakeChannel(70, "Table 1", hikari.ChannelType.GUILD_VOICE, OTHER_CATEGORY_ID),
    ]
    tables, finals_id = await fetch_round_channel_ids(
        FakeBot(channels), guild_id=1, category_id=CATEGORY_ID
    )

    assert tables == [1, 2, 10]  # numeric order, foreign-category Table 1 excluded
    assert finals_id == 50


@pytest.mark.asyncio
async def test_round_prefixed_table_names_parsed_by_table_number() -> None:
    """New "R{n} - Table {m}" names parse by table number (round prefix ignored),
    so reconcile adopts and round-close cleanup deletes them just like the legacy
    "Table {m}" form. A stray legacy name is matched too (transition coexistence).
    """
    channels = [
        FakeChannel(2, "R3 - Table 2", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(10, "R3 - Table 10", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(1, "R3 - Table 1", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(50, "Finals", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(60, "judges", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
    ]
    tables, finals_id = await fetch_round_channel_ids(
        FakeBot(channels), guild_id=1, category_id=CATEGORY_ID
    )
    assert tables == [1, 2, 10]  # numeric by table number, not lexical
    assert finals_id == 50


@pytest.mark.asyncio
async def test_empty_when_no_round_channels_yet() -> None:
    """Before any round: only judges/text exist → caller treats round as fresh."""
    channels = [
        FakeChannel(60, "judges", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(61, "lobby", hikari.ChannelType.GUILD_TEXT, CATEGORY_ID),
    ]
    tables, finals_id = await fetch_round_channel_ids(
        FakeBot(channels), guild_id=1, category_id=CATEGORY_ID
    )
    assert tables == []
    assert finals_id is None
