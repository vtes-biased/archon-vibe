"""Reclassifying a local event to Storyline must strip its decklist state.

The metadata-refresh branch writes `format` with `msgspec.structs.replace`, which
carries every field it does not name — so the engine's Storyline coercion never
runs on this path. A checked-in player would keep a `missing_decklist` warning that
no upload can clear, the format refusing every deck.
"""

from datetime import UTC, datetime
from uuid import uuid4, uuid7

import pytest
import src.db as db
from src.models import (
    Player,
    PlayerState,
    Tournament,
    TournamentFormat,
    TournamentState,
)
from src.vekn_tournament_sync import sync_all_tournaments


class _StubClient:
    """Yields one VEKN event of type 9 (Storyline); venue lookups are empty."""

    def __init__(self, event: dict) -> None:
        self._event = event

    async def fetch_all_events(self, probed=None):
        yield self._event

    async def fetch_venue(self, venue_id):
        return {}


@pytest.mark.asyncio
async def test_sync_clears_decklist_state_when_reclassifying_to_storyline(test_db):
    uid = str(uuid7())
    player_uid = str(uuid7())
    event_id = str(uuid4().int % 100000)
    local = Tournament(
        uid=uid,
        modified=datetime.now(UTC),
        name="Tampere - Family Gathering II",
        start=datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        state=TournamentState.WAITING,
        format=TournamentFormat.Standard,
        decklist_required=True,
        external_ids={"vekn": event_id},
        players=[
            Player(
                user_uid=player_uid,
                state=PlayerState.CHECKED_IN,
                missing_decklist=True,
            )
        ],
    )
    async with db.get_connection() as conn:
        await db.save_tournament(local, conn=conn)

    await sync_all_tournaments(
        _StubClient(
            {
                "event_id": event_id,
                "event_name": "Tampere - Family Gathering II",
                "event_startdate": "2026-08-29",
                "event_starttime": "12:00",
                "eventtype_id": 9,
                "rounds": 3,
                "players": [],
            }
        )
    )

    stored = await db.get_tournament_by_uid(uid)
    assert stored.format == TournamentFormat.Storyline
    assert stored.decklist_required is False
    assert [p.missing_decklist for p in stored.players] == [False]
