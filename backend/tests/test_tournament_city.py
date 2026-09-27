from datetime import UTC, datetime
from uuid import uuid7

import pytest
import src.db as db
from src.models import Role, User

from tests.conftest import make_auth_header

PARIS = 2988507


@pytest.mark.asyncio
async def test_in_person_event_needs_a_geonames_city(test_client):
    ic = User(uid=str(uuid7()), modified=datetime.now(UTC), name="IC", roles=[Role.IC])
    await db.save_user(ic)
    h = make_auth_header(ic.uid)
    event = {"name": "City", "start": "2026-10-10T10:00", "country": "FR"}
    created = None
    try:
        missing = await test_client.post("/api/tournaments/", json=event, headers=h)
        assert missing.status_code == 422

        abroad = event | {"city_geoname_id": 2692969}
        foreign = await test_client.post("/api/tournaments/", json=abroad, headers=h)
        assert foreign.status_code == 422

        named = event | {"city": "Lutetia", "city_geoname_id": PARIS}
        created = await test_client.post("/api/tournaments/", json=named, headers=h)
        assert created.status_code == 201
        assert (created.json()["city"], created.json()["city_geoname_id"]) == (
            "Paris",
            PARIS,
        )
    finally:
        async with db.get_connection() as conn:
            if created is not None and created.status_code == 201:
                await conn.execute(
                    "DELETE FROM objects WHERE uid = %s", (created.json()["uid"],)
                )
            await conn.execute("DELETE FROM objects WHERE uid = %s", (ic.uid,))
