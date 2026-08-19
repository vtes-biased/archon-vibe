"""VEKN push archondata format generation: getting the format wrong means
silent data corruption on the VEKN registry. Tests verify field ordering and
edge cases (finals GW subtraction, missing users, etc.).
"""

import json
from datetime import UTC, datetime

import msgspec
from archon_engine import PyEngine
from src.models import (
    Tournament,
    TournamentFormat,
    TournamentRank,
    User,
)
from src.vekn_push import generate_archondata, tournament_to_vekn_type

_engine = PyEngine()


def _user(uid: str, name: str, vekn_id: str, city: str = "") -> User:
    return User(
        uid=uid,
        modified=datetime(2025, 1, 1, tzinfo=UTC),
        name=name,
        vekn_id=vekn_id,
        city=city,
    )


def _sweep(*uids: str) -> dict:
    """A finished table where the first seat ousts the whole pod. Seats sit in
    predator-prey order and a sweep is a reachable oust order, so the vector
    sums to the table size the way a real game does."""
    vps = [float(len(uids))] + [0.0] * (len(uids) - 1)
    return {
        "seating": [
            {"player_uid": u, "result": {"gw": 0, "vp": v, "tp": 0}}
            for u, v in zip(uids, vps, strict=True)
        ],
        "state": "Finished",
    }


def _finished_tournament(
    *,
    rounds: list | None = None,
    finals: dict | None = None,
    winner: str = "",
    rank: TournamentRank = TournamentRank.BASIC,
    fmt: TournamentFormat = TournamentFormat.Standard,
    proxies: set[str] | None = None,
) -> Tournament:
    """Finish a tournament through the shipped engine, so the standings sheet is
    the engine's own — a hand-typed one drifts from what a real table produces."""
    rounds = rounds or []
    seated: list[str] = []
    for rnd in rounds:
        for table in rnd:
            for seat in table["seating"]:
                if seat["player_uid"] not in seated:
                    seated.append(seat["player_uid"])
    proxies = proxies or set()

    tournament = {
        "uid": "t-001",
        "modified": "2025-06-01T00:00:00Z",
        "name": "Test Tournament",
        "format": fmt.value,
        "rank": rank.value,
        "state": "Playing",
        "start": "2025-06-01T00:00:00Z",
        "organizers_uids": ["org-1"],
        "players": [
            {
                "user_uid": u,
                "state": "Playing",
                "payment_status": "Pending",
                "toss": 0,
                "non_competing": u in proxies,
            }
            for u in seated
        ],
        "rounds": rounds,
        "finals": finals,
        "winner": winner,
    }
    actor = {"uid": "org-1", "roles": ["Prince"], "is_organizer": True}
    result = _engine.process_tournament_event(
        json.dumps(tournament),
        json.dumps({"type": "FinishTournament"}),
        json.dumps(actor),
        "[]",
        "[]",
    )
    return msgspec.convert(json.loads(result)["tournament"], Tournament)


def _finals(uids: list[str], vps: list[float]) -> dict:
    return {
        "seating": [
            {"player_uid": u, "result": {"gw": 0, "vp": v, "tp": 0}}
            for u, v in zip(uids, vps, strict=True)
        ],
        "seed_order": uids,
        "state": "Finished",
    }


def test_vekn_type_standard_basic():
    assert tournament_to_vekn_type(TournamentFormat.Standard, TournamentRank.BASIC) == 2


def test_vekn_type_standard_nc():
    assert tournament_to_vekn_type(TournamentFormat.Standard, TournamentRank.NC) == 8


def test_vekn_type_standard_cc():
    assert tournament_to_vekn_type(TournamentFormat.Standard, TournamentRank.CC) == 6


def test_vekn_type_limited():
    assert tournament_to_vekn_type(TournamentFormat.Limited, TournamentRank.BASIC) == 3


def test_vekn_type_limited_championships():
    """Filed as plain Limited, a championship's finalists lose the rank bonus."""
    assert tournament_to_vekn_type(TournamentFormat.Limited, TournamentRank.NC) == 13
    assert tournament_to_vekn_type(TournamentFormat.Limited, TournamentRank.CC) == 14


def test_vekn_type_v5():
    assert tournament_to_vekn_type(TournamentFormat.V5, TournamentRank.BASIC) == 16


def test_vekn_type_unmappable_is_none():
    """No V5 championship type upstream, and no silent Standard fallback."""
    assert tournament_to_vekn_type(TournamentFormat.V5, TournamentRank.NC) is None
    assert tournament_to_vekn_type(TournamentFormat.V5, TournamentRank.CC) is None


def _pod() -> dict[str, User]:
    return {
        "u1": _user("u1", "Alice Smith", "1000001", city="Paris"),
        "u2": _user("u2", "Bob Jones", "1000002", city="Lyon"),
        "u3": _user("u3", "Cara Doe", "1000003"),
        "u4": _user("u4", "Dan Roe", "1000004"),
        "u5": _user("u5", "Eve Poe", "1000005"),
    }


def test_archondata_basic_format():
    """The wire format: nrounds¤ then rank§first§last§city§vekn§gw§vp§vpf§tp§toss§rtp§"""
    t = _finished_tournament(
        rounds=[
            [_sweep("u1", "u2", "u3", "u4", "u5")],
            [_sweep("u2", "u1", "u3", "u4", "u5")],
        ]
    )
    result = generate_archondata(t, _pod())

    assert result.startswith("2¤")  # len(rounds) + (1 if finals else 0)

    parts = result[2:].split("§")
    assert parts[0] == "1"  # rank
    assert parts[1] == "Alice"  # first name
    assert parts[2] == "Smith"  # last name
    assert parts[3] == "Paris"  # city
    assert parts[4] == "1000001"  # vekn_id
    assert parts[5] == "1"  # gw, as an int
    assert parts[6] == "5.0"  # vp
    assert parts[7] == "0.0"  # vpf — no finals
    assert parts[8] == "90"  # tp
    assert parts[9] == "0"  # toss
    assert parts[10].isdigit()  # rtp, the engine's rating points

    # Bob is rank 2, and each player block is 11 fields.
    assert parts[11] == "2"
    assert parts[12] == "Bob"
    assert parts[13] == "Jones"
    assert parts[14] == "Lyon"
    assert parts[15] == "1000002"
    assert len(parts) == 5 * 11 + 1  # five players, eleven fields each
    assert parts[-1] == ""  # trailing empty after the last player


def test_archondata_nrounds_includes_finals():
    t = _finished_tournament(
        rounds=[
            [_sweep("u1", "u2", "u3", "u4", "u5")],
            [_sweep("u1", "u2", "u3", "u4", "u5")],
        ],
        finals=_finals(["u1", "u2", "u3", "u4", "u5"], [3.0, 1.5, 0.5, 0.0, 0.0]),
        winner="u1",
    )
    assert generate_archondata(t, _pod()).startswith("3¤")


def test_archondata_gw_is_prelim_only_and_vpf_carries_the_final():
    """The pushed GW must be the standings' prelim-only figure — vekn.net adds the
    finals win itself, and a finalist's finals VP travels in vpf, not vp."""
    t = _finished_tournament(
        rounds=[
            [_sweep("u1", "u2", "u3", "u4", "u5")],
            [_sweep("u1", "u2", "u3", "u4", "u5")],
        ],
        finals=_finals(["u1", "u2", "u3", "u4", "u5"], [3.0, 1.5, 0.5, 0.0, 0.0]),
        winner="u1",
    )
    parts = generate_archondata(t, _pod()).split("¤", 1)[1].split("§")

    assert parts[5] == "2"  # winner: two prelim GW, no +1 for the final
    assert parts[6] == "10.0"  # prelim VP only
    assert parts[7] == "3.0"  # her finals VP

    assert parts[11 + 5] == "0"  # runner-up: GW untouched, never subtracted
    assert parts[11 + 7] == "1.5"


def test_archondata_skips_missing_users():
    """A standing whose user we can't resolve is dropped, not pushed as a blank."""
    t = _finished_tournament(rounds=[[_sweep("u1", "u2", "u3", "u4", "u5")]])
    result = generate_archondata(t, {"u1": _pod()["u1"]})

    assert "1000001" in result
    assert "1000002" not in result


def test_archondata_skips_non_competing():
    """A proxy is a non-competing official stood in — never pushed to VEKN as a
    competitor, even though their seat scored real (non-zeroed) VPs."""
    t = _finished_tournament(
        rounds=[[_sweep("u5", "u1", "u2", "u3", "u4")]], proxies={"u5"}
    )
    result = generate_archondata(t, _pod())

    assert "1000001" in result  # real competitor pushed
    assert "1000005" not in result  # proxy excluded from the system of record


def test_archondata_single_name_user():
    t = _finished_tournament(rounds=[[_sweep("u1", "u2", "u3", "u4", "u5")]])
    users = _pod() | {"u1": _user("u1", "Madonna", "1000001")}
    parts = generate_archondata(t, users).split("¤", 1)[1].split("§")

    assert parts[1] == "Madonna"
    assert parts[2] == ""  # no last name


def test_archondata_empty_standings():
    """A tournament that never seated anyone pushes the round count and nothing else."""
    t = _finished_tournament()
    assert generate_archondata(t, {}) == "0¤"
