"""Table-label resolution (resolveTableLabelPy) and judge-call routing
(broadcast_judge_call, only explicit organizers receive).
"""

from datetime import UTC, datetime

from src.broadcast import SSEConnection, broadcast_judge_call
from src.models import (
    Role,
    Room,
    User,
)
from src.routes.tournaments import resolveTableLabelPy

NOW = datetime.now(UTC)


def _make_user(
    uid: str = "u1",
    name: str = "Alice",
    country: str = "FR",
    vekn_id: str | None = "1000001",
    roles: list[Role] | None = None,
) -> User:
    return User(
        uid=uid,
        modified=NOW,
        name=name,
        country=country,
        vekn_id=vekn_id,
        roles=roles or [],
    )


class TestResolveTableLabel:
    def test_no_rooms(self):
        assert resolveTableLabelPy([], 0) == "Table 1"
        assert resolveTableLabelPy([], 3) == "Table 4"

    def test_single_room(self):
        rooms = [Room(name="Main Hall", count=5)]
        assert resolveTableLabelPy(rooms, 0) == "Main Hall T1"
        assert resolveTableLabelPy(rooms, 4) == "Main Hall T5"

    def test_multiple_rooms(self):
        rooms = [Room(name="Room A", count=3), Room(name="Room B", count=4)]
        # Room A: indices 0,1,2
        assert resolveTableLabelPy(rooms, 0) == "Room A T1"
        assert resolveTableLabelPy(rooms, 2) == "Room A T3"
        # Room B: indices 3,4,5,6
        assert resolveTableLabelPy(rooms, 3) == "Room B T1"
        assert resolveTableLabelPy(rooms, 6) == "Room B T4"

    def test_index_beyond_rooms_falls_back(self):
        rooms = [Room(name="Small", count=2)]
        assert resolveTableLabelPy(rooms, 5) == "Table 6"


import pytest


@pytest.mark.asyncio
async def test_judge_call_only_sent_to_explicit_organizers():
    """Judge call SSE events must only reach explicit organizers of that tournament."""
    from src.main import _sse_connections

    organizer = SSEConnection(user=_make_user(uid="org1", roles=[]))
    ic_user = SSEConnection(user=_make_user(uid="ic1", roles=[Role.IC]))
    random_member = SSEConnection(user=_make_user(uid="random", roles=[]))
    no_user = SSEConnection(user=None)

    _sse_connections.clear()
    _sse_connections.update({organizer, ic_user, random_member, no_user})

    try:
        await broadcast_judge_call(
            tournament_uid="t1",
            table=2,
            table_label="Room A T3",
            player_name="Alice",
            organizer_uids=["org1"],
        )

        assert not organizer.queue.empty()
        assert ic_user.queue.empty()  # IC not paged unless an explicit organizer
        assert random_member.queue.empty()
        assert no_user.queue.empty()
    finally:
        _sse_connections.clear()


@pytest.mark.asyncio
async def test_judge_call_not_sent_to_other_tournament_organizer():
    """An organizer of tournament X should not get judge calls for tournament Y."""
    from src.main import _sse_connections

    other_org = SSEConnection(user=_make_user(uid="org-other", roles=[]))

    _sse_connections.clear()
    _sse_connections.add(other_org)

    try:
        await broadcast_judge_call(
            tournament_uid="t1",
            table=0,
            table_label="Table 1",
            player_name="Bob",
            organizer_uids=["org1"],
        )

        assert other_org.queue.empty()
    finally:
        _sse_connections.clear()
