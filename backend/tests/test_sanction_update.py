"""Regression tests for /sanctions endpoint invariants.

1. Level-only edit expiry validation. `_validate_expiry` used to run only inside
   `if expires_at is not None`, so editing *just the level* SUSPENSION->PROBATION
   skipped it and persisted a PROBATION with expires_at=None. That is not cosmetic:
   a null-expiry PROBATION reads as PERMANENTLY active in
   `user_has_active_suspension` (accounts.py — `expires_at is None` -> active
   forever), permanently blocking the member from abandoning their VEKN ID. The
   fix validates the resulting level+expires_at pair unconditionally.

2. One active DQ per player per tournament. A second concurrent DQ is meaningless
   and, once one is lifted, would strand the player zeroed with a FINISHED state.
   create now 409s on a duplicate.

Runs real: real Postgres, real route/auth, no engine (the DQ/SA recompute branches
are gated on the tournament existing, and the guards reject before reaching them).
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
import src.db as db
from src.models import (
    Player,
    PlayerState,
    Role,
    Sanction,
    SanctionCategory,
    SanctionLevel,
    Seat,
    Table,
    Tournament,
    TournamentState,
    User,
)

from tests.conftest import make_auth_header


@pytest.mark.asyncio
async def test_level_only_edit_to_probation_without_expiry_rejected(test_client):
    """SUSPENSION->PROBATION with no expires_at must 400 (not persist null expiry)."""
    ic = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Ethics Officer",
        roles=[Role.IC],
    )
    await db.save_user(ic)

    sanction = Sanction(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        user_uid=ic.uid,
        issued_by_uid=ic.uid,
        level=SanctionLevel.SUSPENSION,  # suspension may have a null expiry
        category=SanctionCategory.UNSPORTSMANLIKE_CONDUCT,
        description="test",
        issued_at=datetime.now(UTC),
        expires_at=None,
    )
    try:
        await db.save_sanction(sanction)

        resp = await test_client.put(
            f"/sanctions/{sanction.uid}",
            json={"level": "probation"},  # no expires_at in the body
            headers=make_auth_header(ic.uid),
        )
        assert resp.status_code == 400
        assert "expir" in resp.json()["detail"].lower()

        # The rejected row is unchanged: still SUSPENSION, still null expiry.
        stored = await db.get_sanction_by_uid(sanction.uid)
        assert stored.level == SanctionLevel.SUSPENSION
        assert stored.expires_at is None
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE type = 'sanction'")


@pytest.mark.asyncio
async def test_create_second_active_dq_rejected(test_client):
    """A second concurrent DQ for the same player+tournament must 409, not persist."""
    ic = User(uid=str(uuid7()), modified=datetime.now(UTC), name="IC", roles=[Role.IC])
    target = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Player")
    await db.save_user(ic)
    await db.save_user(target)

    tournament_uid = str(uuid7())
    existing = Sanction(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        user_uid=target.uid,
        issued_by_uid=ic.uid,
        tournament_uid=tournament_uid,
        level=SanctionLevel.DISQUALIFICATION,
        category=SanctionCategory.UNSPORTSMANLIKE_CONDUCT,
        description="first dq",
        issued_at=datetime.now(UTC),
    )
    try:
        await db.save_sanction(existing)

        resp = await test_client.post(
            "/sanctions/",
            json={
                "user_uid": target.uid,
                "level": "disqualification",
                "category": SanctionCategory.UNSPORTSMANLIKE_CONDUCT.value,
                "description": "second dq",
                "tournament_uid": tournament_uid,
            },
            headers=make_auth_header(ic.uid),
        )
        assert resp.status_code == 409

        # Still exactly one DQ for this player+tournament.
        dqs = [
            s
            for s in await db.get_sanctions_for_tournament(tournament_uid)
            if s.level == SanctionLevel.DISQUALIFICATION
        ]
        assert len(dqs) == 1
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE type = 'sanction'")


@pytest.mark.asyncio
async def test_dq_delete_restores_playable_state(test_client):
    """Deleting an active DQ mid-event returns the player to a PLAYABLE state
    (Playing while their table is live), not Finished/withdrawn — a
    fat-fingered DQ is fully reversible (reversibility over confirmation)."""
    ic = User(uid=str(uuid7()), modified=datetime.now(UTC), name="IC", roles=[Role.IC])
    target = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Player")
    await db.save_user(ic)
    await db.save_user(target)

    seat_uids = [target.uid, str(uuid7()), str(uuid7()), str(uuid7())]
    tournament = Tournament(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="DQ Restore",
        state=TournamentState.PLAYING,
        organizers_uids=[ic.uid],
        players=[
            Player(
                user_uid=uid,
                state=(
                    PlayerState.DISQUALIFIED
                    if uid == target.uid
                    else PlayerState.PLAYING
                ),
            )
            for uid in seat_uids
        ],
        rounds=[[Table(seating=[Seat(player_uid=uid) for uid in seat_uids])]],
    )
    sanction = Sanction(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        user_uid=target.uid,
        issued_by_uid=ic.uid,
        tournament_uid=tournament.uid,
        level=SanctionLevel.DISQUALIFICATION,
        category=SanctionCategory.UNSPORTSMANLIKE_CONDUCT,
        description="fat-fingered dq",
        issued_at=datetime.now(UTC),
    )
    try:
        async with db.get_connection() as conn:
            await db.save_tournament(tournament, conn=conn)
        await db.save_sanction(sanction)

        resp = await test_client.delete(
            f"/sanctions/{sanction.uid}", headers=make_auth_header(ic.uid)
        )
        assert resp.status_code == 200

        updated = await db.get_tournament_by_uid(tournament.uid)
        assert updated is not None
        entry = next(p for p in updated.players if p.user_uid == target.uid)
        assert entry.state == PlayerState.PLAYING
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE type = 'sanction'")
            await conn.execute("DELETE FROM objects WHERE uid = %s", (tournament.uid,))
