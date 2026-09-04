"""A finalist is still seated in the last preliminary round, so a lookup that
scans ``rounds`` first sends a finals ``/report`` to the closed prelim table —
and the engine accepts that score."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot import sse_listener  # noqa: E402
from archon_bot.sse_listener import find_player_table  # noqa: E402

GUILD = "1"
TUID = "tour-1"
KEY = f"{GUILD}:{TUID}"


def _table(*uids: str) -> dict:
    return {"seating": [{"player_uid": u} for u in uids]}


@pytest.fixture(autouse=True)
def _clean_state():
    sse_listener._last_tournament.pop(KEY, None)
    yield
    sse_listener._last_tournament.pop(KEY, None)


def test_finalist_reports_to_the_finals_table_not_the_last_prelim() -> None:
    sse_listener._last_tournament[KEY] = {
        "state": "Playing",
        "rounds": [
            [_table("p1", "p2", "p3", "p4"), _table("p5", "p6", "p7", "p8")],
            [_table("p1", "p5", "p3", "p7"), _table("p2", "p6", "p4", "p8")],
        ],
        "finals": _table("p1", "p2", "p5", "p6", "p7"),
    }
    assert find_player_table(GUILD, TUID, "p1") == (2, 0)
    assert find_player_table(GUILD, TUID, "p3") is None


def test_prelim_lookup_is_the_last_round() -> None:
    sse_listener._last_tournament[KEY] = {
        "state": "Playing",
        "rounds": [
            [_table("p1", "p2", "p3", "p4"), _table("p5", "p6", "p7", "p8")],
            [_table("p5", "p2", "p7", "p4"), _table("p1", "p6", "p3", "p8")],
        ],
    }
    assert find_player_table(GUILD, TUID, "p1") == (1, 1)
