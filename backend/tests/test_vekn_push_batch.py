"""batch_push fail-fast behavior for unsynced members: a connection/auth
failure aborts the whole batch (reruns next cycle) instead of re-timing-out
every pending member serially; a per-item data error skips just that member.
"""

from datetime import UTC, datetime

import pytest
from src import db
from src.models import User
from src.vekn_api import VEKNAPIConnectionError, VEKNAPIError
from src.vekn_push import batch_push


def _member(uid: str, vekn_id: str) -> User:
    return User(
        uid=uid,
        modified=datetime(2025, 6, 1, tzinfo=UTC),
        name="Member",
        vekn_id=vekn_id,
        vekn_synced=False,
    )


class _FakeClient:
    """Minimal stand-in: batch_push only calls create_member."""

    def __init__(self, first_error: Exception | None) -> None:
        self.calls = 0
        self._first_error = first_error

    async def create_member(self, **_kw) -> None:
        self.calls += 1
        if self.calls == 1 and self._first_error is not None:
            raise self._first_error


@pytest.mark.asyncio
async def test_batch_push_aborts_on_connection_error(test_db, monkeypatch):
    monkeypatch.setenv("VEKN_PUSH", "true")
    await db.save_user(_member("m1", "1000001"))
    await db.save_user(_member("m2", "1000002"))

    client = _FakeClient(VEKNAPIConnectionError("vekn.net down"))
    stats = await batch_push(client)

    assert stats["aborted"] is True
    assert stats["members_pushed"] == 0
    # Second member is never attempted — that's the point of failing fast.
    assert client.calls == 1


@pytest.mark.asyncio
async def test_batch_push_skips_data_error_and_continues(test_db, monkeypatch):
    monkeypatch.setenv("VEKN_PUSH", "true")
    await db.save_user(_member("m1", "1000001"))
    await db.save_user(_member("m2", "1000002"))

    client = _FakeClient(VEKNAPIError("bad VEKN number"))
    stats = await batch_push(client)

    assert stats["aborted"] is False
    assert stats["members_pushed"] == 1
    assert stats["errors"] == 1
    assert client.calls == 2
