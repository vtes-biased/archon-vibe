"""qr_checkin must never authorize check-in on an empty stored code.

Regression guard for the access-control hole: a migrated/legacy tournament that
slipped through with checkin_code='' would let an authenticated VEKN-ID holder
self-check-in with code='' (the old gate did a bare `request.code != code`, so
'' == '' passed), auto-registering them as a player. The empty-code guard returns
403 before delegating to the engine.
"""

from datetime import UTC, datetime

import pytest
from src import db
from src.models import Tournament, User

from tests.conftest import make_auth_header, seed_tournament

NOW = datetime.now(UTC)


@pytest.mark.asyncio
async def test_qr_checkin_rejects_empty_stored_code(test_client):
    await db.save_user(User(uid="qr-user-1", modified=NOW, name="Quinn Rider"))
    await seed_tournament(
        Tournament(uid="qr-trn-1", modified=NOW, name="Cup", checkin_code="")
    )
    try:
        resp = await test_client.post(
            "/api/tournaments/qr-trn-1/qr-checkin",
            json={"code": ""},
            headers=make_auth_header("qr-user-1"),
        )
        # An empty stored code must never authorize check-in, even when the
        # submitted code equals it exactly.
        assert resp.status_code == 403
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE uid = 'qr-trn-1'")
