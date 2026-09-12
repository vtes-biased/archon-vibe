"""The inbound sync never rewrites a linked tournament's name, finish or timezone."""

from datetime import UTC, datetime
from uuid import uuid4, uuid7

import pytest
import src.db as db
from src.models import Player, PlayerState, Tournament, TournamentState, User
from src.vekn_tournament_sync import sync_all_tournaments

LOCAL_NAME = "Tampere Open (renamed by the organizer)"
LOCAL_FINISH = datetime(2026, 8, 30, 20, 0)
LOCAL_TIMEZONE = "Pacific/Auckland"  # unguessable from the payload's FR venue


class _StubClient:
    """Yields both events of one cycle; venue lookups are empty."""

    def __init__(self, *events: dict) -> None:
        self._events = events

    async def fetch_all_events(self, probed=None):
        for event in self._events:
            yield event

    async def fetch_venue(self, venue_id):
        return {}


def _linked_local(event_id: str, **kwargs) -> Tournament:
    return Tournament(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name=LOCAL_NAME,
        start=datetime(2026, 8, 29, 12, 0),
        finish=LOCAL_FINISH,
        timezone=LOCAL_TIMEZONE,
        external_ids={"vekn": event_id},
        **kwargs,
    )


def _incoming(event_id: str, players: list[dict]) -> dict:
    return {
        "event_id": event_id,
        "event_name": "Tampere Open",
        "eventtype_id": "2",
        "event_startdate": "2026-08-29",
        "event_starttime": "12:00",
        "event_enddate": "2026-08-29",
        "event_endtime": "18:00",
        "venue_country": "FR",
        "venue_name": "Le Bar a Jeux",
        "rounds": "3",
        "players": players,
    }


@pytest.mark.asyncio
async def test_sync_keeps_the_app_owned_fields_on_both_merge_branches(test_db):
    player = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Known Player",
        vekn_id="1000001",
    )
    await db.save_user(player)

    # test_db wipes users only, so a fixed event id would make the second run
    # find run one's row and never touch the one just saved.
    refresh_id, rebuild_id = str(uuid4().int % 100000), str(uuid4().int % 100000)
    # Metadata-only refresh: local rounds exist, so VEKN speaks for metadata only.
    refreshed = _linked_local(refresh_id, rounds=[[]], state=TournamentState.PLAYING)
    # Round-less rebuild: no local rounds and the incoming event has players, so
    # the sync reconstructs the row from scratch.
    rebuilt = _linked_local(
        rebuild_id,
        state=TournamentState.REGISTRATION,
        players=[Player(user_uid=player.uid, state=PlayerState.REGISTERED)],
    )
    async with db.get_connection() as conn:
        await db.save_tournament(refreshed, conn=conn)
        await db.save_tournament(rebuilt, conn=conn)

    try:
        await sync_all_tournaments(
            _StubClient(
                _incoming(refresh_id, []),
                _incoming(
                    rebuild_id,
                    [
                        {
                            "pos": "1",
                            "veknid": "1000001",
                            "gw": "1",
                            "vp": "4",
                            "tp": "36",
                        }
                    ],
                ),
            )
        )

        for uid in (refreshed.uid, rebuilt.uid):
            stored = await db.get_tournament_by_uid(uid)
            assert stored.name == LOCAL_NAME
            assert stored.finish == LOCAL_FINISH
            assert stored.timezone == LOCAL_TIMEZONE
            # The vekn-owned half still refreshed, so each branch did run.
            assert stored.venue == "Le Bar a Jeux"
            assert stored.country == "FR"

        assert (await db.get_tournament_by_uid(rebuilt.uid)).winner == player.uid
    finally:
        async with db.get_connection() as conn:
            await conn.execute(
                "DELETE FROM objects WHERE uid = ANY(%s)",
                ([refreshed.uid, rebuilt.uid],),
            )
