"""Sanction → table-channel routing.

``sanction_table_channel`` decides whether a sanction posts into a table voice
channel or falls back to the lobby. ``_table_channels`` always maps the LIVE
context's channels, so a past-round back-correction (only standings adjustments
carry ``round_number``) must NOT resolve its table index against the live round
— a round-1 adjustment issued during round 3 would land among strangers.

Pure function, no bot/REST — only env vars to satisfy the config import.

Run from bot/:
    DISCORD_BOT_TOKEN=x OAUTH_CLIENT_ID=x OAUTH_CLIENT_SECRET=x \
        uv run --with pytest pytest -q
"""

from __future__ import annotations

import os

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot.sse_listener import sanction_table_channel  # noqa: E402


def _table(*uids: str) -> dict:
    return {"seating": [{"player_uid": u} for u in uids]}


def _tournament(rounds: list[list[dict]], finals: dict | None = None) -> dict:
    return {"state": "Playing", "rounds": rounds, "finals": finals}


ROUNDS = [
    [_table("p1", "p2"), _table("p3", "p4")],  # round 1
    [_table("p3", "p1"), _table("p2", "p4")],  # round 2
    [_table("p4", "p2"), _table("p1", "p3")],  # round 3 (live)
]
CHANNELS = [301, 302]


def test_routes_only_when_sanction_round_is_live():
    t = _tournament(ROUNDS)
    # Live-round sanction → the player's table channel in that round.
    assert sanction_table_channel(t, 2, "p1", CHANNELS) == 302
    # Past-round back-correction → lobby, even though p1 sat at (same-index)
    # table 1 in round 1: the live table 1 seats strangers.
    assert sanction_table_channel(t, 0, "p1", CHANNELS) is None
    # During finals the prelim channels are gone; a prelim-round sanction
    # must not land in the finals channel.
    tf = _tournament(ROUNDS, finals={"seating": [{"player_uid": "p1"}]})
    assert sanction_table_channel(tf, 2, "p1", [401]) is None
    # Player not seated in the live round → lobby.
    assert sanction_table_channel(t, 2, "p5", CHANNELS) is None
