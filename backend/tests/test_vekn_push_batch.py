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
    User,
)
from src.vekn_api import VEKNAPIConnectionError, VEKNAPIError
from src.vekn_push import UNCREATED_EVENTS_QUERY, UNPUSHED_RESULTS_QUERY, batch_push


def _tournament(
    uid: str,
    *,
    with_rounds: bool,
    open_rounds: bool = False,
    self_organized_rounds: bool = False,
) -> Tournament:
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
        open_rounds=open_rounds,
        self_organized_rounds=self_organized_rounds,
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


# ---------------------------------------------------------------------------
# Fail-fast circuit: a connection/auth failure aborts the whole batch
# (it reruns next cycle) instead of re-timing-out every pending item serially;
# a per-item data error skips only that item and the batch continues.
# ---------------------------------------------------------------------------


def _member(uid: str, vekn_id: str) -> User:
    return User(
        uid=uid,
        modified=datetime(2025, 6, 1, tzinfo=UTC),
        name="Member",
        vekn_id=vekn_id,
        vekn_synced=False,
    )


class _FakeClient:
    """Minimal stand-in: batch_push's member stage only calls create_member."""

    def __init__(self, first_error: Exception | None) -> None:
        self.calls = 0
        self._first_error = first_error

    async def create_member(self, **_kw) -> None:
        self.calls += 1
        if self.calls == 1 and self._first_error is not None:
            raise self._first_error


@pytest.mark.asyncio
async def test_batch_push_aborts_on_connection_error(test_db, monkeypatch):
    monkeypatch.setenv("VEKN_PUSH", "true")
    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM objects WHERE type = 'tournament'")
    await db.save_user(_member("m1", "1000001"))
    await db.save_user(_member("m2", "1000002"))

    client = _FakeClient(VEKNAPIConnectionError("vekn.net down"))
    stats = await batch_push(client)

    assert stats["aborted"] is True
    assert stats["members_pushed"] == 0
    # Second member is never attempted — that's the point of failing fast.
    assert client.calls == 1


@pytest.mark.asyncio
async def test_batch_push_skips_data_error_and_continues(test_db, monkeypatch):
    monkeypatch.setenv("VEKN_PUSH", "true")
    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM objects WHERE type = 'tournament'")
    await db.save_user(_member("m1", "1000001"))
    await db.save_user(_member("m2", "1000002"))

    client = _FakeClient(VEKNAPIError("bad VEKN number"))
    stats = await batch_push(client)

    # Data error skips just that member (push_member swallows it → not counted
    # in members_pushed); the batch does NOT abort and the other member pushes.
    assert stats["aborted"] is False
    assert stats["members_pushed"] == 1
    assert client.calls == 2


@pytest.mark.asyncio
async def test_push_queries_exclude_open_and_self_organized_rounds(test_db):
    """House open-rounds / self-organized events are never pushed to VEKN.

    Both batch_push selection queries must exclude them: an open_rounds=true
    (or self_organized_rounds=true) tournament is byte-identical to a standard
    VEKN event except for the flag, so without the guard its results would be
    sent to the public VEKN registry. Asserts the invariant against the shipped
    queries; a standard event with the same shape stays selected.
    """
    try:
        # Standard pushable event (rounds + vekn id, unpushed) → stays selected.
        await db.save_tournament(_tournament("standard", with_rounds=True))
        await db.save_tournament(
            _tournament("open", with_rounds=True, open_rounds=True)
        )
        await db.save_tournament(
            _tournament("self-org", with_rounds=True, self_organized_rounds=True)
        )

        async with db.get_connection() as conn:
            result = await conn.execute(
                UNPUSHED_RESULTS_QUERY, (ObjectType.TOURNAMENT,)
            )
            results_selected = {r[0]["uid"] for r in await result.fetchall()}
        assert results_selected == {"standard"}

        # Same trio, but as un-created calendar events (no vekn id, unstamped).
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE type = 'tournament'")
        for uid, open_r, self_org in (
            ("standard", False, False),
            ("open", True, False),
            ("self-org", False, True),
        ):
            t = _tournament(
                uid,
                with_rounds=True,
                open_rounds=open_r,
                self_organized_rounds=self_org,
            )
            t.external_ids = {}
            await db.save_tournament(t)

        async with db.get_connection() as conn:
            result = await conn.execute(
                UNCREATED_EVENTS_QUERY, (ObjectType.TOURNAMENT,)
            )
            events_selected = {r[0]["uid"] for r in await result.fetchall()}
        assert events_selected == {"standard"}
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
