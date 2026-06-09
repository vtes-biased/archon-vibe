"""Tests for archon import.

The importer builds tournament state directly. The key invariant guarded here:
`tournament.standings` must be **prelim-only** (like engine-built standings), because
league scoring (`league.rs`) adds finals GW/VP/TP on top of the standings — folding
finals into the standings would double-count them in RTP/GP for imported tournaments.
`Player.result` keeps the full prelim+finals aggregate.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from archon_engine import PyEngine
from src import db
from src.archon_import import (
    ArchonData,
    ArchonPlayer,
    ArchonRoundTable,
    apply_archon_import,
)
from src.models import (
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)


@asynccontextmanager
async def _cleanup_tournaments():
    """test_db only wipes type='user'; drop tournaments we create here."""
    try:
        yield
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE type = 'tournament'")


def _user(uid: str, vekn_id: str) -> User:
    return User(
        uid=uid,
        modified=datetime(2025, 1, 1, tzinfo=UTC),
        name=f"Player {uid}",
        vekn_id=vekn_id,
    )


@pytest.mark.asyncio
async def test_import_standings_are_prelim_only(test_db):
    # 5 players, 1 prelim round + a finals. p1 takes a 2VP prelim GW, then wins the
    # finals with 3 more VP. Standings must show p1 at prelim-only 2VP/1GW (not the
    # 5VP/2GW full aggregate); Player.result keeps the full aggregate.
    async with _cleanup_tournaments():
        vekn = [f"100000{i}" for i in range(1, 6)]
        for i in range(5):
            await db.save_user(_user(f"u{i + 1}", vekn[i]))

        await db.save_tournament(
            Tournament(
                uid="t-import-1",
                modified=datetime(2025, 6, 1, tzinfo=UTC),
                name="Import Test",
                format=TournamentFormat.Standard,
                rank=TournamentRank.BASIC,
                state=TournamentState.PLANNED,
                organizers_uids=["u1"],
            )
        )

        players = [
            ArchonPlayer(
                number=i + 1,
                first_name="Player",
                last_name=str(i + 1),
                city="",
                vekn_id=vekn[i],
            )
            for i in range(5)
        ]
        # Prelim: p1=2 (GW), p2=1, p3=1, p4=0.5, p5=0.5 (sum 5).
        prelim = ArchonRoundTable(
            seats=[(1, 2.0), (2, 1.0), (3, 1.0), (4, 0.5), (5, 0.5)]
        )
        # Finals: p1=3 (winner), p2=1, p3=0.5, p4=0.5, p5=0 (sum 5).
        finals = ArchonRoundTable(
            seats=[(1, 3.0), (2, 1.0), (3, 0.5), (4, 0.5), (5, 0.0)]
        )
        data = ArchonData(
            event_name="Import Test",
            num_rounds=1,
            players=players,
            rounds=[[prelim]],
            finals=finals,
        )

        result = await apply_archon_import("t-import-1", data, "u1", PyEngine())
        assert result.success, result.errors

        updated = await db.get_tournament_by_uid("t-import-1")
        s1 = next(s for s in updated.standings if s.user_uid == "u1")
        assert s1.vp == 2.0, "standings VP is prelim-only (excludes 3 finals VP)"
        assert s1.gw == 1.0, "standings GW is prelim-only (excludes finals GW)"

        # Player.result keeps the full prelim+finals aggregate.
        p1 = next(p for p in updated.players if p.user_uid == "u1")
        assert p1.result.vp == 5.0
        assert p1.result.gw == 2
        assert updated.winner == "u1"
        assert p1.finalist is True
