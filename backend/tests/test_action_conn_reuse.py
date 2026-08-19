"""Regression tests: the tournament action handler must not acquire
extra pooled connections while holding the FOR UPDATE row lock.

Reads inside ``tournament_transaction`` now run on the locked ``tx_conn`` instead
of grabbing a second pooled connection, so one in-flight action consumes exactly
one connection and concurrent actions can't starve the small pool. The per-player
sanction fan-out is also collapsed into a single batched query.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid7

import pytest
import src.db as db
from src.models import Sanction, SanctionCategory, SanctionLevel


def _sanction(user_uid: str, level: SanctionLevel) -> Sanction:
    return Sanction(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        user_uid=user_uid,
        issued_by_uid="issuer",
        level=level,
        category=SanctionCategory.UNSPORTSMANLIKE_CONDUCT,
        description="test",
        issued_at=datetime.now(UTC),
    )


@asynccontextmanager
async def _cleanup_sanctions():
    try:
        yield
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE type = 'sanction'")


@pytest.mark.asyncio
async def test_batched_sanctions_match_per_user_union(test_db):
    """get_sanctions_for_users returns the same set as per-user fan-out."""
    u1, u2, u3 = (str(uuid7()) for _ in range(3))
    async with _cleanup_sanctions():
        await db.save_sanction(_sanction(u1, SanctionLevel.SUSPENSION))
        await db.save_sanction(_sanction(u2, SanctionLevel.DISQUALIFICATION))
        await db.save_sanction(_sanction(u2, SanctionLevel.WARNING))
        # u3 has none

        batched = await db.get_sanctions_for_users([u1, u2, u3])
        per_user = []
        for u in (u1, u2, u3):
            per_user.extend(await db.get_sanctions_for_user(u))

        assert {s.uid for s in batched} == {s.uid for s in per_user}
        assert len(batched) == 3
        assert await db.get_sanctions_for_users([]) == []  # empty short-circuits


@pytest.mark.asyncio
async def test_locked_reads_do_not_acquire_pool_connections(test_db, monkeypatch):
    """While holding tx_conn, readers passed conn=tx_conn make zero pool checkouts.

    This is the starvation fix: any read that grabs its own pooled connection
    while the row is locked is what could exhaust the pool under concurrency.
    """
    calls = {"n": 0}
    real_get_connection = db.get_connection

    @asynccontextmanager
    async def counting_get_connection():
        calls["n"] += 1
        async with real_get_connection() as c:
            yield c

    monkeypatch.setattr(db, "get_connection", counting_get_connection)

    u1 = str(uuid7())
    t_uid = str(uuid7())  # nonexistent row is fine; tx_conn is still yielded

    async with _cleanup_sanctions():
        await db.save_sanction(_sanction(u1, SanctionLevel.SUSPENSION))

        async with db.tournament_transaction(t_uid) as (_tournament, tx_conn):
            calls["n"] = 0  # ignore any setup checkouts
            await db.get_sanctions_for_tournament(t_uid, conn=tx_conn)
            await db.get_sanctions_for_users([u1], conn=tx_conn)
            await db.get_sanctions_for_user(u1, conn=tx_conn)
            await db.get_user_by_uid(u1, conn=tx_conn)
            await db.get_decks_for_tournament(t_uid, conn=tx_conn)
            await db.get_all_leagues(conn=tx_conn)
            assert calls["n"] == 0  # no extra pooled connection while locked

        # Sanity: without conn, the same reader DOES acquire from the pool.
        calls["n"] = 0
        await db.get_user_by_uid(u1)
        assert calls["n"] == 1
