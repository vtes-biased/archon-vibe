"""A sanction's reach, asserted at the action endpoint: a DQ stops at the
tournament it was issued for — even a league sibling — while an active VEKN
suspension bars entry everywhere (wiki/tournaments.md, Sanctions).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
import src.db as db
from src.models import (
    PlayerState,
    Role,
    Sanction,
    SanctionCategory,
    SanctionLevel,
    Tournament,
    TournamentState,
    User,
)

from tests.conftest import make_auth_header, seed_tournament


async def _setup(level: SanctionLevel, tournament_uid: str | None, league_uid: str):
    ic = User(uid=str(uuid7()), modified=datetime.now(UTC), name="IC", roles=[Role.IC])
    target = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Player",
        vekn_id="1234567",
    )
    await db.save_user(ic)
    await db.save_user(target)

    other = Tournament(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Elsewhere",
        state=TournamentState.REGISTRATION,
        organizers_uids=[ic.uid],
        league_uid=league_uid,
    )
    await seed_tournament(other)
    await db.save_sanction(
        Sanction(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            user_uid=target.uid,
            issued_by_uid=ic.uid,
            tournament_uid=tournament_uid,
            level=level,
            category=SanctionCategory.UNSPORTSMANLIKE_CONDUCT,
            description="test",
            issued_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=30)
            if level == SanctionLevel.SUSPENSION
            else None,
        )
    )
    return ic, target, other


async def _cleanup():
    async with db.get_connection() as conn:
        await conn.execute(
            "DELETE FROM objects WHERE type IN ('sanction', 'tournament')"
        )


@pytest.mark.asyncio
async def test_dq_does_not_bar_entry_to_a_league_sibling(test_client):
    league_uid = str(uuid7())
    dq_tournament_uid = str(uuid7())
    try:
        ic, target, other = await _setup(
            SanctionLevel.DISQUALIFICATION, dq_tournament_uid, league_uid
        )
        resp = await test_client.post(
            f"/api/tournaments/{other.uid}/action",
            json={"type": "AddPlayer", "user_uid": target.uid},
            headers=make_auth_header(ic.uid),
        )
        assert resp.status_code == 200, resp.text

        updated = await db.get_tournament_by_uid(other.uid)
        entry = next(p for p in updated.players if p.user_uid == target.uid)
        assert entry.state != PlayerState.DISQUALIFIED
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_active_suspension_bars_entry_to_any_tournament(test_client):
    try:
        ic, target, other = await _setup(SanctionLevel.SUSPENSION, None, str(uuid7()))
        resp = await test_client.post(
            f"/api/tournaments/{other.uid}/action",
            json={"type": "AddPlayer", "user_uid": target.uid},
            headers=make_auth_header(ic.uid),
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "tournament.player_suspended"

        updated = await db.get_tournament_by_uid(other.uid)
        assert all(p.user_uid != target.uid for p in updated.players)
    finally:
        await _cleanup()
