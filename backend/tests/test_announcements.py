"""The announcement list is capped at MAX_ANNOUNCEMENTS, newest kept.

Regression guard for the on-write prune. `announcements` is member-projected and
pushed to every participant over SSE, so the cap is what bounds that payload — a
broken slice (off-by-one, dropped prune, wrong end) would let the list grow
without limit. Asserts the persisted row produced by the real endpoint, not the
slice expression; imports the cap so it pins the invariant, not a copied number.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from src import db
from src.models import Tournament, User
from src.routes.tournaments import MAX_ANNOUNCEMENTS

from tests.conftest import make_auth_header

NOW = datetime.now(UTC)


@pytest.mark.asyncio
async def test_announcements_capped_keeping_newest(test_client: AsyncClient, test_db):
    org = User(uid="org-ann", modified=NOW, name="Olivia Organizer")
    await db.save_user(org)
    await db.save_tournament(
        Tournament(uid="trn-ann", modified=NOW, name="Cup", organizers_uids=["org-ann"])
    )
    try:
        n = MAX_ANNOUNCEMENTS + 5
        for i in range(n):
            resp = await test_client.post(
                "/api/tournaments/trn-ann/announce",
                json={"body": f"msg-{i}"},
                headers=make_auth_header("org-ann"),
            )
            assert resp.status_code == 200

        stored = await db.get_tournament_by_uid("trn-ann")
        bodies = [a.body for a in stored.announcements]
        assert len(bodies) == MAX_ANNOUNCEMENTS
        # The most recent N survive, oldest pruned.
        assert bodies == [f"msg-{i}" for i in range(n - MAX_ANNOUNCEMENTS, n)]
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE uid = 'trn-ann'")
