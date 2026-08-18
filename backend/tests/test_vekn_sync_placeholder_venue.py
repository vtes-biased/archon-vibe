"""The tournament sync must not take the placeholder venue for a location.

vekn.net's venue resource rejects POST, so an in-person event the app files is
filed against the generic placeholder venue, which reads back as an Antarctic
address. Taking it at face value moved a Budapest national qualifier to
Antarctica within the hour and undid the organizer's re-entry on every run.
"""

from datetime import UTC, datetime
from uuid import uuid4, uuid7

import pytest
import src.db as db
from src.models import Tournament, TournamentState
from src.vekn_api import PLACEHOLDER_VENUE_ID, PLACEHOLDER_VENUE_NAME
from src.vekn_tournament_sync import sync_all_tournaments


class _StubClient:
    """Yields one event filed against the placeholder venue, whose lookup — if it
    ever happened — would answer Antarctica."""

    def __init__(self, event: dict) -> None:
        self._event = event

    async def fetch_all_events(self):
        yield self._event

    async def fetch_venue(self, venue_id):
        return {"city": "Antarctica", "address": "Antarctica", "country": "AQ"}


@pytest.mark.asyncio
async def test_sync_keeps_the_local_location_of_an_app_filed_event(test_db):
    uid = str(uuid7())
    event_id = str(uuid4().int % 100000)
    local = Tournament(
        uid=uid,
        modified=datetime.now(UTC),
        name="Budapest NQ",
        start=datetime(2026, 9, 12, 10, 0),
        state=TournamentState.REGISTRATION,
        external_ids={"vekn": event_id},
        country="HU",
        timezone="Europe/Budapest",
        venue="Sárkány Klub",
        venue_url="https://example.hu/klub",
        address="Váci út 1, Budapest",
        map_url="https://www.google.com/maps/search/?api=1&query=47.5,19.05",
    )
    async with db.get_connection() as conn:
        await db.save_tournament(local, conn=conn)

    # vekn.net's view of the same event: renamed there, on the placeholder venue.
    await sync_all_tournaments(
        _StubClient(
            {
                "event_id": event_id,
                "event_name": "Budapest NQ 2026",
                "event_startdate": "2026-09-12",
                "event_starttime": "10:00",
                "eventtype_id": 2,
                "rounds": 3,
                "venue_id": str(PLACEHOLDER_VENUE_ID),
                "venue_name": PLACEHOLDER_VENUE_NAME,
                "venue_country": "AQ",
                "players": [],
            }
        )
    )

    stored = await db.get_tournament_by_uid(uid)
    assert stored.name == "Budapest NQ 2026"  # the refresh did run
    assert (stored.country, stored.timezone) == ("HU", "Europe/Budapest")
    assert stored.venue == "Sárkány Klub"
    assert stored.venue_url == "https://example.hu/klub"
    assert stored.address == "Váci út 1, Budapest"
    assert stored.map_url.endswith("47.5,19.05")
