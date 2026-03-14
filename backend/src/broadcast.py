"""SSE broadcast system.

Owns the connection set and all broadcast functions. Imported directly by any
module that needs to push events — no monkey-patching required.
"""

import asyncio
import logging
from dataclasses import dataclass, field

import msgspec

from .db import BroadcastData
from .models import DataLevel, ObjectType, Role, User

logger = logging.getLogger(__name__)

encoder = msgspec.json.Encoder()


@dataclass(eq=False)
class SSEConnection:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    user: User | None = None


_sse_connections: set[SSEConnection] = set()


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
        return f'data: {{"type":"{bd.obj_type}","data":{json_str}}}\n\n'

    pub_msg = _make_msg(bd.pub_json) if bd.pub_json else None
    mem_msg = _make_msg(bd.mem_json) if bd.mem_json else None
    full_msg = _make_msg(bd.full_json) if bd.full_json else None

    org_uids = bd.org_uids or []
    disconnected: set[SSEConnection] = set()
    for sse_conn in _sse_connections:
        try:
            viewer = sse_conn.user
            msg = None

            if not viewer:
                msg = pub_msg
            elif Role.IC in viewer.roles:
                msg = full_msg
            elif (
                (Role.NC in viewer.roles or Role.PRINCE in viewer.roles)
                and viewer.country
                and bd.country
                and viewer.country == bd.country
            ):
                msg = full_msg
            elif isinstance(org_uids, list) and viewer.uid in org_uids:
                msg = full_msg
            elif viewer.vekn_id:
                # Member level — but check personal overlay
                if bd.obj_type == ObjectType.USER and bd.uid == viewer.uid:
                    msg = full_msg  # Own profile
                elif bd.obj_type == ObjectType.DECK and bd.obj_user_uid == viewer.uid:
                    msg = full_msg  # Own deck
                else:
                    msg = mem_msg
            else:
                msg = pub_msg

            if msg:
                sse_conn.queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for connection, dropping")
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
    """Broadcast judge call to organizers and IC users only."""
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
        if Role.IC in conn.user.roles or conn.user.uid in org_set:
            try:
                conn.queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for judge_call, dropping")
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
                logger.warning(f"SSE queue full for resync user {user_uid}")
