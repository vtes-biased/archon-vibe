"""Seating-push mapping (#314): a wrong table/seat/round number sends a player to
the wrong table at a live event. Guards the index math and round-scoping in
`build_seating_specs`/`render_payload`, not the copy — asserts structured
routing/numbers, deliberately does not snapshot wording.
"""

from datetime import UTC, datetime

from src.models import (
    FinalsTable,
    Room,
    Seat,
    Table,
    TableState,
    Tournament,
    TournamentState,
)
from src.push_service import build_reseat_specs, build_seating_specs, render_payload

NOW = datetime.now(UTC)


def _t(**kw) -> Tournament:
    return Tournament(uid="trn-1", modified=NOW, name="Cup", **kw)


def test_start_round_numbers_each_seat_by_table_and_seat() -> None:
    t = _t(
        rounds=[
            [
                Table(seating=[Seat(player_uid=f"a{i}") for i in range(5)]),
                Table(seating=[Seat(player_uid=f"b{i}") for i in range(5)]),
            ]
        ]
    )
    specs = dict(build_seating_specs(t, "StartRound"))

    assert len(specs) == 10
    # Table 1 seat 1 and table 2 seat 3 pin the per-table 1-based numbering.
    assert specs["a0"]["url"] == "/tournaments/trn-1"
    assert (specs["a0"]["round"], specs["a0"]["table"], specs["a0"]["seat"]) == (
        1,
        1,
        1,
    )
    assert (specs["b2"]["table"], specs["b2"]["seat"]) == (2, 3)
    # tag is per-round so a re-seated round replaces, not stacks.
    assert specs["a0"]["tag"] == "seating-trn-1-1"
    body = render_payload(specs["b2"], "en")["body"]
    assert "Round 1" in body and "Table 2" in body and "seat 3" in body

    t2 = _t(
        rounds=[
            *t.rounds,
            [Table(seating=[Seat(player_uid=f"c{i}") for i in range(4)])],
        ]
    )
    s2 = dict(build_seating_specs(t2, "StartRound"))
    assert s2["c0"]["round"] == 2
    assert s2["c0"]["tag"] == "seating-trn-1-2"


def test_self_organize_round_pushes_only_the_new_pod() -> None:
    # Only rounds[-1] is the just-seated pod; a player in an earlier round must
    # NOT be paged, or enumerating all rounds would page the whole field.
    t = _t(
        rounds=[
            [Table(seating=[Seat(player_uid=f"old{i}") for i in range(4)])],
            [Table(seating=[Seat(player_uid=f"new{i}") for i in range(4)])],
        ]
    )
    targets = build_seating_specs(t, "SelfOrganizeRound")
    assert {uid for uid, _ in targets} == {f"new{i}" for i in range(4)}


def test_start_finals_reads_finals_seating_with_finals_url() -> None:
    t = _t(
        # a prelim round exists
        rounds=[[Table(seating=[Seat(player_uid=f"x{i}") for i in range(4)])]],
        finals=FinalsTable(
            seating=[Seat(player_uid=f"f{i}") for i in range(5)],
            seed_order=[f"f{i}" for i in range(5)],
        ),
    )
    specs = dict(build_seating_specs(t, "StartFinals"))

    assert set(specs) == {f"f{i}" for i in range(5)}  # finalists only, no prelim seat
    assert specs["f1"]["url"] == "/tournaments/trn-1"
    assert specs["f1"]["tag"] == "seating-trn-1-finals"
    assert specs["f1"]["seat"] == 2
    assert "seat 2" in render_payload(specs["f1"], "en")["body"]


def test_no_rounds_and_missing_finals_yield_nothing() -> None:
    assert build_seating_specs(_t(), "StartRound") == []
    assert build_seating_specs(_t(), "StartFinals") == []


def _round() -> list[Table]:
    return [
        Table(seating=[Seat(player_uid=f"a{i}") for i in range(4)]),
        Table(
            seating=[Seat(player_uid=f"b{i}") for i in range(4)],
            state=TableState.FINISHED,
        ),
    ]


def test_reseat_pushes_only_moved_players_on_live_tables() -> None:
    # A substitute replaces a1 (live table, gets paged); b0/b1 swap on a
    # FINISHED table (score correction, not paged).
    old = _t(state=TournamentState.PLAYING, rounds=[_round()])
    new = _t(state=TournamentState.PLAYING, rounds=[_round()])
    new.rounds[0][0].seating[1] = Seat(player_uid="sub")
    t2 = new.rounds[0][1].seating
    t2[0], t2[1] = t2[1], t2[0]

    specs = dict(build_reseat_specs(old, new))

    assert set(specs) == {"sub"}
    assert (specs["sub"]["round"], specs["sub"]["table"], specs["sub"]["seat"]) == (
        1,
        1,
        2,
    )
    # Same tag as the StartRound push → the stale assignment gets replaced.
    assert specs["sub"]["tag"] == "seating-trn-1-1"


def test_reseat_skips_non_playing_tournament() -> None:
    # Post-finish seating corrections are bookkeeping, not seat calls.
    old = _t(state=TournamentState.FINISHED, rounds=[_round()])
    new = _t(state=TournamentState.FINISHED, rounds=[_round()])
    new.rounds[0][0].seating[1] = Seat(player_uid="sub")
    assert build_reseat_specs(old, new) == []


def test_room_label_replaces_table_number_in_body() -> None:
    # With table_rooms configured the app/wall signs say "Main Hall 2", so the
    # push must too — not "Table 2".
    rooms = [Room(name="Main Hall", count=2)]
    old = _t(state=TournamentState.PLAYING, rounds=[_round()], table_rooms=rooms)
    new = _t(state=TournamentState.PLAYING, rounds=[_round()], table_rooms=rooms)
    new.rounds[0][1].state = TableState.IN_PROGRESS
    new.rounds[0][1].seating[0] = Seat(player_uid="sub")

    specs = dict(build_reseat_specs(old, new))
    body = render_payload(specs["sub"], "en")["body"]
    assert "Main Hall 2" in body and "Table" not in body


def test_render_payload_falls_back_to_en_for_unknown_locale() -> None:
    # An unsupported/garbage locale must render (in en), never KeyError.
    spec = build_seating_specs(
        _t(rounds=[[Table(seating=[Seat(player_uid=f"p{i}") for i in range(4)])]]),
        "StartRound",
    )[0][1]
    assert render_payload(spec, "zz")["body"] == render_payload(spec, "en")["body"]
