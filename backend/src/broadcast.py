"""SSE broadcast system.

Owns the connection set and all broadcast functions. Imported directly by any
module that needs to push events — no monkey-patching required.
"""

import asyncio
import logging
from dataclasses import dataclass, field

import msgspec

from .db import BroadcastData
from .models import ObjectType, Role, User

logger = logging.getLogger(__name__)

encoder = msgspec.json.Encoder()


@dataclass(eq=False)
class SSEConnection:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    user: User | None = None
    # Set when the queue overflows: the SSE generator checks this and ends the
    # stream so the browser EventSource reconnects and runs a catch-up sync,
    # rather than staying OPEN on a queue that no longer receives events.
    closed: bool = False
    # Tournament-scoped connections (the Discord bot) receive ONLY events for
    # this tournament — its own object, its sanctions, and its judge calls —
    # instead of the whole corpus. None = unscoped (the browser's full sync).
    tournament_uid: str | None = None
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
    column. IC sees full; NC/Prince see full in their own country; explicit
    organizers see full for their tournaments; members see member (plus full for
    their own profile/decks); everyone else sees public.
    """
    if not viewer:
        return "public"
    if Role.IC in viewer.roles:
        return "full"
    if (
        (Role.NC in viewer.roles or Role.PRINCE in viewer.roles)
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
            conn.queue.put_nowait("")  # Empty message to wake up the queue.get()
        except Exception:
            pass


def broadcast_precomputed(bd: BroadcastData) -> None:
    """Broadcast pre-computed projections to SSE connections. No DB access."""

    def _make_msg(json_str: str) -> str:
        # `ts` carries the authoritative modified_at so clients advance their
        # sync cursor in the same value space as the `since` catch-up filter.
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
                sse_conn.queue.put_nowait(msg)
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
                conn.queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(
                    f"SSE queue full for resync user {user_uid}, closing connection"
                )
                conn.closed = True
