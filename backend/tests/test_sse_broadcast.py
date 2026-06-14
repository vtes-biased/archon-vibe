"""Tests for SSE broadcast envelope + overflow handling.

Covers two sync-correctness invariants:
- broadcast_precomputed emits the authoritative modified_at as the envelope
  `ts` field, so clients advance their sync cursor in the same value space as
  the server's `since` catch-up filter.
- On asyncio.QueueFull the connection is marked closed and evicted, so the SSE
  generator ends the stream and the browser reconnects + catches up instead of
  staying OPEN on a queue that no longer receives events.
"""

import asyncio

from src.broadcast import (
    SSEConnection,
    _scope_matches,
    _sse_connections,
    broadcast_precomputed,
)
from src.db import BroadcastData
from src.models import ObjectType

MODIFIED_AT = "2026-06-03T12:00:00.123456"


def _bd(modified_at: str | None = MODIFIED_AT, uid: str = "t1") -> BroadcastData:
    return BroadcastData(
        obj_type=ObjectType.TOURNAMENT,
        uid=uid,
        pub_json=f'{{"uid":"{uid}"}}',
        mem_json=None,
        full_json=f'{{"uid":"{uid}"}}',
        modified_at=modified_at,
    )


def test_broadcast_precomputed_includes_ts():
    """Live envelope carries `ts` = authoritative modified_at."""
    conn = SSEConnection(user=None)  # no user -> public projection
    _sse_connections.clear()
    _sse_connections.add(conn)
    try:
        broadcast_precomputed(_bd())
        msg = conn.queue.get_nowait()
        assert '"type":"tournament"' in msg
        assert '"data":{"uid":"t1"}' in msg
        assert f'"ts":"{MODIFIED_AT}"' in msg
    finally:
        _sse_connections.clear()


def test_broadcast_precomputed_omits_ts_when_missing():
    """Defensive: no `ts` key when modified_at is absent."""
    conn = SSEConnection(user=None)
    _sse_connections.clear()
    _sse_connections.add(conn)
    try:
        broadcast_precomputed(_bd(modified_at=None))
        msg = conn.queue.get_nowait()
        assert '"ts"' not in msg
    finally:
        _sse_connections.clear()


def test_scoped_connection_only_receives_its_tournament():
    """A tournament-scoped connection (the bot) gets its tournament's events and
    drops everything else; an unscoped connection still gets both."""
    scoped = SSEConnection(user=None, tournament_uid="t1")
    unscoped = SSEConnection(user=None)
    _sse_connections.clear()
    _sse_connections.update({scoped, unscoped})
    try:
        broadcast_precomputed(_bd(uid="t2"))  # a different tournament
        assert scoped.queue.empty()  # scoped drops it
        assert not unscoped.queue.empty()  # unscoped still gets it

        broadcast_precomputed(_bd(uid="t1"))  # the scoped tournament
        assert '"data":{"uid":"t1"}' in scoped.queue.get_nowait()
    finally:
        _sse_connections.clear()


def test_scope_matches_sanction_by_tournament_uid():
    """A scoped connection wants only the sanctions of its tournament; unscoped
    wants everything."""
    scoped = SSEConnection(user=None, tournament_uid="t1")
    unscoped = SSEConnection(user=None)
    mine = BroadcastData(
        obj_type=ObjectType.SANCTION,
        uid="s1",
        pub_json=None,
        mem_json='{"uid":"s1"}',
        full_json='{"uid":"s1"}',
        tournament_uid="t1",
    )
    other = BroadcastData(
        obj_type=ObjectType.SANCTION,
        uid="s2",
        pub_json=None,
        mem_json='{"uid":"s2"}',
        full_json='{"uid":"s2"}',
        tournament_uid="t2",
    )
    assert _scope_matches(scoped, mine) is True
    assert _scope_matches(scoped, other) is False
    assert _scope_matches(unscoped, other) is True


def test_broadcast_precomputed_closes_connection_on_overflow():
    """QueueFull marks the connection closed and evicts it."""
    conn = SSEConnection(user=None)
    # Saturate the bounded queue so the next put_nowait raises QueueFull.
    while True:
        try:
            conn.queue.put_nowait("filler")
        except asyncio.QueueFull:
            break
    _sse_connections.clear()
    _sse_connections.add(conn)
    try:
        broadcast_precomputed(_bd())
        assert conn.closed is True
        assert conn not in _sse_connections
    finally:
        _sse_connections.clear()
