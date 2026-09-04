"""A finalist is still seated in the last preliminary round, so a lookup that
scans ``rounds`` first sends a finals ``/report`` to the closed prelim table —
and the engine accepts that score."""

from __future__ import annotations

import os

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot import sse_listener  # noqa: E402
from archon_bot.sse_listener import find_player_table  # noqa: E402

GUILD = "1"
TUID = "tour-1"


def _seated(*uids: str) -> dict:
    return {"seating": [{"player_uid": u} for u in uids]}


def _snapshot(obj: dict):
    sse_listener._last_tournament[f"{GUILD}:{TUID}"] = obj


def test_finalist_reports_to_the_finals_table_not_the_last_prelim() -> None:
    _snapshot(
        {
            "state": "Playing",
            "rounds": [[_seated("p1", "p2")], [_seated("p1", "p3")]],
            "finals": _seated("p1", "p3", "p4"),
        }
    )
    assert find_player_table(GUILD, TUID, "p1") == (2, 0)
    assert find_player_table(GUILD, TUID, "p2") is None


def test_prelim_lookup_is_the_last_round() -> None:
    _snapshot(
        {
            "state": "Playing",
            "rounds": [[_seated("p1", "p2")], [_seated("p3"), _seated("p1")]],
        }
    )
    assert find_player_table(GUILD, TUID, "p1") == (1, 1)
