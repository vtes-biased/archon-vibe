"""SSE broadcast system.

Owns the connection set and all broadcast functions. Imported directly by any
module that needs to push events — no monkey-patching required.
"""

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

# Distinct pending frames a per-connection queue holds before overflow→close.
# Each whole-tournament frame is ~300KB, so coalescing (below) already caps a
# stalled tournament viewer at ~1 frame; this just bounds the count of DISTINCT
# objects a stalled full-corpus browser can pile up. 100→30 as cheap insurance.
_SSE_QUEUE_MAXSIZE = 30


class CoalescingQueue:
    """Per-connection SSE queue that keeps only the LATEST frame per key.

    Tournament actions rebroadcast the WHOLE object, so a newer frame for a given
    (type, uid) fully supersedes any older one still pending. Keying object frames
    by (type, uid) and replacing in place bounds a stalled consumer to ~1 frame per
    distinct object (~300KB for a 400-player tournament) instead of a backlog of
    up-to-maxsize stale whole-object snapshots — the Peak-1 memory blowup. The
    consumer then drains *current* state, not a replay of superseded frames.

    Non-object events (resync, judge_call, shutdown wakeup) pass a distinct key so
    they are never coalesced away. `maxsize` counts DISTINCT pending keys and a put
    over the cap raises asyncio.QueueFull, so the existing overflow→close→reconnect
    valve is unchanged. Single-consumer / event-loop-only: no locking needed.
    """

    def __init__(self, maxsize: int = _SSE_QUEUE_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._items: OrderedDict[object, str] = OrderedDict()
        self._event = asyncio.Event()
        self._seq = 0

    def put_nowait(self, msg: str, *, key: object = None) -> None:
        """Enqueue `msg`. With `key`, an existing frame for that key is replaced in
        place (coalesced, keeping its FIFO position); without one, the frame gets a
        unique key and is never coalesced. Raises asyncio.QueueFull past maxsize."""
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
        _, msg = self._items.popitem(last=False)  # FIFO
        return msg

    def empty(self) -> bool:
        return not self._items


@dataclass(eq=False)
class SSEConnection:
    queue: CoalescingQueue = field(default_factory=CoalescingQueue)
    user: User | None = None
    # Set when the queue overflows: the SSE generator checks this and ends the
    # stream so the browser EventSource reconnects and runs a catch-up sync,
    # rather than staying OPEN on a queue that no longer receives events.
    closed: bool = False
    # Tournament-scoped connections (the Discord bot) receive ONLY events for
    # this tournament — its own object, its sanctions, and its judge calls —
    # instead of the whole corpus. None = unscoped (the browser's full sync).
    tournament_uid: str | None = None
    # The offline-lock device this browser identifies as (getDeviceId on the
    # client; None for the bot / pre-device clients). Lets a write self-exclude
    # the originating device from its own broadcast — see broadcast_precomputed's
    # exclude_device_id, used by go-online so the device doesn't receive the
    # offline_mode=false echo that races ahead of its own HTTP response.
    device_id: str | None = None
    # Scoped-only: the bot needs each seated participant's User identity
    # (name/nickname) to render seating, but _scope_matches drops generic user
    # broadcasts. So identities are pushed alongside the tournament: a tournament
    # delivery sets `needs_participant_refresh`, and the async live loop then
    # fetches+sends member-level user frames for participants not in
    # `sent_participant_uids` (broadcast_precomputed is sync + no-DB and can't
    # fetch here). The set is seeded by the scoped catch-up so steady-state
    # tournament events that add no players do zero DB work.
    sent_participant_uids: set[str] = field(default_factory=set)
    needs_participant_refresh: bool = False


_sse_connections: set[SSEConnection] = set()


def _conn_label(conn: SSEConnection) -> str:
    """Identify a connection in logs: user + scope (tournament uid or full corpus).

    Without this, overflow/close warnings can't be attributed to the bot vs a
    browser tab — exactly the ambiguity that made the bot SSE-listener wedge hard
    to diagnose from the backend logs.
    """
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
    """The projection level a viewer is entitled to for one object.

    Single source of truth for SSE access, shared by the live broadcast and the
    tournament-scoped catch-up (main.stream_updates). Returns "public",
    "member", or "full"; the caller maps that to its precomputed message or DB
    column. IC sees full; an NC sees full in their own country; explicit
    organizers see full for their tournaments; members see member (plus full for
    their own profile/decks); everyone else sees public.
    """
    if not viewer:
        return "public"
    if Role.IC in viewer.roles:
        return "full"
    # Promo inventory chain (IC→NC→organizer) is not country-scoped: NC sees the
    # full projection (holdings) for every promo. Princes/organizers stay member;
    # an organizer's own stock reaches them via their own User full projection.
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
            return "full"  # Own profile
        if obj_type == ObjectType.DECK and obj_user_uid == viewer.uid:
            return "full"  # Own deck
        return "member"
    return "public"


def _scope_matches(conn: SSEConnection, bd: BroadcastData) -> bool:
    """Whether a (possibly tournament-scoped) connection wants this object.

    Unscoped connections want everything. A scoped connection wants only its own
    tournament object and that tournament's sanctions — symmetric with the
    scoped catch-up (main._scoped_catchup_frames); other types (users, decks,
    leagues) are dropped.
    """
    if conn.tournament_uid is None:
        return True
    if bd.obj_type == ObjectType.TOURNAMENT:
        return bd.uid == conn.tournament_uid
    if bd.obj_type == ObjectType.SANCTION:
        return bd.tournament_uid == conn.tournament_uid
    return False


def _wake_sse_connections() -> None:
    """Wake up all SSE connections so they can check for shutdown."""
    for conn in list(_sse_connections):
        try:
            # Fixed key: repeat wakeups coalesce to one pending nudge.
            conn.queue.put_nowait("", key="__wake__")  # wake up the queue.get()
        except Exception:
            pass


def broadcast_precomputed(
    bd: BroadcastData, *, exclude_device_id: str | None = None
) -> None:
    """Broadcast pre-computed projections to SSE connections. No DB access.

    `exclude_device_id` skips every connection that identifies as that device —
    used by go-online so the initiating device doesn't receive the
    offline_mode=false echo of its own write (which would race ahead of the HTTP
    response and trip the client's lost-lock warning). Excludes the whole device,
    not one tab; offline mode is single-tab in practice (the WASM engine writes
    IndexedDB directly), so there's no sibling tab to starve of the update.
    """

    def _make_msg(json_str: str) -> str:
        # `ts` carries the authoritative modified_at so clients advance their
        # sync cursor in the same value space as the `since` catch-up filter.
        # NO `av` here: this is a per-LEVEL shared frame, but the fingerprint is
        # per-USER — only broadcast_personal (per-user) may carry `av`. A shared
        # frame's av would be wrong for some recipients → resync loop.
        ts = f',"ts":"{bd.modified_at}"' if bd.modified_at else ""
        return f'data: {{"type":"{bd.obj_type}","data":{json_str}{ts}}}\n\n'

    msg_by_level = {
        "public": _make_msg(bd.pub_json) if bd.pub_json else None,
        "member": _make_msg(bd.mem_json) if bd.mem_json else None,
        "full": _make_msg(bd.full_json) if bd.full_json else None,
    }

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
                # Coalesce by (type, uid): a newer whole-object frame supersedes
                # any older one still pending for the same object.
                sse_conn.queue.put_nowait(msg, key=(bd.obj_type, bd.uid))
                # A tournament delivery to the bot may carry new participants;
                # flag the live loop to push their identities (see SSEConnection).
                if (
                    sse_conn.tournament_uid is not None
                    and bd.obj_type == ObjectType.TOURNAMENT
                ):
                    sse_conn.needs_participant_refresh = True
                # Trace delivery to scoped (bot) connections only — low volume
                # (one tournament) and answers "did this event reach the bot?".
                # Full-corpus (browser) connections would be far too noisy.
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
    table_label: str,
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
    """Push a resync event to a specific user's SSE connection(s)."""
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
    """Push ONE object to ONE user at that user's *currently*-entitled projection.

    Targeted counterpart to broadcast_precomputed's per-level shared frame: it
    re-derives the user's entitled_level for this object NOW and sends the matching
    projection, so an entitlement transition (organizer add/remove) is delivered as
    a single targeted update with no full resync. If the entitled projection is None
    (e.g. a private deck once the viewer is no longer its organizer), a TOMBSTONE
    frame (deleted_at) is sent so the client evicts just that one object.
    `access_version`, when given, rides the frame so the client refreshes its stored
    fingerprint without a reconnect (else it would mismatch and resync needlessly).

    Browser (full-corpus) connections only — scoped (bot) streams replay full state
    on every connect and never need targeted invalidation.
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
