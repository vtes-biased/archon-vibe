"""Tests for the ambient transaction connection.

While a `tournament_transaction` is open, READ helpers (those routed through
`db._acquire`) transparently reuse its connection instead of checking out a
second one — so an action holds one pooled connection and can't starve the pool.
WRITES deliberately do NOT ride the ambient connection: they pool independently
(or join only when passed `conn=tx_conn` explicitly), which keeps the go-online
VEKN-ID allocation loop correct. A child asyncio task must never touch the
ambient connection; doing so raises.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
import src.db as db
from src.models import User
from uuid import uuid7


@asynccontextmanager
async def _count_pool_checkouts(monkeypatch):
    """Yield a counter dict; increments once per pool checkout via get_connection."""
    calls = {"n": 0}
    real = db.get_connection

    @asynccontextmanager
    async def counting():
        calls["n"] += 1
        async with real() as c:
            yield c

    monkeypatch.setattr(db, "get_connection", counting)
    yield calls


@pytest.mark.asyncio
async def test_read_helper_reuses_ambient_without_explicit_conn(test_db, monkeypatch):
    """A read inside a transaction reuses tx_conn even with no conn= passed."""
    u1 = str(uuid7())
    t_uid = str(uuid7())
    async with _count_pool_checkouts(monkeypatch) as calls:
        async with db.tournament_transaction(t_uid) as (_t, _tx):
            calls["n"] = 0
            # No conn argument — must still reuse the ambient connection.
            await db.get_sanctions_for_users([u1])
            await db.get_user_by_uid(u1)
            await db.get_user_by_vekn_id("1000000")
            assert calls["n"] == 0  # zero pool checkouts while locked


@pytest.mark.asyncio
async def test_write_inside_transaction_pools_independently(test_db, monkeypatch):
    """Writes must NOT ride the ambient connection — they check out of the pool.

    This is what keeps go-online's allocate→insert→allocate loop correct: each
    new user commits independently and is visible to the next allocation.
    """
    t_uid = str(uuid7())
    async with _count_pool_checkouts(monkeypatch) as calls:
        async with db.tournament_transaction(t_uid) as (_t, _tx):
            calls["n"] = 0
            await db.get_user_by_uid(str(uuid7()))  # read → ambient → 0
            assert calls["n"] == 0
            await db.save_user(
                User(uid=str(uuid7()), modified=datetime.now(UTC), name="W")
            )
            assert calls["n"] == 1  # write → its own pooled connection


@pytest.mark.asyncio
async def test_vekn_allocation_inside_transaction_no_collision(test_db):
    """allocate→insert→allocate inside a transaction yields distinct VEKN IDs.

    Direct regression for the bug avoided by keeping writes independent: if
    save_user joined the outer transaction, its row would be uncommitted and
    the second allocation (a separate advisory-locked txn) would reissue the id.
    """
    t_uid = str(uuid7())
    async with db.tournament_transaction(t_uid) as (_t, _tx):
        id1 = await db.allocate_next_vekn_id()
        await db.save_user(
            User(uid=str(uuid7()), modified=datetime.now(UTC), name="P1", vekn_id=id1)
        )
        id2 = await db.allocate_next_vekn_id()
    assert id1 != id2


@pytest.mark.asyncio
async def test_ambient_connection_rejects_cross_task_use(test_db):
    """A task spawned inside a transaction must not use the ambient connection."""
    u1 = str(uuid7())
    t_uid = str(uuid7())
    async with db.tournament_transaction(t_uid) as (_t, _tx):

        async def child():
            # Inherits the contextvar but runs in a different asyncio.Task.
            return await db.get_user_by_uid(u1)

        task = asyncio.create_task(child())
        with pytest.raises(RuntimeError, match="different task"):
            await task
