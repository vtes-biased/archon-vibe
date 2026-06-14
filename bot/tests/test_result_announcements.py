"""Score-report detection for table voice channels (open reporting = anti-cheat).

``compute_result_announcements`` is the gate that turns the firehose of whole-
tournament SSE pushes into "post this table's VPs to its channel". It runs on
EVERY tournament update (sanctions, check-ins, seating swaps, new rounds — all
re-broadcast the whole object), so a false positive spams every table on every
push. This pins the contract:

  - announce only when a table's seats are unchanged but a reported score moved;
  - stay silent on no-op pushes, on seating swaps (different players), and on
    round/finals context changes (those carry their own seating announcement);
  - only the table(s) that actually changed are announced, index-aligned to the
    live table channels; finals is handled like a one-table round.

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

from archon_bot.sse_listener import compute_result_announcements  # noqa: E402

PLAYERS = [
    {"user_uid": "alice", "display_name": "Alice"},
    {"user_uid": "bob", "display_name": "Bob"},
    {"user_uid": "carol", "display_name": "Carol"},
    {"user_uid": "dave", "display_name": "Dave"},
]


def _seat(uid: str, vp: float = 0.0, gw: int = 0, judge: str = "") -> dict:
    return {
        "player_uid": uid,
        "result": {"gw": gw, "vp": vp, "tp": 0},
        "judge_uid": judge,
    }


def _table(seats: list[dict], state: str = "In Progress") -> dict:
    return {"seating": seats, "state": state, "override": None}


def _tourney(round_tables: list[dict], finals: dict | None = None) -> dict:
    obj = {"rounds": [round_tables]} if round_tables else {"rounds": []}
    if finals is not None:
        obj["finals"] = finals
    return obj


def test_announces_only_the_table_whose_score_changed() -> None:
    t0 = _table([_seat("alice"), _seat("bob")])
    t1 = _table([_seat("carol"), _seat("dave")])
    prev = _tourney([t0, t1])
    # Alice reports 3 VP at table 0; table 1 untouched.
    cur = _tourney([_table([_seat("alice", 3), _seat("bob", 1)], "Finished"), t1])

    out = compute_result_announcements(prev, cur, table_chs=[111, 222], players=PLAYERS)

    assert len(out) == 1
    ch_id, msg = out[0]
    assert ch_id == 111  # table 0's channel only
    assert "Table 1" in msg and "Alice" in msg and "3 VP" in msg


def test_table_added_mid_round_keeps_original_alignment() -> None:
    """A table appended mid-round must not shift an original table's channel.

    prev has 1 table; cur has 2 (a table was added) AND table 0's score moved.
    Only table 0's channel (111) is announced; the fresh table 1 has no prior
    score to diff and is clamped out.
    """
    prev = _tourney([_table([_seat("alice"), _seat("bob")])])
    cur = _tourney(
        [
            _table([_seat("alice", 4), _seat("bob", 0)], "Finished"),
            _table([_seat("carol"), _seat("dave")]),  # newly added
        ]
    )

    out = compute_result_announcements(prev, cur, table_chs=[111, 222], players=PLAYERS)

    assert len(out) == 1
    assert out[0][0] == 111  # original table 0, not the new channel 222


def test_silent_on_noop_push() -> None:
    """A sanction/check-in re-broadcasts the whole object but moves no score."""
    same = _tourney([_table([_seat("alice", 2), _seat("bob", 1)], "Finished")])
    assert compute_result_announcements(same, same, [111], PLAYERS) == []


def test_silent_on_seating_swap() -> None:
    """Different players at the position is a swap (announced elsewhere), not a report."""
    prev = _tourney([_table([_seat("alice", 1), _seat("bob")])])
    cur = _tourney([_table([_seat("carol"), _seat("dave")])])
    assert compute_result_announcements(prev, cur, [111], PLAYERS) == []


def test_silent_on_new_round() -> None:
    """round1 → round2 is a context change (tag mismatch), not a score report."""
    prev = {"rounds": [[_table([_seat("alice", 3)])]]}
    cur = {"rounds": [[_table([_seat("alice", 3)])], [_table([_seat("alice")])]]}
    assert compute_result_announcements(prev, cur, [111], PLAYERS) == []


def test_finals_score_change_announced() -> None:
    finals_prev = {
        "seating": [_seat("alice"), _seat("bob")],
        "state": "In Progress",
        "override": None,
        "seed_order": ["alice", "bob"],
    }
    finals_cur = {
        "seating": [_seat("alice", 3), _seat("bob", 0)],
        "state": "Finished",
        "override": None,
        "seed_order": ["alice", "bob"],
    }
    prev = _tourney([_table([_seat("alice", 1)])], finals=finals_prev)
    cur = _tourney([_table([_seat("alice", 1)])], finals=finals_cur)

    out = compute_result_announcements(prev, cur, table_chs=[999], players=PLAYERS)

    assert len(out) == 1
    ch_id, msg = out[0]
    assert ch_id == 999
    assert "Finals" in msg and "Alice" in msg and "3 VP" in msg
