"""Tests for VEKN push sync — archondata format generation.

The archondata string is consumed by the VEKN API (vekn.net) to import
tournament results. Getting the format wrong means silent data corruption
on the VEKN registry. These tests verify the output format, field ordering,
and edge cases (finals GW subtraction, missing users, etc.).
"""

from datetime import UTC, datetime
from unittest.mock import patch

from src.models import (
    FinalsTable,
    Score,
    Seat,
    Standing,
    Table,
    TableState,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)
from src.vekn_push import generate_archondata, tournament_to_vekn_type

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user(uid: str, name: str, vekn_id: str, city: str = "") -> User:
    return User(
        uid=uid,
        modified=datetime(2025, 1, 1, tzinfo=UTC),
        name=name,
        vekn_id=vekn_id,
        city=city,
    )


def _make_tournament(
    *,
    rounds: list | None = None,
    finals: FinalsTable | None = None,
    standings: list[Standing] | None = None,
    winner: str = "",
    rank: TournamentRank = TournamentRank.BASIC,
    name: str = "Test Tournament",
) -> Tournament:
    return Tournament(
        uid="t-001",
        modified=datetime(2025, 6, 1, tzinfo=UTC),
        name=name,
        format=TournamentFormat.Standard,
        rank=rank,
        state=TournamentState.FINISHED,
        start=datetime(2025, 6, 1, tzinfo=UTC),
        rounds=rounds or [],
        finals=finals,
        standings=standings or [],
        winner=winner,
        organizers_uids=["org-1"],
    )


# Stub out _compute_entry_sync since it requires the Rust engine.
# We only care about the archondata *format*, not the rating computation.
class FakeEntry:
    def __init__(self, points: int = 42):
        self.points = points


def _fake_compute(tournament, user_uid, sanctions=None):
    return FakeEntry(points=10)


# ---------------------------------------------------------------------------
# tournament_to_vekn_type
# ---------------------------------------------------------------------------


def test_vekn_type_standard_basic():
    assert tournament_to_vekn_type(TournamentFormat.Standard, TournamentRank.BASIC) == 2


def test_vekn_type_standard_nc():
    assert tournament_to_vekn_type(TournamentFormat.Standard, TournamentRank.NC) == 8


def test_vekn_type_standard_cc():
    assert tournament_to_vekn_type(TournamentFormat.Standard, TournamentRank.CC) == 6


def test_vekn_type_limited():
    assert tournament_to_vekn_type(TournamentFormat.Limited, TournamentRank.BASIC) == 3


def test_vekn_type_v5():
    assert tournament_to_vekn_type(TournamentFormat.V5, TournamentRank.BASIC) == 16


def test_vekn_type_unknown_defaults_to_standard():
    """Unmapped combinations should default to 2 (Standard Constructed)."""
    assert tournament_to_vekn_type(TournamentFormat.V5, TournamentRank.NC) == 2


# ---------------------------------------------------------------------------
# generate_archondata — format validation
# ---------------------------------------------------------------------------


@patch("src.vekn_push._compute_entry_sync", side_effect=_fake_compute)
def test_archondata_basic_format(mock_compute):
    """Verify the basic archondata format: nrounds¤rank§first§last§city§vekn§gw§vp§vpf§tp§toss§rtp§"""
    users = {
        "u1": _user("u1", "Alice Smith", "1000001", city="Paris"),
        "u2": _user("u2", "Bob Jones", "1000002", city="Lyon"),
    }
    standings = [
        Standing(user_uid="u1", gw=2.0, vp=8.5, tp=60, toss=3),
        Standing(user_uid="u2", gw=1.0, vp=5.0, tp=48, toss=1),
    ]
    # 2 rounds of tables, no finals
    rounds = [
        [
            Table(
                seating=[Seat(player_uid="u1"), Seat(player_uid="u2")],
                state=TableState.FINISHED,
            )
        ],
        [
            Table(
                seating=[Seat(player_uid="u1"), Seat(player_uid="u2")],
                state=TableState.FINISHED,
            )
        ],
    ]
    t = _make_tournament(rounds=rounds, standings=standings)
    result = generate_archondata(t, users)

    # nrounds = len(rounds) + (1 if finals else 0) = 2
    assert result.startswith("2¤")

    # Split off the nrounds prefix
    after_nrounds = result[2:]  # skip "2¤"

    # Each player block ends with §, and blocks are concatenated
    # Player 1: rank=1
    # Fields: rank§first§last§city§vekn§gw§vp§vpf§tp§toss§rtp§
    parts = after_nrounds.split("§")
    # Alice Smith: rank 1, first=Alice, last=Smith, city=Paris, vekn=1000001, gw=2, vp=8.5, vpf=0.0, tp=60, toss=3, rtp=10
    assert parts[0] == "1"  # rank
    assert parts[1] == "Alice"  # first name
    assert parts[2] == "Smith"  # last name
    assert parts[3] == "Paris"  # city
    assert parts[4] == "1000001"  # vekn_id
    assert parts[5] == "2"  # gw (int)
    assert parts[6] == "8.5"  # vp
    assert parts[7] == "0.0"  # vpf (no finals)
    assert parts[8] == "60"  # tp
    assert parts[9] == "3"  # toss
    assert parts[10] == "10"  # rating points (mocked)

    # Bob Jones: rank 2 (each player block is 11 fields, so Bob starts at index 11)
    assert parts[11] == "2"  # rank
    assert parts[12] == "Bob"  # first name
    assert parts[13] == "Jones"  # last name
    assert parts[14] == "Lyon"  # city
    assert parts[15] == "1000002"  # vekn_id
    assert parts[16] == "1"  # gw
    assert parts[17] == "5.0"  # vp
    assert parts[22] == ""  # trailing empty after last player


@patch("src.vekn_push._compute_entry_sync", side_effect=_fake_compute)
def test_archondata_nrounds_includes_finals(mock_compute):
    """nrounds should count finals as an extra round."""
    users = {"u1": _user("u1", "Alice Smith", "1000001")}
    standings = [Standing(user_uid="u1", gw=1.0, vp=4.0, tp=36)]
    finals = FinalsTable(
        seating=[Seat(player_uid="u1", result=Score(gw=1, vp=3.0))],
        seed_order=["u1"],
        state=TableState.FINISHED,
    )
    rounds = [
        [Table(seating=[Seat(player_uid="u1")], state=TableState.FINISHED)],
        [Table(seating=[Seat(player_uid="u1")], state=TableState.FINISHED)],
    ]
    t = _make_tournament(rounds=rounds, finals=finals, standings=standings)
    result = generate_archondata(t, users)

    # 2 rounds + 1 finals = 3
    assert result.startswith("3¤")


@patch("src.vekn_push._compute_entry_sync", side_effect=_fake_compute)
def test_archondata_winner_finals_gw_subtracted(mock_compute):
    """Winner's GW should have finals GW subtracted (VEKN wants prelim-only GW)."""
    users = {
        "u1": _user("u1", "Alice Smith", "1000001"),
        "u2": _user("u2", "Bob Jones", "1000002"),
    }
    # Alice is the winner: standings include finals GW
    standings = [
        Standing(user_uid="u1", gw=3.0, vp=10.0, tp=60),  # 2 prelim + 1 finals GW
        Standing(user_uid="u2", gw=1.0, vp=4.0, tp=48),
    ]
    finals = FinalsTable(
        seating=[
            Seat(player_uid="u1", result=Score(gw=1, vp=3.0)),
            Seat(player_uid="u2", result=Score(gw=0, vp=1.5)),
        ],
        seed_order=["u1", "u2"],
        state=TableState.FINISHED,
    )
    rounds = [
        [
            Table(
                seating=[Seat(player_uid="u1"), Seat(player_uid="u2")],
                state=TableState.FINISHED,
            )
        ],
        [
            Table(
                seating=[Seat(player_uid="u1"), Seat(player_uid="u2")],
                state=TableState.FINISHED,
            )
        ],
    ]
    t = _make_tournament(rounds=rounds, finals=finals, standings=standings, winner="u1")
    result = generate_archondata(t, users)

    after_nrounds = result.split("¤", 1)[1]
    parts = after_nrounds.split("§")

    # Alice (winner): gw should be 3 - 1 = 2 (prelim only)
    assert parts[5] == "2"  # gw

    # Alice's vpf should be 3.0 (her finals VP)
    assert parts[7] == "3.0"

    # Bob (non-winner): starts at index 11 (11 fields per player block)
    assert parts[11 + 5] == "1"  # gw unchanged
    assert parts[11 + 7] == "1.5"  # finals VP


@patch("src.vekn_push._compute_entry_sync", side_effect=_fake_compute)
def test_archondata_non_winner_gw_not_subtracted(mock_compute):
    """Non-winner finalists should NOT have GW subtracted even with finals."""
    users = {
        "u1": _user("u1", "Alice Smith", "1000001"),
        "u2": _user("u2", "Bob Jones", "1000002"),
    }
    standings = [
        Standing(user_uid="u1", gw=3.0, vp=10.0, tp=60),
        Standing(user_uid="u2", gw=2.0, vp=7.0, tp=48),
    ]
    finals = FinalsTable(
        seating=[
            Seat(player_uid="u1", result=Score(gw=1, vp=3.0)),
            Seat(player_uid="u2", result=Score(gw=0, vp=1.5)),
        ],
        seed_order=["u1", "u2"],
        state=TableState.FINISHED,
    )
    rounds = [
        [
            Table(
                seating=[Seat(player_uid="u1"), Seat(player_uid="u2")],
                state=TableState.FINISHED,
            )
        ]
    ]
    t = _make_tournament(rounds=rounds, finals=finals, standings=standings, winner="u1")
    result = generate_archondata(t, users)
    after_nrounds = result.split("¤", 1)[1]
    parts = after_nrounds.split("§")

    # Bob is at rank 2 (starts at index 11, 11 fields per player block)
    assert parts[11 + 5] == "2"  # Bob's GW stays 2 (not subtracted)


@patch("src.vekn_push._compute_entry_sync", side_effect=_fake_compute)
def test_archondata_skips_missing_users(mock_compute):
    """Players not found in users_by_uid should be silently skipped."""
    users = {
        "u1": _user("u1", "Alice Smith", "1000001"),
        # u2 is missing from users dict
    }
    standings = [
        Standing(user_uid="u1", gw=2.0, vp=8.0, tp=60),
        Standing(user_uid="u2", gw=1.0, vp=4.0, tp=48),
    ]
    rounds = [[Table(seating=[Seat(player_uid="u1")], state=TableState.FINISHED)]]
    t = _make_tournament(rounds=rounds, standings=standings)
    result = generate_archondata(t, users)

    # Should only contain Alice, not Bob
    assert "1000001" in result
    assert "u2" not in result


@patch("src.vekn_push._compute_entry_sync", side_effect=_fake_compute)
def test_archondata_single_name_user(mock_compute):
    """User with a single-word name should have empty last name."""
    users = {"u1": _user("u1", "Madonna", "1000001")}
    standings = [Standing(user_uid="u1", gw=1.0, vp=4.0, tp=36)]
    rounds = [[Table(seating=[Seat(player_uid="u1")], state=TableState.FINISHED)]]
    t = _make_tournament(rounds=rounds, standings=standings)
    result = generate_archondata(t, users)
    parts = result.split("¤", 1)[1].split("§")

    assert parts[1] == "Madonna"  # first
    assert parts[2] == ""  # last (empty)


@patch("src.vekn_push._compute_entry_sync", side_effect=_fake_compute)
def test_archondata_no_finals_vpf_zero(mock_compute):
    """Without finals, all players should have vpf=0.0."""
    users = {"u1": _user("u1", "Alice Smith", "1000001")}
    standings = [Standing(user_uid="u1", gw=2.0, vp=8.0, tp=60)]
    rounds = [[Table(seating=[Seat(player_uid="u1")], state=TableState.FINISHED)]]
    t = _make_tournament(rounds=rounds, standings=standings)
    result = generate_archondata(t, users)
    parts = result.split("¤", 1)[1].split("§")

    assert parts[7] == "0.0"  # vpf


@patch("src.vekn_push._compute_entry_sync", side_effect=_fake_compute)
def test_archondata_empty_standings(mock_compute):
    """Empty standings should produce just the nrounds prefix."""
    t = _make_tournament(rounds=[[Table(seating=[], state=TableState.FINISHED)]])
    result = generate_archondata(t, {})

    assert result == "1¤"
