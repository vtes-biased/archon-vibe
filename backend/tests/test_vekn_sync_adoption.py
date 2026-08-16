"""A vekn.net event must never duplicate an event we already hold — legacy-
archon-merged events carry no vekn id, so the sync's lookup used to miss them
and insert a copy (double-visible, disagreeing results, and a rejected
duplicate calendar-create).
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4, uuid7

import pytest
import src.db as db
from src.models import Table, TableState, Tournament, TournamentState
from src.vekn_tournament_sync import _adopt_same_event


def _tournament(name: str, start: datetime, **overrides) -> Tournament:
    return Tournament(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name=name,
        start=start,
        state=TournamentState.FINISHED,
        # Rich copy: the rounds guard is what makes adoption safe (the sync then
        # refreshes metadata only and never overwrites play data).
        rounds=[[Table(seating=[], state=TableState.FINISHED)]],
        **overrides,
    )


@pytest.mark.asyncio
async def test_vekn_event_adopts_veknless_copy_instead_of_duplicating(test_db):
    name = f"Adoption {uuid4()}"
    start = datetime(2026, 10, 17, 16, 0, tzinfo=UTC)
    local = _tournament(name, start)
    async with db.get_connection() as conn:
        await db.save_tournament(local, conn=conn)

    # The sync builds its own row from vekn.net: same event, but the instant comes
    # from a guessed venue timezone — hours off, same day.
    incoming = _tournament(name, start - timedelta(hours=9))
    adopted = await _adopt_same_event(incoming, "13423")

    assert adopted is not None and adopted.uid == local.uid
    stored = await db.get_tournament_by_uid(local.uid)
    assert stored.external_ids["vekn"] == "13423"

    # Already linked to another event id: the local copies are a duplicate pair
    # only an operator can resolve, so refuse rather than steal the id.
    assert await _adopt_same_event(_tournament(name, start), "99999") is None


@pytest.mark.asyncio
async def test_no_adoption_when_name_and_day_are_not_unique(test_db):
    """Placeholder names cover many distinct events per day — never merge on
    one. Legacy imports share names like "Imported VTES Event" across hundreds
    of 2005 events; a vekn-less copy among same-day copies that already hold
    their own vekn ids must NOT be adopted."""
    name = f"Imported VTES Event {uuid4()}"
    day = datetime(2005, 5, 14, 8, 0, tzinfo=UTC)
    distinct = _tournament(name, day, external_ids={"vekn": "630"})
    veknless = _tournament(name, day + timedelta(hours=3))
    async with db.get_connection() as conn:
        await db.save_tournament(distinct, conn=conn)
        await db.save_tournament(veknless, conn=conn)

    assert await _adopt_same_event(_tournament(name, day), "1461") is None
    stored = await db.get_tournament_by_uid(veknless.uid)
    assert "vekn" not in stored.external_ids
