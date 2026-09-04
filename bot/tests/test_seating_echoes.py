"""Runs on EVERY tournament update, so a false positive pings every table on
every score report, sanction or check-in."""

from __future__ import annotations

import os

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot.sse_listener import compute_seating_echoes  # noqa: E402


def _seat(uid: str, vp: float = 0.0) -> dict:
    return {"player_uid": uid, "result": {"gw": 0, "vp": vp, "tp": 0}}


def _table(seats: list[dict], state: str = "In Progress") -> dict:
    return {"seating": seats, "state": state, "override": None}


def test_round_start_echoes_every_table_and_skips_the_zero_sentinel() -> None:
    prev = {"rounds": [], "state": "Waiting"}
    cur = {
        "rounds": [
            [
                _table([_seat("alice"), _seat("bob")]),
                _table([_seat("carol"), _seat("dave")]),
                _table([_seat("erin"), _seat("frank")]),
            ]
        ],
        "state": "Playing",
    }
    # Channel 0 is the sentinel of a failed create; table 3 keeps its index.
    assert compute_seating_echoes(prev, cur, [111, 0, 333]) == [(111, 0), (333, 2)]


def test_silent_on_score_report_and_noop_push() -> None:
    prev = {"rounds": [[_table([_seat("alice"), _seat("bob")])]]}
    scored = {"rounds": [[_table([_seat("alice", 3), _seat("bob", 1)], "Finished")]]}
    assert compute_seating_echoes(prev, scored, [111]) == []
    assert compute_seating_echoes(prev, prev, [111]) == []


def test_mid_round_update_echoes_only_the_changed_tables() -> None:
    prev = {
        "rounds": [
            [
                _table([_seat("alice"), _seat("bob")]),
                _table([_seat("carol"), _seat("dave")]),
            ]
        ]
    }
    cur = {
        "rounds": [
            [
                _table([_seat("alice"), _seat("bob")]),
                _table([_seat("dave"), _seat("carol")]),
                _table([_seat("erin"), _seat("frank")]),
            ]
        ]
    }
    assert compute_seating_echoes(prev, cur, [111, 222, 333]) == [(222, 1), (333, 2)]
