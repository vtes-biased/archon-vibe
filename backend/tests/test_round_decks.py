"""The delegated deck read answers the deck stamped with the ongoing round.

Regression guarded: `DeckObject.round` used to be a per-player count of rounds
played, derived at upload. A mid-array `CancelRound` is a soft-cancel and that
count skips `Cancelled` rounds, so cancelling round 0 after round 1 was played
shifted every later slot down by one and the endpoint answered the previous
round's deck — silently, and only once a round had been voided.

Pins the delegated-deck-read contract: `round` on the wire and `DeckObject.round`
are one coordinate, and a voided round moves neither. Asserted at the HTTP
boundary against a real DB and the real route.
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
# VETERAN played round 0 and is seated in round 1; NEWCOMER joins at round 1
# under open rounds. Round 0 is then voided, which moves neither stamp.
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
                        state=TableState.CANCELLED,
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
    for user_uid, round_index in ((VETERAN, 0), (VETERAN, 1), (NEWCOMER, 1)):
        await db.save_object_from_model(
            ObjectType.DECK,
            DeckObject(
                uid=str(uuid7()),
                modified=NOW,
                tournament_uid=TRN,
                user_uid=user_uid,
                round=round_index,
                name=f"{user_uid}-round-{round_index}",
            ),
        )


async def _drop() -> None:
    async with db.get_connection() as conn:
        await conn.execute(
            "DELETE FROM objects WHERE uid = %s OR \"full\"->>'tournament_uid' = %s",
            (TRN, TRN),
        )


@pytest.mark.asyncio
async def test_a_voided_round_does_not_shift_the_answer(
    test_client: AsyncClient, test_db
):
    await _seed()
    try:
        resp = await test_client.get(
            f"/api/tournaments/{TRN}/decks", headers=make_auth_header(ORG)
        )
        assert resp.status_code == 200
        body = resp.json()

        # Only round 1 is In Progress. Round 0 is voided, so a count of rounds
        # played would answer VETERAN's round-0 deck here.
        assert [r["round"] for r in body["rounds"]] == [1]
        names = sorted(d["name"] for d in body["rounds"][0]["decks"])
        assert names == [f"{NEWCOMER}-round-1", f"{VETERAN}-round-1"]
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
