"""Tests for archon import.

The importer builds tournament state directly. The key invariant guarded here:
`tournament.standings` must be **prelim-only** (like engine-built standings), because
league scoring (`league.rs`) adds finals GW/VP/TP on top of the standings — folding
finals into the standings would double-count them in RTP/GP for imported tournaments.
`Player.result` keeps the full prelim+finals aggregate.
"""

import io
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.resources import files

import msgspec
import openpyxl
import pytest
from archon_engine import PyEngine
from src import db
from src.archon_import import (
    ArchonData,
    ArchonPlayer,
    ArchonRoundTable,
    apply_archon_import,
    parse_archon_file,
    validate_archon_import,
)
from src.models import (
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)

from tests.conftest import seed_tournament


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

        await seed_tournament(
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


@pytest.mark.asyncio
async def test_override_sheet_imports_table_as_judge_overridden(test_db):
    # A Life Boon merged two half VPs into one.
    async with _cleanup_tournaments():
        vekn = [f"200000{i}" for i in range(1, 6)]
        for i in range(5):
            await db.save_user(_user(f"u{i + 1}", vekn[i]))
        await seed_tournament(
            Tournament(
                uid="t-import-2",
                modified=datetime(2025, 6, 1, tzinfo=UTC),
                name="Override Test",
                format=TournamentFormat.Standard,
                rank=TournamentRank.BASIC,
                state=TournamentState.PLANNED,
                organizers_uids=["u1"],
            )
        )

        template = files("src").joinpath("data", "thearchon1.5l.xlsx").read_bytes()
        wb = openpyxl.load_workbook(io.BytesIO(template))
        wb["Override"]["A6"] = 1
        wb["Override"]["B6"] = 2
        wb["Override"]["D6"] = "Life Boon, game ended in time"
        out = io.BytesIO()
        wb.save(out)
        data = parse_archon_file(out.getvalue())
        data.players = [
            ArchonPlayer(number=i + 1, first_name="P", last_name="", city="", vekn_id=v)
            for i, v in enumerate(vekn)
        ]
        boon = ArchonRoundTable(
            seats=[(1, 1.0), (2, 0.0), (3, 0.0), (4, 1.5), (5, 0.5)], number=2
        )
        data.rounds = [[boon]]
        engine = PyEngine()
        assert engine.check_table_vps([s[1] for s in boon.seats])
        assert validate_archon_import(data, engine) == []

        result = await apply_archon_import("t-import-2", data, "u1", engine)
        assert result.success, result.errors
        table = (await db.get_tournament_by_uid("t-import-2")).rounds[0][0]
        assert table.state == "Finished"
        assert table.override.judge_uid == "u1"
        assert table.override.comment == "Life Boon, game ended in time"


@pytest.mark.asyncio
async def test_import_no_final_breaks_first_place_tie_with_toss(test_db):
    async with _cleanup_tournaments():
        vekn = [f"300000{i}" for i in range(1, 9)]
        for i in range(8):
            await db.save_user(_user(f"u{i + 1}", vekn[i]))
        await seed_tournament(
            Tournament(
                uid="t-import-no-final",
                modified=datetime(2025, 6, 1, tzinfo=UTC),
                name="No-Final Import",
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
            for i in range(8)
        ]
        t1 = ArchonRoundTable(seats=[(1, 2.5), (2, 1.0), (3, 0.5), (4, 0.0)], number=1)
        t2 = ArchonRoundTable(seats=[(5, 2.5), (6, 1.0), (7, 0.5), (8, 0.0)], number=2)
        data = ArchonData(
            event_name="No-Final Import",
            num_rounds=1,
            players=players,
            rounds=[[t1, t2]],
            finals=None,
        )

        engine = PyEngine()
        result = await apply_archon_import("t-import-no-final", data, "u1", engine)
        assert result.success, result.errors

        updated = await db.get_tournament_by_uid("t-import-no-final")
        assert updated.finals is None
        assert updated.winner in ("u1", "u5")
        assert updated.standings[0].user_uid == updated.winner
        assert all(not p.finalist for p in updated.players)
        assert all(not s.finalist for s in updated.standings)

        toss_u1 = next(p.toss for p in updated.players if p.user_uid == "u1")
        toss_u5 = next(p.toss for p in updated.players if p.user_uid == "u5")
        assert {toss_u1, toss_u5} == {1, 2}

        t_json = msgspec.json.encode(updated).decode()
        assert engine.ranking_eligibility(t_json) == "eligible"
        assert engine.compute_rating_vp_gw(t_json, "[]", updated.winner) == (2.5, 1.0)
        final_rows = msgspec.json.decode(
            engine.compute_final_standings(
                msgspec.json.encode(
                    {"standings": updated.standings, "winner": updated.winner}
                ).decode()
            )
        )
        assert final_rows[0]["user_uid"] == updated.winner
        assert final_rows[0]["rank"] == 1
        assert final_rows[0]["finalist_position"] == 0
