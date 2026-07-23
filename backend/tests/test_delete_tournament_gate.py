"""Delete gate: a tournament is deletable at any state until it has a VEKN
footprint, then never (deleting here would orphan the vekn.net record — VEKN is
the system of record). One test over the whole gate: an unpushed non-PLANNED
event deletes; either VEKN signal (external_ids.vekn OR vekn_pushed_at) blocks it.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
import src.db as db
from src.models import (
    DeckObject,
    ObjectType,
    Role,
    Sanction,
    SanctionCategory,
    SanctionLevel,
    Tournament,
    TournamentState,
    User,
)

from tests.conftest import make_auth_header


def _tournament(org_uid: str, **overrides) -> Tournament:
    fields = {
        "uid": str(uuid7()),
        "modified": datetime.now(UTC),
        "name": "Gate",
        "state": TournamentState.REGISTRATION,
        "organizers_uids": [org_uid],
        **overrides,
    }
    return Tournament(**fields)


@pytest.mark.asyncio
async def test_delete_gated_by_vekn_footprint_not_state(test_client):
    org = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Org",
        roles=[Role.PRINCE],
        vekn_id="1000001",
    )
    await db.save_user(org)

    # Unpushed, past PLANNED — previously blocked (state != PLANNED), now deletable.
    unpushed = _tournament(org.uid, state=TournamentState.REGISTRATION)
    # Pushed via a live calendar event id: deleting would orphan vekn.net.
    has_event = _tournament(org.uid, external_ids={"vekn": "12345"})
    # Pushed via results upload: the other VEKN signal in the OR gate.
    has_results = _tournament(org.uid, vekn_pushed_at=datetime.now(UTC))

    for t in (unpushed, has_event, has_results):
        async with db.get_connection() as conn:
            await db.save_tournament(t, conn=conn)

    try:
        h = make_auth_header(org.uid)

        ok = await test_client.delete(f"/api/tournaments/{unpushed.uid}", headers=h)
        assert ok.status_code == 200
        assert ok.json()["message"] == "Tournament deleted"

        for t in (has_event, has_results):
            blocked = await test_client.delete(f"/api/tournaments/{t.uid}", headers=h)
            assert blocked.status_code == 400
            assert (await db.get_tournament_by_uid(t.uid)).deleted_at is None
    finally:
        async with db.get_connection() as conn:
            for t in (unpushed, has_event, has_results):
                await conn.execute("DELETE FROM objects WHERE uid = %s", (t.uid,))


@pytest.mark.asyncio
async def test_delete_cascades_to_decks_and_sanctions(test_client):
    """Deleting a tournament tombstones its decks and sanctions too — otherwise
    they linger orphaned (a dangling DQ/SA on the player, a deck pointing at a
    gone event) in every client's IndexedDB."""
    org = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Org",
        roles=[Role.PRINCE],
        vekn_id="1000002",
    )
    await db.save_user(org)

    t = _tournament(org.uid, state=TournamentState.FINISHED)
    deck = DeckObject(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        tournament_uid=t.uid,
        user_uid=org.uid,
    )
    sanction = Sanction(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        user_uid=org.uid,
        issued_by_uid=org.uid,
        tournament_uid=t.uid,
        level=SanctionLevel.WARNING,
        category=SanctionCategory.PROCEDURAL_ERROR,
        description="gate cascade",
        issued_at=datetime.now(UTC),
    )
    async with db.get_connection() as conn:
        await db.save_tournament(t, conn=conn)
    await db.save_object_from_model(ObjectType.DECK, deck)
    await db.save_sanction(sanction)

    try:
        resp = await test_client.delete(
            f"/api/tournaments/{t.uid}", headers=make_auth_header(org.uid)
        )
        assert resp.status_code == 200

        async with db.get_connection() as conn:
            for uid in (deck.uid, sanction.uid):
                row = await (
                    await conn.execute(
                        "SELECT deleted_at FROM objects WHERE uid = %s", (uid,)
                    )
                ).fetchone()
                assert row[0] is not None, f"{uid} not tombstoned"
    finally:
        async with db.get_connection() as conn:
            for uid in (t.uid, deck.uid, sanction.uid):
                await conn.execute("DELETE FROM objects WHERE uid = %s", (uid,))
