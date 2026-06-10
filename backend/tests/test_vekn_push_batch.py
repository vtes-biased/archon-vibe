"""Tests for batch_push's selection queries (the import guards).

batch_push retries any finished tournament that has no `vekn_pushed_at`. The
rounds guard excludes tournaments whose results did NOT originate in-app — VEKN
imports / ETL-migrated history have populated `standings` but no `rounds`.
Re-pushing those would send finals-folded numbers to the public VEKN registry
(see test_vekn_tournament_sync.py for the other half of the invariant).

The calendar-event query's vekn_pushed_at guard excludes ETL-imported finished
tournaments that never had a vekn id (old in-app events): without it, the first
push run would create vekn.net calendar events for years-old history.
"""

from datetime import UTC, datetime

import pytest
from src import db
from src.models import (
    ObjectType,
    Seat,
    Standing,
    Table,
    TableState,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
)
from src.vekn_push import UNCREATED_EVENTS_QUERY, UNPUSHED_RESULTS_QUERY


def _tournament(uid: str, *, with_rounds: bool) -> Tournament:
    rounds = (
        [[Table(seating=[Seat(player_uid="p1")], state=TableState.FINISHED)]]
        if with_rounds
        else []
    )
    return Tournament(
        uid=uid,
        modified=datetime(2025, 6, 1, tzinfo=UTC),
        name=f"T {uid}",
        format=TournamentFormat.Standard,
        rank=TournamentRank.BASIC,
        state=TournamentState.FINISHED,
        start=datetime(2025, 6, 1, tzinfo=UTC),
        rounds=rounds,
        # Imports always carry standings regardless of rounds.
        standings=[Standing(user_uid="p1", gw=1.0, vp=4.0, tp=36)],
        external_ids={"vekn": "999"},
        organizers_uids=["org-1"],
    )


@pytest.mark.asyncio
async def test_results_query_selects_in_app_excludes_imports(test_db):
    try:
        # In-app finished tournament: has rounds, unpushed → MUST be selected.
        await db.save_tournament(_tournament("in-app", with_rounds=True))
        # VEKN import: standings but no rounds, unpushed → MUST NOT be selected
        # (even with vekn_pushed_at unset, the rounds guard keeps it out).
        await db.save_tournament(_tournament("import", with_rounds=False))

        async with db.get_connection() as conn:
            result = await conn.execute(
                UNPUSHED_RESULTS_QUERY, (ObjectType.TOURNAMENT,)
            )
            rows = await result.fetchall()
        # psycopg returns jsonb columns pre-decoded to dicts
        selected = {r[0]["uid"] for r in rows}

        assert selected == {"in-app"}
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE type = 'tournament'")


@pytest.mark.asyncio
async def test_events_query_excludes_stamped_imports(test_db):
    try:
        # In-app tournament without a vekn event yet → MUST be selected.
        t_new = _tournament("in-app", with_rounds=True)
        t_new.external_ids = {}
        await db.save_tournament(t_new)
        # ETL-imported finished tournament without a vekn id: stamped
        # vekn_pushed_at at import (no push owed) → MUST NOT be selected.
        t_old = _tournament("import", with_rounds=True)
        t_old.external_ids = {}
        t_old.vekn_pushed_at = datetime(2025, 6, 2, tzinfo=UTC)
        await db.save_tournament(t_old)

        async with db.get_connection() as conn:
            result = await conn.execute(
                UNCREATED_EVENTS_QUERY, (ObjectType.TOURNAMENT,)
            )
            rows = await result.fetchall()
        selected = {r[0]["uid"] for r in rows}

        assert selected == {"in-app"}
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE type = 'tournament'")
