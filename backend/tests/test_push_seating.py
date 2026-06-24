"""Seating-push mapping (#314): a wrong table/seat/round number sends a player to
the wrong table at a live event.

`build_seating_specs` is pure (no DB/engine/network) and is the contract
`send_to_users` consumes; `render_payload` localizes a spec into the wire body. The
regressions worth guarding are the index math and the round-scoping, not the copy:
  - 0-indexed table/seat/round → 1-based human numbering (four `+1` sites);
  - StartRound/SelfOrganizeRound enumerate ONLY the newly-appended round
    (`rounds[-1]`), so a self-organized single pod pushes one pod, not the field;
  - StartFinals reads `finals.seating` (not a preliminary round);
  - render_payload formats those numbers into the body and falls back to `en`.
Asserts the structured routing/numbers; deliberately does not snapshot wording.
"""

from datetime import UTC, datetime

from src.models import FinalsTable, Seat, Table, Tournament
from src.push_service import build_seating_specs, render_payload

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
    specs = dict(build_seating_specs(t, "StartRound"))

    assert len(specs) == 10  # every seated player, once
    # Table 1 seat 1 and table 2 seat 3 pin the per-table 1-based numbering.
    assert specs["a0"]["url"] == "/tournaments/trn-1?table=1"
    assert (specs["a0"]["round"], specs["a0"]["table"], specs["a0"]["seat"]) == (1, 1, 1)
    assert (specs["b2"]["table"], specs["b2"]["seat"]) == (2, 3)
    # tag is per-round so a re-seated round replaces, not stacks.
    assert specs["a0"]["tag"] == "seating-trn-1-1"
    # render formats those numbers into the body.
    body = render_payload(specs["b2"], "en")["body"]
    assert "Round 1" in body and "Table 2" in body and "seat 3" in body

    # A second round bumps the round number and the tag.
    t2 = _t(rounds=[*t.rounds, [Table(seating=[Seat(player_uid="c0")])]])
    s2 = dict(build_seating_specs(t2, "StartRound"))
    assert s2["c0"]["round"] == 2
    assert s2["c0"]["tag"] == "seating-trn-1-2"


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
    targets = build_seating_specs(t, "SelfOrganizeRound")
    assert {uid for uid, _ in targets} == {"new1", "new2"}


def test_start_finals_reads_finals_seating_with_finals_url() -> None:
    t = _t(
        rounds=[[Table(seating=[Seat(player_uid="x")])]],  # a prelim round exists
        finals=FinalsTable(
            seating=[Seat(player_uid="f1"), Seat(player_uid="f2")],
            seed_order=["f1", "f2"],
        ),
    )
    specs = dict(build_seating_specs(t, "StartFinals"))

    assert set(specs) == {"f1", "f2"}  # finalists only, not the prelim seat
    assert specs["f2"]["url"] == "/tournaments/trn-1?finals=1"
    assert specs["f2"]["tag"] == "seating-trn-1-finals"
    assert specs["f2"]["seat"] == 2
    assert "seat 2" in render_payload(specs["f2"], "en")["body"]


def test_no_rounds_and_missing_finals_yield_nothing() -> None:
    assert build_seating_specs(_t(), "StartRound") == []
    assert build_seating_specs(_t(), "StartFinals") == []


def test_render_payload_falls_back_to_en_for_unknown_locale() -> None:
    # An unsupported/garbage locale must render (in en), never KeyError.
    spec = build_seating_specs(
        _t(rounds=[[Table(seating=[Seat(player_uid="p")])]]), "StartRound"
    )[0][1]
    assert render_payload(spec, "zz")["body"] == render_payload(spec, "en")["body"]
