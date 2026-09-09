"""TWDA submission designer credit: the published entry credits the deck's typed
`attribution` and nothing else — a credit that names nobody must never leak a
name into an archive that keeps it forever.

Real DB, real engine, real (pinned) card data: every assertion below reads the
TWDA text that would be published, not an intermediate the code hands a stub.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid7

import pytest
from src import db
from src.db import TWDA_MIN_PLAYERS
from src.models import (
    AttributionKind,
    DeckAttribution,
    DeckObject,
    ObjectType,
    Player,
    Seat,
    Table,
    TableState,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    TwdaOutcome,
    User,
)
from src.routes.tournaments import _winner_deck_twda, maybe_submit_twda

from tests.conftest import seed_tournament

CREDIT = "Created by: "


def _user(uid: str, name: str, vekn_id: str = "") -> User:
    return User(
        uid=uid,
        modified=datetime(2025, 1, 1, tzinfo=UTC),
        name=name,
        vekn_id=vekn_id,
    )


@asynccontextmanager
async def _published(
    *,
    attribution: DeckAttribution,
    designer: User | None = None,
    winner_name: str = "Winner Wendy",
    winner_vekn: str = "1000001",
    seated: int = TWDA_MIN_PLAYERS,
):
    """Seed a finished event whose winner has a deck, and yield its TWDA text."""
    winner = _user(str(uuid7()), winner_name, winner_vekn)
    await db.save_user(winner)
    if designer:
        await db.save_user(designer)

    player_uids = [winner.uid] + [str(uuid7()) for _ in range(seated - 1)]
    for uid in player_uids[1:]:
        await db.save_user(_user(uid, f"Player {uid[:8]}", ""))

    seats = [Seat(player_uid=u) for u in player_uids]
    tournament = Tournament(
        uid=str(uuid7()),
        modified=datetime(2025, 6, 1, tzinfo=UTC),
        name="Test Tournament",
        format=TournamentFormat.Standard,
        # BASIC on purpose: rank (the Basic/NC/CC championship axis) must not gate
        # TWDA — the old rank!=BASIC check skipped every ordinary tournament.
        rank=TournamentRank.BASIC,
        state=TournamentState.FINISHED,
        start=datetime(2025, 6, 1, tzinfo=UTC),
        country="FR",
        external_ids={"vekn": "12345"},
        # What the backfill leaves on a vekn-bearing row: the submission keys on
        # the code, and the code of such a row is its vekn event id.
        event_code="12345",
        winner=winner.uid,
        players=[Player(user_uid=u) for u in player_uids],
        rounds=[
            [
                Table(seating=seats[i : i + 5], state=TableState.FINISHED)
                for i in range(0, len(seats), 5)
            ]
        ],
    )
    deck = DeckObject(
        uid=str(uuid7()),
        modified=datetime(2025, 6, 1, tzinfo=UTC),
        tournament_uid=tournament.uid,
        user_uid=winner.uid,
        name="My Deck",
        attribution=attribution,
        cards={"200001": 12, "100001": 10},
    )
    try:
        await seed_tournament(tournament)
        await db.save_object_from_model(ObjectType.DECK, deck)
        yield tournament, await _winner_deck_twda(tournament)
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE uid = %s", (deck.uid,))
            await conn.execute("DELETE FROM objects WHERE uid = %s", (tournament.uid,))


@pytest.mark.asyncio
async def test_place_line_spells_the_country_out(test_db):
    async with _published(attribution=DeckAttribution(kind=AttributionKind.OWNER)) as (
        _t,
        twda,
    ):
        assert twda.splitlines()[1] == "France"


@pytest.mark.asyncio
async def test_anonymous_credits_nobody(test_db):
    async with _published(
        attribution=DeckAttribution(kind=AttributionKind.ANONYMOUS)
    ) as (_t, twda):
        assert CREDIT not in twda


@pytest.mark.asyncio
async def test_own_deck_omits_the_credit(test_db):
    """Crediting the winner as their own designer is noise in the archive."""
    async with _published(attribution=DeckAttribution(kind=AttributionKind.OWNER)) as (
        _t,
        twda,
    ):
        assert CREDIT not in twda


@pytest.mark.asyncio
async def test_member_credit_resolves_the_current_name(test_db):
    """A member credit names that member now, not whatever was typed once."""
    designer = _user(str(uuid7()), "Designer Dave", "1000002")
    async with _published(
        attribution=DeckAttribution(kind=AttributionKind.MEMBER, vekn_id="1000002"),
        designer=designer,
    ) as (_t, twda):
        assert f"{CREDIT}Designer Dave" in twda


@pytest.mark.asyncio
async def test_member_credit_naming_nobody_credits_nobody(test_db):
    """An id no member holds names nobody — the typed credit keeps no free text
    to fall back on, which is the whole point of it."""
    async with _published(
        attribution=DeckAttribution(kind=AttributionKind.MEMBER, vekn_id="9999999")
    ) as (_t, twda):
        assert CREDIT not in twda


@pytest.mark.asyncio
async def test_named_non_member_is_credited_verbatim(test_db):
    async with _published(
        attribution=DeckAttribution(kind=AttributionKind.NAMED, name="Offline Designer")
    ) as (_t, twda):
        assert f"{CREDIT}Offline Designer" in twda


@pytest.mark.asyncio
async def test_archive_credit_passes_its_name_through(test_db):
    """A reconstructed TWDA entry carries its archived author verbatim."""
    async with _published(
        attribution=DeckAttribution(
            kind=AttributionKind.ARCHIVE, name="Archived Author"
        )
    ) as (_t, twda):
        assert f"{CREDIT}Archived Author" in twda


@pytest.mark.asyncio
async def test_below_participation_floor_skips_twda(test_db):
    """Under the floor the event never reaches the archive, and says why."""
    async with _published(
        attribution=DeckAttribution(kind=AttributionKind.ANONYMOUS),
        seated=TWDA_MIN_PLAYERS - 1,
    ) as (tournament, _twda):
        await maybe_submit_twda(tournament)
        stored = await db.get_tournament_by_uid(tournament.uid)
        assert stored is not None
        assert stored.twda_status is not None
        assert stored.twda_status.outcome == TwdaOutcome.SKIPPED
        assert stored.twda_status.reason == "too_few_players"
