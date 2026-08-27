"""The delegated deck read answers each seated player's *own* deck slot.

Regression guarded: `DeckObject.round` is a per-player slot, not the
tournament's round index, and under open rounds the two diverge — players
progress through the pool independently, so two people seated in round 2 can be
on their 2nd and their 1st deck. Keying the lookup on the round index instead
reads the wrong deck, silently, and only for open-rounds events; a standard
event where everyone plays every round hides it completely.

Pins the delegated-deck-read contract: the endpoint answers each seated player's
own slot. Asserted at the HTTP boundary against a real DB and the real route.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient
from src import db
from src.models import (
    DeckObject,
    FinalsTable,
    ObjectType,
    Player,
    PlayerState,
    Seat,
    Table,
    TableState,
    Tournament,
    TournamentState,
    User,
)

from tests.conftest import make_auth_header, seed_tournament

NOW = datetime.now(UTC)
TRN = "trn-round-decks"
ORG = "org-round-decks"
# VETERAN played round 0 and is seated in round 1 — its 2nd deck.
# NEWCOMER joins at round 1 under open rounds — its 1st.
VETERAN = "player-veteran"
NEWCOMER = "player-newcomer"


async def _seed() -> None:
    for uid in (ORG, VETERAN, NEWCOMER):
        await db.save_user(User(uid=uid, modified=NOW, name=uid, vekn_id=None))
    await seed_tournament(
        Tournament(
            uid=TRN,
            modified=NOW,
            name="Open rounds",
            organizers_uids=[ORG],
            state=TournamentState.PLAYING,
            multideck=True,
            open_rounds=True,
            players=[
                Player(user_uid=VETERAN, state=PlayerState.PLAYING),
                Player(user_uid=NEWCOMER, state=PlayerState.PLAYING),
            ],
            rounds=[
                [
                    Table(
                        seating=[Seat(player_uid=VETERAN)],
                        state=TableState.FINISHED,
                    )
                ],
                [
                    Table(
                        seating=[Seat(player_uid=VETERAN), Seat(player_uid=NEWCOMER)],
                        state=TableState.IN_PROGRESS,
                    )
                ],
            ],
        )
    )
    for user_uid, slot in ((VETERAN, 0), (VETERAN, 1), (NEWCOMER, 0)):
        await db.save_object_from_model(
            ObjectType.DECK,
            DeckObject(
                uid=str(uuid7()),
                modified=NOW,
                tournament_uid=TRN,
                user_uid=user_uid,
                round=slot,
                name=f"{user_uid}-slot-{slot}",
            ),
        )


async def _drop() -> None:
    async with db.get_connection() as conn:
        await conn.execute(
            "DELETE FROM objects WHERE uid = %s OR \"full\"->>'tournament_uid' = %s",
            (TRN, TRN),
        )


@pytest.mark.asyncio
async def test_ongoing_round_answers_each_players_own_deck_slot(
    test_client: AsyncClient, test_db
):
    await _seed()
    try:
        resp = await test_client.get(
            f"/api/tournaments/{TRN}/decks", headers=make_auth_header(ORG)
        )
        assert resp.status_code == 200
        body = resp.json()

        # Only round 1 is In Progress.
        assert [r["round"] for r in body["rounds"]] == [1]
        names = sorted(d["name"] for d in body["rounds"][0]["decks"])
        assert names == [f"{NEWCOMER}-slot-0", f"{VETERAN}-slot-1"]
    finally:
        await _drop()


@pytest.mark.asyncio
async def test_an_ongoing_final_answers_the_registered_decks(
    test_client: AsyncClient, test_db
):
    """A final is a round, at index len(rounds). Dropping it left an online-play
    platform with nothing at the one moment it most needs the finalists' decks."""
    for uid in (ORG, VETERAN, NEWCOMER):
        await db.save_user(User(uid=uid, modified=NOW, name=uid, vekn_id=None))
    await seed_tournament(
        Tournament(
            uid=TRN,
            modified=NOW,
            name="With a final",
            organizers_uids=[ORG],
            state=TournamentState.PLAYING,
            players=[
                Player(user_uid=VETERAN, state=PlayerState.PLAYING),
                Player(user_uid=NEWCOMER, state=PlayerState.PLAYING),
            ],
            rounds=[
                [
                    Table(
                        seating=[Seat(player_uid=VETERAN), Seat(player_uid=NEWCOMER)],
                        state=TableState.FINISHED,
                    )
                ]
            ],
            finals=FinalsTable(
                seating=[Seat(player_uid=VETERAN), Seat(player_uid=NEWCOMER)],
                state=TableState.IN_PROGRESS,
                seed_order=[VETERAN, NEWCOMER],
            ),
        )
    )
    # Single-deck event: the registered deck carries no slot at all.
    for user_uid in (VETERAN, NEWCOMER):
        await db.save_object_from_model(
            ObjectType.DECK,
            DeckObject(
                uid=str(uuid7()),
                modified=NOW,
                tournament_uid=TRN,
                user_uid=user_uid,
                name=f"{user_uid}-registered",
            ),
        )
    try:
        resp = await test_client.get(
            f"/api/tournaments/{TRN}/decks", headers=make_auth_header(ORG)
        )
        assert resp.status_code == 200
        body = resp.json()

        assert [r["round"] for r in body["rounds"]] == [1]
        names = sorted(d["name"] for d in body["rounds"][0]["decks"])
        assert names == [f"{NEWCOMER}-registered", f"{VETERAN}-registered"]
    finally:
        await _drop()
