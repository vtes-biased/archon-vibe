"""Tests for rating computation helpers."""

import msgspec
import pytest

from src.models import (
    FinalsTable,
    Score,
    Seat,
    Standing,
    Table,
    Tournament,
)
from src.ratings import _finalist_position, _player_stats


def _make_tournament(**overrides) -> Tournament:
    """Minimal Tournament with sensible defaults."""
    defaults = dict(
        uid="t-001",
        modified="2026-01-01T00:00:00",
        name="Test Tournament",
        format="Standard",
        rank="",
        state="Finished",
        country="FR",
        rounds=[],
        finals=None,
        standings=[],
        winner="",
    )
    defaults.update(overrides)
    return msgspec.convert(defaults, Tournament)


def _seat(uid: str, vp: float = 0.0, gw: int = 0) -> dict:
    return {"player_uid": uid, "result": {"vp": vp, "gw": gw, "tp": 0}}


# ---------------------------------------------------------------------------
# _player_stats
# ---------------------------------------------------------------------------


class TestPlayerStats:
    def test_prelim_only(self):
        """Player who only played prelims gets prelim VP/GW."""
        t = _make_tournament(
            rounds=[
                [{"seating": [_seat("p1", 2.0, 1), _seat("p2", 1.0, 0)]}],
                [{"seating": [_seat("p1", 0.5, 0), _seat("p3", 1.5, 0)]}],
            ],
        )
        vp, gw = _player_stats(t, "p1")
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
        vp, gw = _player_stats(t, "p1")
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
        vp, gw = _player_stats(t, "p3")
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
        vp, gw = _player_stats(t, "p1")
        assert vp == 3.0
        assert gw == 1  # 0 prelim + 1 finals

    def test_vekn_synced_fallback(self):
        """No rounds/finals: falls back to standings."""
        t = _make_tournament(
            standings=[
                {"user_uid": "p1", "vp": 7.5, "gw": 3.0, "tp": 36},
                {"user_uid": "p2", "vp": 4.0, "gw": 1.0, "tp": 24},
            ],
        )
        vp, gw = _player_stats(t, "p1")
        assert vp == 7.5
        assert gw == 3

    def test_vekn_synced_missing_player(self):
        """Standings fallback returns 0 for unknown player."""
        t = _make_tournament(
            standings=[{"user_uid": "p1", "vp": 5.0, "gw": 2.0, "tp": 24}],
        )
        vp, gw = _player_stats(t, "unknown")
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
        vp, gw = _player_stats(t, "p1")
        assert vp == 4.0
        assert gw == 1


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
