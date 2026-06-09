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

from src.broadcast import SSEConnection, _sse_connections, broadcast_precomputed
from src.db import BroadcastData
from src.models import ObjectType

MODIFIED_AT = "2026-06-03T12:00:00.123456"


def _bd(modified_at: str | None = MODIFIED_AT) -> BroadcastData:
    return BroadcastData(
        obj_type=ObjectType.TOURNAMENT,
        uid="t1",
        pub_json='{"uid":"t1"}',
        mem_json=None,
        full_json='{"uid":"t1"}',
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
