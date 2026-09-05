"""SSE broadcast system: owns the connection set and all broadcast functions."""

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import msgspec

from .access_levels import compute_full, compute_member, compute_public
from .db import BroadcastData
from .models import ObjectType, Role, User

logger = logging.getLogger(__name__)

encoder = msgspec.json.Encoder()

# Distinct pending frames before overflow→close; coalescing below already caps
# a stalled tournament viewer at ~1 frame. 100→30 as cheap insurance.
_SSE_QUEUE_MAXSIZE = 30


class CoalescingQueue:
    """Per-connection SSE queue keeping only the LATEST frame per key — coalesced
    by (type, uid), so a stalled consumer holds ~1 frame per object, not a backlog
    of stale snapshots. Non-keyed events are never coalesced.
    Single-consumer, event-loop-only: no locking.
    """

    def __init__(self, maxsize: int = _SSE_QUEUE_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._items: OrderedDict[object, str] = OrderedDict()
        self._event = asyncio.Event()
        self._seq = 0

    def put_nowait(self, msg: str, *, key: object = None) -> None:
        """A given `key` replaces any pending frame for it in place (FIFO position
        kept); no key means never coalesced. Raises asyncio.QueueFull past maxsize."""
        if key is None:
            key = self._seq
            self._seq += 1
        if key not in self._items and len(self._items) >= self._maxsize:
            raise asyncio.QueueFull
        self._items[key] = msg  # replace keeps original position (no reorder)
        self._event.set()

    def get_nowait(self) -> str:
        if not self._items:
            raise asyncio.QueueEmpty
        _, msg = self._items.popitem(last=False)
        return msg

    async def get(self) -> str:
        while not self._items:
            self._event.clear()
            await self._event.wait()
        _, msg = self._items.popitem(last=False)
        return msg

    def empty(self) -> bool:
        return not self._items


@dataclass(eq=False)
class SSEConnection:
    queue: CoalescingQueue = field(default_factory=CoalescingQueue)
    user: User | None = None
    # Set when the queue overflows: the SSE generator ends the stream so the
    # browser reconnects and catches up, rather than staying open deaf.
    closed: bool = False
    # None = unscoped (browser full sync); otherwise scoped to one tournament's
    # object, sanctions and judge calls (the Discord bot).
    tournament_uid: str | None = None
    # The offline-lock device this browser identifies as (None for the bot).
    # Lets a write self-exclude its originating device from its own broadcast.
    device_id: str | None = None
    # Scoped connections need seated participants' User identities, which the
    # scope filter drops; the live loop fetches them when this flag is set.
    sent_participant_uids: set[str] = field(default_factory=set)
    needs_participant_refresh: bool = False


_sse_connections: set[SSEConnection] = set()


def _conn_label(conn: SSEConnection) -> str:
    """Identify a connection in logs by user + scope, so overflow/close warnings
    can be attributed to the bot vs a browser tab."""
    user = conn.user.uid if conn.user else "anon"
    scope = (
        f"tournament={conn.tournament_uid}" if conn.tournament_uid else "full-corpus"
    )
    return f"user={user} {scope}"


def entitled_level(
    viewer: User | None,
    *,
    obj_type: str,
    uid: str,
    country: str | None,
    org_uids: list[str] | None,
    obj_user_uid: str | None,
) -> str:
    """Returns "public", "member" or "full" — the projection level `viewer` is
    entitled to for one object. Single source of truth for SSE access, shared by
    the live broadcast and the tournament-scoped catch-up (main.stream_updates).
    """
    if not viewer:
        return "public"
    if Role.IC in viewer.roles:
        return "full"
    # Promo inventory chain isn't country-scoped — NC sees full (holdings)
    # everywhere; Princes/organizers stay member.
    if obj_type == ObjectType.PROMO and Role.NC in viewer.roles:
        return "full"
    if (
        Role.NC in viewer.roles
        and viewer.country
        and country
        and viewer.country == country
    ):
        return "full"
    if org_uids and viewer.uid in org_uids:
        return "full"
    if viewer.vekn_id:
        if obj_type == ObjectType.USER and uid == viewer.uid:
            return "full"
        if obj_type == ObjectType.DECK and obj_user_uid == viewer.uid:
            return "full"
        return "member"
    return "public"


def _scope_matches(conn: SSEConnection, bd: BroadcastData) -> bool:
    """Whether a scoped connection wants this object. Unscoped connections want
    everything; a scoped one wants only its own tournament and that tournament's
    sanctions — keep symmetric with main._scoped_catchup_frames.
    """
    if conn.tournament_uid is None:
        return True
    if bd.obj_type == ObjectType.TOURNAMENT:
        return bd.uid == conn.tournament_uid
    if bd.obj_type == ObjectType.SANCTION:
        return bd.tournament_uid == conn.tournament_uid
    return False


def _wake_sse_connections() -> None:
    for conn in list(_sse_connections):
        try:
            # Fixed key: repeat wakeups coalesce to one pending nudge.
            conn.queue.put_nowait("", key="__wake__")
        except Exception:
            pass


def broadcast_precomputed(
    bd: BroadcastData, *, exclude_device_id: str | None = None
) -> None:
    """Broadcast pre-computed projections to SSE connections. No DB access.

    `exclude_device_id` skips the initiating device so it doesn't get its own
    write echoed back (go-online); excludes the whole device since offline mode
    is single-tab.
    """

    def _make_msg(json_str: str) -> str:
        # `ts` carries modified_at for the sync cursor. NO `av` here: this frame is
        # per-LEVEL shared, but the fingerprint is per-USER — only broadcast_personal carries it.
        ts = f',"ts":"{bd.modified_at}"' if bd.modified_at else ""
        return f'data: {{"type":"{bd.obj_type}","data":{json_str}{ts}}}\n\n'

    msg_by_level = {
        "public": _make_msg(bd.pub_json) if bd.pub_json else None,
        "member": _make_msg(bd.mem_json) if bd.mem_json else None,
        "full": _make_msg(bd.full_json) if bd.full_json else None,
    }
    if bd.retracted_levels:
        deleted_at = bd.modified_at or datetime.now(UTC).isoformat()
        tombstone = _make_msg(
            encoder.encode({"uid": bd.uid, "deleted_at": deleted_at}).decode("utf-8")
        )
        for retracted in bd.retracted_levels:
            msg_by_level[retracted] = tombstone

    disconnected: set[SSEConnection] = set()
    for sse_conn in _sse_connections:
        try:
            if (
                exclude_device_id is not None
                and sse_conn.device_id == exclude_device_id
            ):
                continue
            if not _scope_matches(sse_conn, bd):
                continue
            level = entitled_level(
                sse_conn.user,
                obj_type=bd.obj_type,
                uid=bd.uid,
                country=bd.country,
                org_uids=bd.org_uids,
                obj_user_uid=bd.obj_user_uid,
            )
            msg = msg_by_level.get(level)
            if msg:
                sse_conn.queue.put_nowait(msg, key=(bd.obj_type, bd.uid))
                if (
                    sse_conn.tournament_uid is not None
                    and bd.obj_type == ObjectType.TOURNAMENT
                ):
                    sse_conn.needs_participant_refresh = True
                # Scoped (bot) connections only: low volume; full-corpus browser
                # connections would be far too noisy to log per-message.
                if sse_conn.tournament_uid is not None:
                    logger.info(
                        "SSE → %s: queued %s %s (%s)",
                        _conn_label(sse_conn),
                        bd.obj_type,
                        bd.uid,
                        level,
                    )
        except asyncio.QueueFull:
            logger.warning(
                "SSE queue full (%s), closing connection so client reconnects and "
                "catches up; dropped %s %s",
                _conn_label(sse_conn),
                bd.obj_type,
                bd.uid,
            )
            sse_conn.closed = True
            disconnected.add(sse_conn)
    _sse_connections.difference_update(disconnected)


async def broadcast_judge_call(
    *,
    tournament_uid: str,
    table: int,
    table_label: str | None,
    player_name: str,
    organizer_uids: list[str] | None = None,
) -> None:
    """Broadcast judge call to explicit organizers only (they are on premises)."""
    event_data = {
        "type": "judge_call",
        "data": {
            "tournament_uid": tournament_uid,
            "table": table,
            "table_label": table_label,
            "player_name": player_name,
        },
    }
    message = f"data: {encoder.encode(event_data).decode('utf-8')}\n\n"
    org_set = set(organizer_uids or [])
    disconnected: set[SSEConnection] = set()
    for conn in _sse_connections:
        if not conn.user:
            continue
        if conn.tournament_uid is not None and conn.tournament_uid != tournament_uid:
            continue
        if conn.user.uid in org_set:
            try:
                conn.queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(
                    "SSE queue full for judge_call (%s), closing connection",
                    _conn_label(conn),
                )
                conn.closed = True
                disconnected.add(conn)
    _sse_connections.difference_update(disconnected)


async def broadcast_resync(user_uid: str) -> None:
    event_data = {"type": "resync"}
    message = f"data: {encoder.encode(event_data).decode('utf-8')}\n\n"
    for conn in _sse_connections:
        if conn.user and conn.user.uid == user_uid:
            try:
                # Coalesce: a pending resync makes a second one redundant.
                conn.queue.put_nowait(message, key="__resync__")
            except asyncio.QueueFull:
                logger.warning(
                    f"SSE queue full for resync user {user_uid}, closing connection"
                )
                conn.closed = True


_LEVEL_PROJECTORS = {"public": compute_public, "member": compute_member}


def broadcast_personal(
    user_uid: str,
    *,
    obj_type: ObjectType,
    uid: str,
    full_dict: dict,
    country: str | None = None,
    org_uids: list[str] | None = None,
    obj_user_uid: str | None = None,
    modified_at: str | None = None,
    access_version: str | None = None,
) -> None:
    """Push ONE object to ONE user at their currently-entitled projection — the
    targeted counterpart to broadcast_precomputed. A None projection sends a
    tombstone so the client evicts the object. Browser connections only; scoped
    (bot) streams replay full state on every connect and never need this.
    """
    av = f',"av":"{access_version}"' if access_version else ""
    ts = f',"ts":"{modified_at}"' if modified_at else ""

    disconnected: set[SSEConnection] = set()
    for conn in _sse_connections:
        if conn.tournament_uid is not None or not (
            conn.user and conn.user.uid == user_uid
        ):
            continue
        level = entitled_level(
            conn.user,
            obj_type=obj_type,
            uid=uid,
            country=country,
            org_uids=org_uids,
            obj_user_uid=obj_user_uid,
        )
        proj = (
            compute_full(obj_type, full_dict)
            if level == "full"
            else _LEVEL_PROJECTORS[level](obj_type, full_dict)
        )
        if proj is None:
            # No entitlement at this level → evict the stale copy from the user's IDB.
            deleted_at = modified_at or datetime.now(UTC).isoformat()
            json_str = encoder.encode({"uid": uid, "deleted_at": deleted_at}).decode()
        else:
            json_str = encoder.encode(proj).decode()
        msg = f'data: {{"type":"{obj_type}","data":{json_str}{ts}{av}}}\n\n'
        try:
            conn.queue.put_nowait(msg, key=(obj_type, uid))
        except asyncio.QueueFull:
            logger.warning(
                "SSE queue full for personal push (%s), closing connection",
                _conn_label(conn),
            )
            conn.closed = True
            disconnected.add(conn)
    _sse_connections.difference_update(disconnected)
