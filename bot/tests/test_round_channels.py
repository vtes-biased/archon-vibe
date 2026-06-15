"""Idempotency hinge for channel reconciliation (regression: SSE wedge fix).

``round_channels_by_name`` is the sole gate that lets reconcile tell which
volatile round voice channels already exist on Discord, keyed by the
deterministic name it diffs ``desired_channels`` against. If it miscounts the
set — admitting a #judges/text channel, a foreign-category channel, or missing a
legacy ``Table N`` — reconcile either re-creates duplicates or deletes a channel
it doesn't own.

This pins its contract:
  - only GUILD_VOICE channels under the given category are returned;
  - ``R{n} - Table {m}``, the legacy ``Table {m}``, and ``Finals`` are all
    recognized and keyed by their name;
  - the per-tournament ``judges`` voice channel, text channels, and any channel
    under a different category are excluded.

Real ``hikari.ChannelType`` enum members are used (the function compares against
them); the only fake is a duck-typed channel object exposing the same four
attributes the function reads off a real hikari channel.

Run from bot/:
    DISCORD_BOT_TOKEN=x OAUTH_CLIENT_ID=x OAUTH_CLIENT_SECRET=x \
        uv run --with pytest --with pytest-asyncio pytest -q
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import hikari

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot.channel_manager import round_channels_by_name  # noqa: E402

CATEGORY_ID = 100
OTHER_CATEGORY_ID = 999


@dataclass
class FakeChannel:
    """Duck-types the channel attrs the parser reads: id/name/type/parent_id."""

    id: int
    name: str
    type: hikari.ChannelType
    parent_id: int | None


def test_keys_round_finals_and_legacy_names_ignores_noise() -> None:
    channels = [
        FakeChannel(2, "R3 - Table 2", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(1, "R3 - Table 1", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(
            9, "Table 1", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID
        ),  # legacy
        FakeChannel(50, "Finals", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        # Noise that must NOT be admitted:
        FakeChannel(60, "judges", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(61, "lobby", hikari.ChannelType.GUILD_TEXT, CATEGORY_ID),
        # A Table channel under a DIFFERENT category (another tournament).
        FakeChannel(70, "Table 2", hikari.ChannelType.GUILD_VOICE, OTHER_CATEGORY_ID),
    ]
    result = round_channels_by_name(channels, CATEGORY_ID)

    assert set(result) == {"R3 - Table 1", "R3 - Table 2", "Table 1", "Finals"}
    assert result["R3 - Table 1"].id == 1
    assert result["Finals"].id == 50
    assert "judges" not in result and "lobby" not in result


def test_empty_when_no_round_channels_yet() -> None:
    """Before any round only judges/text exist → reconcile sees nothing to adopt."""
    channels = [
        FakeChannel(60, "judges", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(61, "lobby", hikari.ChannelType.GUILD_TEXT, CATEGORY_ID),
    ]
    assert round_channels_by_name(channels, CATEGORY_ID) == {}
