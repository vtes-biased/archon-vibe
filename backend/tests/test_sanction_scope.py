"""A sanction's reach, asserted at the action endpoint: a DQ stops at the
tournament it was issued for, even for a league sibling, while an active VEKN
suspension bars entry to every tournament.
"""

from datetime import UTC, datetime, timedelta
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
    Tournament,
    TournamentState,
    User,
)

from tests.conftest import make_auth_header, seed_tournament


async def _actors() -> tuple[User, User]:
    ic = User(uid=str(uuid7()), modified=datetime.now(UTC), name="IC", roles=[Role.IC])
    target = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Player",
        vekn_id="1234567",
    )
    await db.save_user(ic)
    await db.save_user(target)
    return ic, target


async def _save_sanction(
    ic: User,
    target: User,
    level: SanctionLevel,
    tournament_uid: str | None,
) -> None:
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
            expires_at=(
                datetime.now(UTC) + timedelta(days=30)
                if level == SanctionLevel.SUSPENSION
                else None
            ),
        )
    )


async def _cleanup() -> None:
    async with db.get_connection() as conn:
        await conn.execute(
            "DELETE FROM objects WHERE type IN ('sanction', 'tournament')"
        )


@pytest.mark.asyncio
async def test_dq_does_not_bar_check_in_at_a_league_sibling(test_client):
    """Both leak paths land here: the retired league bar rejected the check-in
    outright, and a DQ left in the engine payload disqualifies the player again."""
    league_uid = str(uuid7())
    try:
        ic, target = await _actors()
        dq_event = Tournament(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            name="Where the DQ happened",
            state=TournamentState.FINISHED,
            organizers_uids=[ic.uid],
            league_uid=league_uid,
        )
        sibling = Tournament(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            name="Sibling",
            state=TournamentState.WAITING,
            organizers_uids=[ic.uid],
            league_uid=league_uid,
            players=[Player(user_uid=target.uid, state=PlayerState.REGISTERED)],
        )
        await seed_tournament(dq_event)
        await seed_tournament(sibling)
        await _save_sanction(ic, target, SanctionLevel.DISQUALIFICATION, dq_event.uid)

        resp = await test_client.post(
            f"/api/tournaments/{sibling.uid}/action",
            json={"type": "CheckIn", "player_uid": target.uid},
            headers=make_auth_header(ic.uid),
        )
        assert resp.status_code == 200, resp.text

        updated = await db.get_tournament_by_uid(sibling.uid)
        entry = next(p for p in updated.players if p.user_uid == target.uid)
        assert entry.state == PlayerState.CHECKED_IN
    finally:
        await _cleanup()


@pytest.mark.asyncio
async def test_active_suspension_bars_entry_to_any_tournament(test_client):
    try:
        ic, target = await _actors()
        other = Tournament(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            name="Elsewhere",
            state=TournamentState.REGISTRATION,
            organizers_uids=[ic.uid],
        )
        await seed_tournament(other)
        await _save_sanction(ic, target, SanctionLevel.SUSPENSION, None)

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
