"""Judge-call routing: broadcast_judge_call reaches only explicit organizers."""

from datetime import UTC, datetime

import pytest
from src.broadcast import SSEConnection, broadcast_judge_call
from src.models import Role, User

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
            table_label="Room A 3",
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
            table_label=None,
            player_name="Bob",
            organizer_uids=["org1"],
        )

        assert other_org.queue.empty()
    finally:
        _sse_connections.clear()
