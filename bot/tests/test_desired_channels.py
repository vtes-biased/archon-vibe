"""Merge gate for the reconcile epic: the two PURE functions reconcile builds on.

``desired_channels`` is the single source of truth for which round/finals voice
channels must exist and who may connect; ``structure_signature`` is the cheap
guard that decides whether a tournament update is even structurally relevant.
Together they are the only unit-testable surface of the reconcile rewrite (the
bot has no CI — #156), so this file pins their contracts:

  - nothing is desired unless the tournament is ``Playing``;
  - a Playing round yields ordered ``R{n} - Table {m}`` channels, each scoped to
    its seated players ∪ the organizers;
  - finals (seating present, no result) collapse to a single ``Finals`` channel
    and SUPPRESS the prelim tables; a finished finals desires nothing;
  - the signature is stable across non-structural churn (a reported score) but
    flips on a SAME-SIZE seat swap (the principal-engineer amendment: a count-only
    key would miss it), a new round, and an organizer change.

Pure functions over plain dicts — no Discord, no REST, no fakes.

Run from bot/:
    DISCORD_BOT_TOKEN=x OAUTH_CLIENT_ID=x OAUTH_CLIENT_SECRET=x \
        uv run --with pytest --with pytest-asyncio pytest -q
"""

from __future__ import annotations

import os

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot.channel_manager import (  # noqa: E402
    DesiredChannel,
    desired_channels,
    structure_signature,
)

ORG = "org1"


def _table(*player_uids: str) -> dict:
    return {"seating": [{"player_uid": uid} for uid in player_uids]}


def _playing(rounds: list[list[dict]], *, organizers=(ORG,), finals=None) -> dict:
    obj = {
        "uid": "t1",
        "state": "Playing",
        "organizers_uids": list(organizers),
        "rounds": rounds,
    }
    if finals is not None:
        obj["finals"] = finals
    return obj


# ── desired_channels ────────────────────────────────────────────────────────


def test_empty_unless_playing() -> None:
    for state in ("Planned", "Registration", "Waiting", "Finished"):
        obj = _playing([[_table("p1", "p2")]])
        obj["state"] = state
        assert desired_channels(obj) == [], state


def test_round_tables_ordered_and_round_prefixed_with_organizers() -> None:
    obj = _playing(
        [
            [_table("a", "b")],  # round 1 (ignored — only latest round is live)
            [_table("p1", "p2"), _table("p3", "p4")],  # round 2
        ]
    )
    assert desired_channels(obj) == [
        DesiredChannel("R2 - Table 1", frozenset({"p1", "p2", ORG})),
        DesiredChannel("R2 - Table 2", frozenset({"p3", "p4", ORG})),
    ]


def test_no_rounds_yet_is_empty() -> None:
    assert desired_channels(_playing([])) == []


def test_finals_single_channel_suppresses_prelim_tables() -> None:
    # Prelim rounds still present in the object, but finals is seated → only Finals.
    obj = _playing(
        [[_table("p1", "p2"), _table("p3", "p4")]],
        finals={"seating": [{"player_uid": f} for f in ("p1", "p2", "p3")]},
    )
    assert desired_channels(obj) == [
        DesiredChannel("Finals", frozenset({"p1", "p2", "p3", ORG}))
    ]


def test_finished_finals_desires_nothing() -> None:
    obj = _playing(
        [[_table("p1", "p2")]],
        finals={
            "seating": [{"player_uid": "p1"}, {"player_uid": "p2"}],
            "result": {"winner": "p1"},
        },
    )
    assert desired_channels(obj) == []


def test_empty_seats_excluded_from_member_set() -> None:
    obj = _playing([[{"seating": [{"player_uid": "p1"}, {}, {"player_uid": ""}]}]])
    (ch,) = desired_channels(obj)
    assert ch.member_uids == frozenset({"p1", ORG})


# ── structure_signature ───────────────────────────────────────────────────────


def test_signature_stable_across_score_report() -> None:
    """A reported score re-broadcasts the tournament but changes no structure:
    the signature must match so reconcile is skipped."""
    before = _playing([[_table("p1", "p2", "p3"), _table("p4", "p5")]])
    after = _playing(
        [
            [
                {
                    "seating": [
                        {"player_uid": "p1", "result": {"vp": 2}},
                        {"player_uid": "p2"},
                        {"player_uid": "p3"},
                    ]
                },
                _table("p4", "p5"),
            ]
        ]
    )
    assert structure_signature(before) == structure_signature(after)


def test_signature_flips_on_same_size_seat_swap() -> None:
    """The principal-engineer amendment: two tables before AND after (same count),
    but a player swapped between them — a count-only key misses this; a
    membership-keyed signature must flip."""
    before = _playing([[_table("p1", "p2"), _table("p3", "p4")]])
    after = _playing([[_table("p1", "p4"), _table("p3", "p2")]])
    assert structure_signature(before) != structure_signature(after)


def test_signature_flips_on_new_round() -> None:
    r1 = _playing([[_table("p1", "p2")]])
    r2 = _playing([[_table("p1", "p2")], [_table("p1", "p2")]])  # same seats, R2
    assert structure_signature(r1) != structure_signature(r2)


def test_signature_flips_on_organizer_change() -> None:
    before = _playing([[_table("p1", "p2")]], organizers=("org1",))
    after = _playing([[_table("p1", "p2")]], organizers=("org1", "org2"))
    assert structure_signature(before) != structure_signature(after)


def test_signature_flips_on_prelim_to_finals() -> None:
    prelim = _playing([[_table("p1", "p2"), _table("p3", "p4")]])
    finals = _playing(
        [[_table("p1", "p2"), _table("p3", "p4")]],
        finals={"seating": [{"player_uid": "p1"}, {"player_uid": "p2"}]},
    )
    assert structure_signature(prelim) != structure_signature(finals)
