"""Targeted organizer-view invalidation (205d).

When an organizer is removed, the old code forced a full resync. The new path
(_invalidate_organizer_view) instead pushes just the affected objects to just that user:
the tournament downgraded to member, and — the leak fix — a TOMBSTONE for each private
deck, whose member projection is null and so could never be evicted by the since-catch-up.
Both frames carry the recomputed access-version so the client doesn't resync at reconnect.
"""

import json
from datetime import UTC, datetime

import pytest
from src import db
from src.broadcast import SSEConnection, _sse_connections
from src.models import DeckObject, ObjectType, Tournament, User
from src.routes.tournaments import _invalidate_organizer_view

from tests.conftest import seed_tournament

NOW = datetime.now(UTC)
PUSH_TS = "2026-06-15T00:00:00"


async def _drain(conn: SSEConnection) -> dict[str, dict]:
    frames = {}
    while not conn.queue.empty():
        f = json.loads(conn.queue.get_nowait().removeprefix("data: ").strip())
        frames[f["type"]] = f
    return frames


@pytest.mark.asyncio
async def test_remove_organizer_tombstones_private_deck(test_db):
    org = User(uid="org-x", modified=NOW, name="Org", vekn_id="111")
    await db.save_user(org)
    # A private (non-public) deck owned by another player — its member projection is null.
    deck = DeckObject(
        uid="deck-x",
        modified=NOW,
        tournament_uid="trn-x",
        user_uid="other",
        public=False,
        cards={"Card": 1},
    )
    await db.save_object_from_model(ObjectType.DECK, deck)
    # The tournament AFTER removal: `org` is no longer an organizer.
    t = Tournament(uid="trn-x", modified=NOW, name="T", organizers_uids=[])
    bd = await seed_tournament(t)
    assert (
        bd.modified_at
    )  # self-heal invariant: the row was (re)written, modified_at moved

    conn = SSEConnection(user=org)
    _sse_connections.clear()
    _sse_connections.add(conn)
    try:
        await _invalidate_organizer_view(t, "org-x", PUSH_TS)
        frames = await _drain(conn)
    finally:
        _sse_connections.clear()
        async with db.get_connection() as c:
            await c.execute("DELETE FROM objects WHERE uid IN ('trn-x', 'deck-x')")

    # Tournament downgraded to member: the full-only checkin_code is gone; av rides along.
    assert "checkin_code" not in frames["tournament"]["data"]
    assert frames["tournament"]["av"]
    # Private deck evicted via tombstone — contents gone, deleted_at set.
    assert frames["deck"]["data"]["deleted_at"] == PUSH_TS
    assert "cards" not in frames["deck"]["data"]
    assert frames["deck"]["av"] == frames["tournament"]["av"]
