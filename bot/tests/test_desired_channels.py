"""``structure_signature`` must flip on a SAME-SIZE seat swap — a count-only
key would miss it — as well as a new round or an organizer change."""

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
T1 = ("p1", "p2", "p3", "p4")
T2 = ("p5", "p6", "p7", "p8")
FINALISTS = ("p1", "p2", "p5", "p6", "p7")


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


def test_empty_unless_playing() -> None:
    for state in ("Planned", "Registration", "Waiting", "Finished"):
        obj = _playing([[_table(*T1)]])
        obj["state"] = state
        assert desired_channels(obj) == [], state


def test_round_tables_ordered_and_round_prefixed_with_organizers() -> None:
    obj = _playing(
        [
            [_table(*T2)],  # round 1 (ignored — only latest round is live)
            [_table(*T1), _table(*T2)],  # round 2
        ]
    )
    assert desired_channels(obj) == [
        DesiredChannel("R2 - Table 1", frozenset({*T1, ORG})),
        DesiredChannel("R2 - Table 2", frozenset({*T2, ORG})),
    ]


def test_no_rounds_yet_is_empty() -> None:
    assert desired_channels(_playing([])) == []


def test_finals_single_channel_suppresses_prelim_tables() -> None:
    obj = _playing([[_table(*T1), _table(*T2)]], finals=_table(*FINALISTS))
    assert desired_channels(obj) == [
        DesiredChannel("Finals", frozenset({*FINALISTS, ORG}))
    ]


def test_reported_finals_keep_their_channel_until_the_tournament_finishes() -> None:
    finals = {**_table(*FINALISTS), "state": "Finished", "override": None}
    obj = _playing([[_table(*T1), _table(*T2)]], finals=finals)
    assert [dc.name for dc in desired_channels(obj)] == ["Finals"]
    obj["state"] = "Finished"
    assert desired_channels(obj) == []


def test_empty_seats_excluded_from_member_set() -> None:
    obj = _playing(
        [[{"seating": [*_table("p1", "p2", "p3")["seating"], {"player_uid": ""}]}]]
    )
    (ch,) = desired_channels(obj)
    assert ch.member_uids == frozenset({"p1", "p2", "p3", ORG})


def test_signature_stable_across_score_report() -> None:
    """A reported score re-broadcasts the tournament but changes no structure:
    the signature must match so reconcile is skipped."""
    before = _playing([[_table(*T1), _table(*T2)]])
    scored = _table(*T1)
    scored["seating"][0]["result"] = {"vp": 2}
    after = _playing([[scored, _table(*T2)]])
    assert structure_signature(before) == structure_signature(after)


def test_signature_flips_on_same_size_seat_swap() -> None:
    """Same table count before and after, but a player swapped between them —
    a count-only key would miss this."""
    before = _playing([[_table(*T1), _table(*T2)]])
    after = _playing([[_table("p1", "p2", "p3", "p8"), _table("p5", "p6", "p7", "p4")]])
    assert structure_signature(before) != structure_signature(after)


def test_signature_flips_on_new_round() -> None:
    r1 = _playing([[_table(*T1)]])
    r2 = _playing([[_table(*T1)], [_table(*T1)]])  # same seats, R2
    assert structure_signature(r1) != structure_signature(r2)


def test_signature_flips_on_organizer_change() -> None:
    before = _playing([[_table(*T1)]], organizers=("org1",))
    after = _playing([[_table(*T1)]], organizers=("org1", "org2"))
    assert structure_signature(before) != structure_signature(after)


def test_signature_flips_on_prelim_to_finals() -> None:
    prelim = _playing([[_table(*T1), _table(*T2)]])
    finals = _playing([[_table(*T1), _table(*T2)]], finals=_table(*FINALISTS))
    assert structure_signature(prelim) != structure_signature(finals)
