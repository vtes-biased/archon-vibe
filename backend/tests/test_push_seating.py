"""Seating-push payload mapping (#314): a wrong table/seat/round number sends a
player to the wrong table at a live event.

`build_seating_payloads` is pure (no DB/engine/network) and is the contract
`send_to_users` consumes. The regressions worth guarding are the index math and
the round-scoping, not the English copy:
  - 0-indexed table/seat/round → 1-based human numbering (four `+1` sites);
  - StartRound/SelfOrganizeRound enumerate ONLY the newly-appended round
    (`rounds[-1]`), so a self-organized single pod pushes one pod, not the field;
  - StartFinals reads `finals.seating` (not a preliminary round).
Asserts the structured routing (user_uid, url, tag) and the numbers carried in
the body; deliberately does not snapshot the wording.
"""

from datetime import UTC, datetime

from src.models import FinalsTable, Seat, Table, Tournament
from src.push_service import build_seating_payloads

NOW = datetime.now(UTC)


def _t(**kw) -> Tournament:
    return Tournament(uid="trn-1", modified=NOW, name="Cup", **kw)


def test_start_round_numbers_each_seat_by_table_and_seat() -> None:
    # Two tables of 5 in the newly-started round; numbering must be per-table,
    # 1-based, and the round number = len(rounds).
    t = _t(
        rounds=[
            [
                Table(seating=[Seat(player_uid=f"a{i}") for i in range(5)]),
                Table(seating=[Seat(player_uid=f"b{i}") for i in range(5)]),
            ]
        ]
    )
    payloads = dict(build_seating_payloads(t, "StartRound"))

    assert len(payloads) == 10  # every seated player, once
    # Table 1, seat 1 and table 2, seat 3 pin the per-table 1-based numbering.
    assert payloads["a0"]["url"] == "/tournaments/trn-1?table=1"
    assert payloads["b2"]["url"] == "/tournaments/trn-1?table=2"
    assert "Round 1" in payloads["a0"]["body"]
    assert "Table 2" in payloads["b2"]["body"] and "seat 3" in payloads["b2"]["body"]
    # tag is per-round so a re-seated round replaces, not stacks.
    assert payloads["a0"]["tag"] == "seating-trn-1-1"

    # A second round bumps the round number and the tag.
    t2 = _t(rounds=[*t.rounds, [Table(seating=[Seat(player_uid="c0")])]])
    p2 = dict(build_seating_payloads(t2, "StartRound"))
    assert "Round 2" in p2["c0"]["body"]
    assert p2["c0"]["tag"] == "seating-trn-1-2"


def test_self_organize_round_pushes_only_the_new_pod() -> None:
    # Two parallel pods exist, but only rounds[-1] is the just-seated one: a
    # player in an earlier round must NOT be paged. Enumerating all rounds
    # (instead of rounds[-1]) would page the whole field.
    t = _t(
        rounds=[
            [Table(seating=[Seat(player_uid="old1"), Seat(player_uid="old2")])],
            [Table(seating=[Seat(player_uid="new1"), Seat(player_uid="new2")])],
        ]
    )
    targets = build_seating_payloads(t, "SelfOrganizeRound")
    assert {uid for uid, _ in targets} == {"new1", "new2"}


def test_start_finals_reads_finals_seating_with_finals_url() -> None:
    t = _t(
        rounds=[[Table(seating=[Seat(player_uid="x")])]],  # a prelim round exists
        finals=FinalsTable(
            seating=[Seat(player_uid="f1"), Seat(player_uid="f2")],
            seed_order=["f1", "f2"],
        ),
    )
    payloads = dict(build_seating_payloads(t, "StartFinals"))

    assert set(payloads) == {"f1", "f2"}  # finalists only, not the prelim seat
    assert payloads["f2"]["url"] == "/tournaments/trn-1?finals=1"
    assert payloads["f2"]["tag"] == "seating-trn-1-finals"
    assert "seat 2" in payloads["f2"]["body"]


def test_no_rounds_and_missing_finals_yield_nothing() -> None:
    assert build_seating_payloads(_t(), "StartRound") == []
    assert build_seating_payloads(_t(), "StartFinals") == []
