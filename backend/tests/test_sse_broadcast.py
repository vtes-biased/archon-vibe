"""SSE broadcast envelope + overflow handling: broadcast_precomputed's `ts`
must equal the authoritative modified_at (same value space as the `since`
catch-up filter), and asyncio.QueueFull must mark+evict the connection so the
client reconnects instead of stalling on a dead queue.
"""

import asyncio
import json
from datetime import UTC, datetime

from src.broadcast import (
    SSEConnection,
    _scope_matches,
    _sse_connections,
    broadcast_personal,
    broadcast_precomputed,
)
from src.db import BroadcastData
from src.models import ObjectType, User

MODIFIED_AT = "2026-06-03T12:00:00.123456"


def _member(uid: str = "viewer") -> User:
    """A plain member viewer (vekn_id, no overlay-granting role, no org rights)."""
    return User(uid=uid, modified=datetime.now(UTC), name="M", vekn_id="9999")


def _private_deck(uid: str = "d1", owner: str = "owner") -> dict:
    return {
        "uid": uid,
        "tournament_uid": "t1",
        "user_uid": owner,
        "public": False,
        "cards": {"Some Card": 1},
    }


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


def test_tournament_delivery_flags_scoped_conn_for_participant_refresh():
    """A tournament delivery to the bot flags the live loop to push participant
    identities (newly-seated players resolve to names); sanction deliveries and
    unscoped connections must not set the flag."""
    scoped = SSEConnection(user=None, tournament_uid="t1")
    unscoped = SSEConnection(user=None)
    _sse_connections.clear()
    _sse_connections.update({scoped, unscoped})
    try:
        broadcast_precomputed(_bd(uid="t1"))
        assert scoped.needs_participant_refresh is True
        assert unscoped.needs_participant_refresh is False

        scoped.needs_participant_refresh = False
        broadcast_precomputed(
            BroadcastData(
                obj_type=ObjectType.SANCTION,
                uid="s1",
                pub_json=None,
                mem_json='{"uid":"s1"}',
                full_json='{"uid":"s1"}',
                tournament_uid="t1",
            )
        )
        assert scoped.needs_participant_refresh is False  # sanction doesn't flag
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


def test_broadcast_precomputed_excludes_originating_device():
    """exclude_device_id skips every connection identifying as that device — the
    go-online self-exclusion stopping the initiating device from receiving its
    own offline_mode=false echo. Other devices still get the frame."""
    initiating = SSEConnection(user=None, device_id="dev-A")
    other_device = SSEConnection(user=None, device_id="dev-B")
    no_device = SSEConnection(user=None)  # bot / pre-device client
    _sse_connections.clear()
    _sse_connections.update({initiating, other_device, no_device})
    try:
        broadcast_precomputed(_bd(uid="t1"), exclude_device_id="dev-A")
        assert initiating.queue.empty()  # self-excluded
        assert not other_device.queue.empty()  # different device still served
        assert not no_device.queue.empty()  # no device_id never matches the filter
    finally:
        _sse_connections.clear()


def test_broadcast_precomputed_coalesces_repeat_frames_per_object():
    """Repeated whole-object frames for the same (type,uid) supersede each
    other — the stalled queue holds only the latest per object, not a backlog
    (the memory fix). Distinct objects are NOT coalesced."""
    conn = SSEConnection(user=None)  # public projection
    _sse_connections.clear()
    _sse_connections.add(conn)
    try:
        broadcast_precomputed(_bd(modified_at="2026-06-03T12:00:00.1", uid="t1"))
        broadcast_precomputed(_bd(modified_at="2026-06-03T12:00:00.2", uid="t1"))
        broadcast_precomputed(_bd(modified_at="2026-06-03T12:00:00.3", uid="t2"))
        # t1 collapsed to one frame; t2 distinct → two frames total.
        first = conn.queue.get_nowait()
        second = conn.queue.get_nowait()
        assert conn.queue.empty()
        # t1's surviving frame is the LATEST snapshot (drains current state).
        assert '"ts":"2026-06-03T12:00:00.2"' in first
        assert '"data":{"uid":"t2"}' in second
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


def test_personal_private_deck_demote_emits_tombstone():
    """A demoted organizer (no longer in org_uids) has only member entitlement
    for a private deck, whose member projection is None — so the push is a
    tombstone (uid + deleted_at only) evicting that deck."""
    viewer = _member()
    conn = SSEConnection(user=viewer)
    _sse_connections.clear()
    _sse_connections.add(conn)
    try:
        broadcast_personal(
            viewer.uid,
            obj_type=ObjectType.DECK,
            uid="d1",
            full_dict=_private_deck(),
            obj_user_uid="owner",  # not the viewer's own deck
            org_uids=[],  # no longer an organizer
            modified_at=MODIFIED_AT,
        )
        data = json.loads(conn.queue.get_nowait().removeprefix("data: ").strip())
        assert data["type"] == "deck"
        assert data["data"] == {"uid": "d1", "deleted_at": MODIFIED_AT}
        assert "cards" not in data["data"]  # contents evicted, not leaked
    finally:
        _sse_connections.clear()


def test_personal_organizer_gets_private_deck_at_full():
    """Promote: the same private deck, but the viewer IS now an organizer, so the
    full projection (with contents) is delivered — no tombstone."""
    viewer = _member()
    conn = SSEConnection(user=viewer)
    _sse_connections.clear()
    _sse_connections.add(conn)
    try:
        broadcast_personal(
            viewer.uid,
            obj_type=ObjectType.DECK,
            uid="d1",
            full_dict=_private_deck(),
            obj_user_uid="owner",
            org_uids=[viewer.uid],  # organizer → full
        )
        data = json.loads(conn.queue.get_nowait().removeprefix("data: ").strip())
        assert data["data"]["cards"] == {"Some Card": 1}
        assert "deleted_at" not in data["data"]
    finally:
        _sse_connections.clear()


def test_personal_carries_access_version():
    """The frame rides the new fingerprint so the client refreshes `av` without a
    reconnect."""
    viewer = _member()
    conn = SSEConnection(user=viewer)
    _sse_connections.clear()
    _sse_connections.add(conn)
    try:
        broadcast_personal(
            viewer.uid,
            obj_type=ObjectType.DECK,
            uid="d1",
            full_dict=_private_deck(),
            obj_user_uid="owner",
            org_uids=[],
            access_version="abc123",
        )
        assert '"av":"abc123"' in conn.queue.get_nowait()
    finally:
        _sse_connections.clear()


def test_personal_skips_other_users_and_scoped_streams():
    """Targets only the named user's browser connections — never another user, and
    never a scoped (bot) stream (which replays full state and isn't IDB-backed)."""
    viewer = _member("viewer")
    other = SSEConnection(user=_member("someone-else"))
    scoped = SSEConnection(user=viewer, tournament_uid="t1")
    target = SSEConnection(user=viewer)
    _sse_connections.clear()
    _sse_connections.update({other, scoped, target})
    try:
        broadcast_personal(
            viewer.uid,
            obj_type=ObjectType.DECK,
            uid="d1",
            full_dict=_private_deck(),
            obj_user_uid="owner",
            org_uids=[],
        )
        assert not target.queue.empty()
        assert other.queue.empty()
        assert scoped.queue.empty()
    finally:
        _sse_connections.clear()
