"""A date-only field takes `YYYY-MM-DD` — what the frontend's date inputs send —
and stores naive midnight."""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient
from src import db
from src.models import Role, User

from tests.conftest import make_auth_header


@pytest.mark.asyncio
async def test_league_takes_a_date_only_start(test_client: AsyncClient, test_db):
    ic = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="IC",
        country="FR",
        roles=[Role.IC],
    )
    await db.save_user(ic)
    response = await test_client.post(
        "/api/leagues",
        json={"name": "Dated", "start": "2026-01-15", "finish": "2026-06-30"},
        headers=make_auth_header(ic.uid),
    )
    assert response.status_code == 201, response.text
    assert response.json()["start"] == "2026-01-15T00:00:00"
