"""Delete gate: an organizer deletes any non-Finished tournament (even with a
historical `external_ids.vekn`), Finished tournaments are IC-only, and an
offline-locked tournament is refused for everyone until unlocked.
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
async def test_delete_gate_organizer_unfinished_ic_finished_offline_blocked(
    test_client,
):
    org = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Org",
        roles=[Role.PRINCE],
        vekn_id="1000001",
    )
    ic = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="IC",
        roles=[Role.IC],
        vekn_id="1000003",
    )
    await db.save_user(org)
    await db.save_user(ic)

    unfinished_vekn = _tournament(
        org.uid, state=TournamentState.REGISTRATION, external_ids={"vekn": "12345"}
    )
    finished = _tournament(
        org.uid, state=TournamentState.FINISHED, external_ids={"vekn": "12346"}
    )
    offline_locked = _tournament(
        org.uid, state=TournamentState.PLAYING, offline_mode=True
    )

    for t in (unfinished_vekn, finished, offline_locked):
        async with db.get_connection() as conn:
            await db.save_tournament(t, conn=conn)

    try:
        org_h = make_auth_header(org.uid)
        ic_h = make_auth_header(ic.uid)

        ok = await test_client.delete(
            f"/api/tournaments/{unfinished_vekn.uid}", headers=org_h
        )
        assert ok.status_code == 200
        assert ok.json()["message"] == "Tournament deleted"

        denied = await test_client.delete(
            f"/api/tournaments/{finished.uid}", headers=org_h
        )
        assert denied.status_code == 403
        assert (await db.get_tournament_by_uid(finished.uid)).deleted_at is None

        ic_ok = await test_client.delete(
            f"/api/tournaments/{finished.uid}", headers=ic_h
        )
        assert ic_ok.status_code == 200

        locked = await test_client.delete(
            f"/api/tournaments/{offline_locked.uid}", headers=ic_h
        )
        assert locked.status_code == 400
        assert (await db.get_tournament_by_uid(offline_locked.uid)).deleted_at is None
    finally:
        async with db.get_connection() as conn:
            for t in (unfinished_vekn, finished, offline_locked):
                await conn.execute("DELETE FROM objects WHERE uid = %s", (t.uid,))


@pytest.mark.asyncio
async def test_delete_cascades_to_decks_and_sanctions(test_client):
    """Deleting a tournament tombstones its decks and sanctions too — otherwise
    they linger orphaned (a dangling DQ/SA on the player, a deck pointing at a
    gone event) in every client's IndexedDB."""
    ic = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="IC",
        roles=[Role.IC],
        vekn_id="1000002",
    )
    await db.save_user(ic)

    t = _tournament(ic.uid, state=TournamentState.FINISHED)
    deck = DeckObject(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        tournament_uid=t.uid,
        user_uid=ic.uid,
    )
    sanction = Sanction(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        user_uid=ic.uid,
        issued_by_uid=ic.uid,
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
            f"/api/tournaments/{t.uid}", headers=make_auth_header(ic.uid)
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
