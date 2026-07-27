"""The tournament sync must not wipe a local registration list.

A tournament that has a vekn calendar entry but has not started a round yet
(in-app created, or a dedup survivor that just inherited the id) has real local
state — registered players — that vekn.net does not know about. VEKN is
authoritative for a round-less event it OWNS, not for one we own.
"""

from datetime import UTC, datetime
from uuid import uuid4, uuid7

import pytest
import src.db as db
from src.models import Player, PlayerState, Tournament, TournamentState
from src.vekn_tournament_sync import sync_all_tournaments


class _StubClient:
    """Yields one planned VEKN event; venue lookups are empty."""

    def __init__(self, event: dict) -> None:
        self._event = event

    async def fetch_all_events(self):
        yield self._event

    async def fetch_venue(self, venue_id):
        return {}


@pytest.mark.asyncio
async def test_sync_keeps_registered_players_on_a_roundless_local_event(test_db):
    uid = str(uuid7())
    player_uid = str(uuid7())
    event_id = str(uuid4().int % 100000)
    local = Tournament(
        uid=uid,
        modified=datetime.now(UTC),
        name="Tampere - Family Gathering II",
        start=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        state=TournamentState.REGISTRATION,
        external_ids={"vekn": event_id},
        players=[Player(user_uid=player_uid, state=PlayerState.REGISTERED)],
    )
    async with db.get_connection() as conn:
        await db.save_tournament(local, conn=conn)

    # vekn.net's view of the same event: a future calendar entry, no players.
    await sync_all_tournaments(
        _StubClient(
            {
                "event_id": event_id,
                "event_name": "Tampere - Family Gathering II",
                "event_startdate": "2026-08-29",
                "event_starttime": "12:00",
                "eventtype_id": 2,
                "rounds": 3,
                "players": [],
            }
        )
    )

    stored = await db.get_tournament_by_uid(uid)
    assert stored.state == TournamentState.REGISTRATION
    assert [p.user_uid for p in stored.players] == [player_uid]
