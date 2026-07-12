"""Tests for rating computation helpers."""

import msgspec
import pytest
from archon_engine import PyEngine
from src import db
from src.models import (
    ObjectType,
    Sanction,
    Tournament,
)
from src.ratings import (
    _compute_entry_sync,
    _finalist_position,
    _is_disqualified,
    _player_count,
)

_engine = PyEngine()


def _rating_vp_gw(t: Tournament, user_uid: str, sanctions: list | None = None):
    """Exercise the single-source Rust rating stat (VP/GW incl. finals + SA)."""
    return _engine.compute_rating_vp_gw(
        msgspec.json.encode(t).decode(),
        msgspec.json.encode(sanctions or []).decode(),
        user_uid,
    )


def _make_tournament(**overrides) -> Tournament:
    """Minimal Tournament with sensible defaults."""
    defaults = {
        "uid": "t-001",
        "modified": "2026-01-01T00:00:00",
        "name": "Test Tournament",
        "format": "Standard",
        "rank": "",
        "state": "Finished",
        "country": "FR",
        "rounds": [],
        "finals": None,
        "standings": [],
        "winner": "",
    }
    defaults.update(overrides)
    return msgspec.convert(defaults, Tournament)


def _seat(uid: str, vp: float = 0.0, gw: int = 0) -> dict:
    return {"player_uid": uid, "result": {"vp": vp, "gw": gw, "tp": 0}}


# ---------------------------------------------------------------------------
# compute_rating_vp_gw (single-source Rust rating stat)
# ---------------------------------------------------------------------------


class TestRatingVpGw:
    def test_prelim_only(self):
        """Player who only played prelims gets prelim VP/GW."""
        t = _make_tournament(
            rounds=[
                [{"seating": [_seat("p1", 2.0, 1), _seat("p2", 1.0, 0)]}],
                [{"seating": [_seat("p1", 0.5, 0), _seat("p3", 1.5, 0)]}],
            ],
        )
        vp, gw = _rating_vp_gw(t, "p1")
        assert vp == 2.5
        assert gw == 1

    def test_finalist_includes_finals(self):
        """Finalist gets prelim + finals VP/GW combined."""
        t = _make_tournament(
            rounds=[
                [{"seating": [_seat("p1", 2.0, 1), _seat("p2", 1.0, 0)]}],
            ],
            finals={
                "seating": [_seat("p1", 3.0, 1), _seat("p2", 0.5, 0)],
                "seed_order": ["p1", "p2"],
            },
        )
        vp, gw = _rating_vp_gw(t, "p1")
        assert vp == 5.0
        assert gw == 2

    def test_non_finalist_unaffected(self):
        """Player not in finals only gets prelim stats."""
        t = _make_tournament(
            rounds=[
                [{"seating": [_seat("p3", 1.0, 0)]}],
            ],
            finals={
                "seating": [_seat("p1", 3.0, 1), _seat("p2", 0.5, 0)],
                "seed_order": ["p1", "p2"],
            },
        )
        vp, gw = _rating_vp_gw(t, "p3")
        assert vp == 1.0
        assert gw == 0

    def test_winner_gw(self):
        """Winner's GW includes the finals GW."""
        t = _make_tournament(
            rounds=[
                [{"seating": [_seat("p1", 1.0, 0), _seat("p2", 2.0, 1)]}],
            ],
            finals={
                "seating": [_seat("p1", 2.0, 1), _seat("p2", 1.0, 0)],
                "seed_order": ["p1", "p2"],
            },
            winner="p1",
        )
        vp, gw = _rating_vp_gw(t, "p1")
        assert vp == 3.0
        assert gw == 1  # 0 prelim + 1 finals

    def test_sa_full_penalty(self):
        """SA on a played round subtracts a full 1.0 VP (not the old overflow)."""
        t = _make_tournament(
            rounds=[
                [{"seating": [_seat("p1", 2.0, 0), _seat("p2", 0.0, 0)]}],
            ],
        )
        sanctions = [
            {
                "user_uid": "p1",
                "level": "standings_adjustment",
                "round_number": 0,
                "lifted_at": None,
                "deleted_at": None,
            }
        ]
        vp, gw = _rating_vp_gw(t, "p1", sanctions)
        assert vp == 1.0  # raw 2.0 - full 1.0 (old overflow would have been 0)

    def test_sa_goes_negative(self):
        """SA penalty can push the rating VP below zero."""
        t = _make_tournament(
            rounds=[
                [{"seating": [_seat("p1", 0.0, 0), _seat("p2", 0.0, 0)]}],
            ],
        )
        sanctions = [
            {
                "user_uid": "p1",
                "level": "standings_adjustment",
                "round_number": 0,
                "lifted_at": None,
                "deleted_at": None,
            }
        ]
        vp, _ = _rating_vp_gw(t, "p1", sanctions)
        assert vp == -1.0

    def test_vekn_synced_fallback(self):
        """No rounds/finals: falls back to standings."""
        t = _make_tournament(
            standings=[
                {"user_uid": "p1", "vp": 7.5, "gw": 3.0, "tp": 36},
                {"user_uid": "p2", "vp": 4.0, "gw": 1.0, "tp": 24},
            ],
        )
        vp, gw = _rating_vp_gw(t, "p1")
        assert vp == 7.5
        assert gw == 3

    def test_vekn_synced_missing_player(self):
        """Standings fallback returns 0 for unknown player."""
        t = _make_tournament(
            standings=[{"user_uid": "p1", "vp": 5.0, "gw": 2.0, "tp": 24}],
        )
        vp, gw = _rating_vp_gw(t, "unknown")
        assert vp == 0.0
        assert gw == 0

    def test_finals_only_no_rounds(self):
        """Edge case: finals data but no rounds (guard: rounds or finals)."""
        t = _make_tournament(
            finals={
                "seating": [_seat("p1", 4.0, 1), _seat("p2", 1.0, 0)],
                "seed_order": ["p1", "p2"],
            },
        )
        vp, gw = _rating_vp_gw(t, "p1")
        assert vp == 4.0
        assert gw == 1


# ---------------------------------------------------------------------------
# Disqualified player earns no RTP (the backend guard, not just engine zeroing)
# ---------------------------------------------------------------------------


def _sanction(user_uid: str, **overrides) -> Sanction:
    d = {
        "uid": "s-001",
        "modified": "2026-01-01T00:00:00",
        "user_uid": user_uid,
        "issued_by_uid": "judge",
        "level": "disqualification",
        "category": "unsportsmanlike_conduct",
        "description": "",
        "issued_at": "2026-01-01T00:00:00",
    }
    d.update(overrides)
    return msgspec.convert(d, Sanction)


def test_dq_player_earns_no_rating_entry_co_player_unaffected_count_inclusive():
    """A DQ'd player who played earns NO rating points — not even the 5-point
    participation base (spec #284). The engine zeroes their VP/GW to (0,0), so an
    entry would still score base=5; the backend guard that prevents any entry is
    `_is_disqualified`. This pins that guard (both DQ signals), proves the co-player
    is untouched, and that `_player_count` stays inclusive of the DQ'd head."""
    t = _make_tournament(
        players=[
            {"user_uid": "dq_state", "state": "Disqualified"},
            {"user_uid": "dq_sanction", "state": "Finished"},
            {"user_uid": "clean", "state": "Finished"},
        ],
        rounds=[
            [
                {
                    "seating": [
                        _seat("dq_state", 1.0, 0),
                        _seat("dq_sanction", 1.0, 0),
                        _seat("clean", 2.0, 1),
                    ]
                }
            ],
        ],
    )
    sanctions = [_sanction("dq_sanction")]

    # Both DQ signals trip the guard; the clean co-player does not.
    assert _is_disqualified(t, sanctions, "dq_state")
    assert _is_disqualified(t, sanctions, "dq_sanction")
    assert not _is_disqualified(t, sanctions, "clean")

    # Were a DQ'd player NOT skipped, their entry would still bank the 5-pt base
    # (VP/GW zeroed by the engine, not the points) — which is exactly the RTP the
    # spec forbids, and why the guard must skip the entry entirely.
    dq_entry = _compute_entry_sync(t, "dq_state", sanctions)
    assert (dq_entry.vp, dq_entry.gw) == (0.0, 0)
    assert dq_entry.points == 5

    # The co-player's entry is unaffected.
    clean_entry = _compute_entry_sync(t, "clean", sanctions)
    assert clean_entry.vp == 2.0 and clean_entry.gw == 1

    # Head-count stays inclusive of DQ'd players (finalist-coefficient base).
    assert _player_count(t) == 3


# ---------------------------------------------------------------------------
# _finalist_position
# ---------------------------------------------------------------------------


class TestFinalistPosition:
    def test_winner(self):
        t = _make_tournament(
            winner="p1",
            finals={
                "seating": [_seat("p1"), _seat("p2")],
                "seed_order": ["p1", "p2"],
            },
        )
        assert _finalist_position(t, "p1") == 1

    def test_runner_up(self):
        t = _make_tournament(
            winner="p1",
            finals={
                "seating": [_seat("p1"), _seat("p2")],
                "seed_order": ["p1", "p2"],
            },
        )
        assert _finalist_position(t, "p2") == 2

    def test_non_finalist(self):
        t = _make_tournament(
            winner="p1",
            finals={
                "seating": [_seat("p1"), _seat("p2")],
                "seed_order": ["p1", "p2"],
            },
        )
        assert _finalist_position(t, "p3") == 0

    def test_vekn_synced_runner_up(self):
        """No finals object: uses standings.finalist flag."""
        t = _make_tournament(
            winner="p1",
            standings=[
                {"user_uid": "p1", "finalist": True},
                {"user_uid": "p2", "finalist": True},
                {"user_uid": "p3", "finalist": False},
            ],
        )
        assert _finalist_position(t, "p2") == 2

    def test_vekn_synced_non_finalist(self):
        t = _make_tournament(
            winner="p1",
            standings=[
                {"user_uid": "p1", "finalist": True},
                {"user_uid": "p3", "finalist": False},
            ],
        )
        assert _finalist_position(t, "p3") == 0


# ---------------------------------------------------------------------------
# Hall of Fame win counting (get_tournament_wins_for_users)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hof_wins_exclude_online_and_house_formats(test_db):
    """HoF convention: only finished IRL VEKN-format wins count."""
    cases = [
        ("w-irl", {}, True),
        ("w-online", {"online": True}, False),
        ("w-open", {"open_rounds": True}, False),
        ("w-self", {"self_organized_rounds": True}, False),
        ("w-running", {"state": "Playing"}, False),
    ]
    for uid, overrides, _ in cases:
        t = _make_tournament(uid=uid, winner="champ", **overrides)
        await db.save_object_from_model(ObjectType.TOURNAMENT, t)

    wins = await db.get_tournament_wins_for_users({"champ"})
    assert set(wins.get("champ", [])) == {uid for uid, _, counts in cases if counts}
