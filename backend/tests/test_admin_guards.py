"""Authorization guards for IC-only break-glass endpoints.

These endpoints are now exposed in the UI (profile Admin section + the offline
force-unlock button), so the role gate matters. The guard reads roles from the
DB user (get_current_user loads via get_user_by_uid), never from JWT claims —
these tests pin the 401/403 behaviour, not the underlying sync/unlock work.

Users are created explicitly (not mined from the randomized populated_db) so the
known-IC / known-non-IC selection is deterministic.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
import pytest_asyncio
import src.db as db
from httpx import AsyncClient
from src.models import Role, User

from tests.conftest import make_auth_header

ADMIN_SYNC_PATHS = [
    "/admin/sync-vekn",
    "/admin/sync-vekn-tournaments",
    "/admin/sync-twda-decks",
]
# Any path uid works: the IC gate fires before the tournament is ever loaded.
FORCE_UNLOCK = "/api/tournaments/00000000-0000-0000-0000-000000000000/force-unlock"


@pytest_asyncio.fixture
async def ic_user(test_db) -> User:
    u = User(
        uid=str(uuid7()), modified=datetime.now(UTC), name="IC Admin", roles=[Role.IC]
    )
    await db.save_user(u)
    return u


@pytest_asyncio.fixture
async def non_ic_user(test_db) -> User:
    u = User(
        uid=str(uuid7()), modified=datetime.now(UTC), name="Regular", roles=[Role.JUDGE]
    )
    await db.save_user(u)
    return u


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_SYNC_PATHS)
async def test_admin_sync_rejects_anonymous(test_client: AsyncClient, path):
    assert (await test_client.post(path)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ADMIN_SYNC_PATHS)
async def test_admin_sync_requires_ic(test_client: AsyncClient, non_ic_user, path):
    headers = make_auth_header(non_ic_user.uid)
    assert (await test_client.post(path, headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_admin_sync_vekn_allows_ic(test_client: AsyncClient, ic_user):
    """IC clears the role gate; no runner is registered in tests, so the handler
    reports 503 rather than 403 — proving IC passed the guard."""
    resp = await test_client.post(
        "/admin/sync-vekn", headers=make_auth_header(ic_user.uid)
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_force_unlock_rejects_anonymous(test_client: AsyncClient):
    assert (await test_client.post(FORCE_UNLOCK)).status_code == 401


@pytest.mark.asyncio
async def test_force_unlock_requires_ic(test_client: AsyncClient, non_ic_user):
    headers = make_auth_header(non_ic_user.uid)
    assert (await test_client.post(FORCE_UNLOCK, headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_force_unlock_allows_ic(test_client: AsyncClient, ic_user):
    """IC clears the role gate; the tournament doesn't exist, so the handler
    reports 404 rather than 403 — proving IC passed the guard."""
    resp = await test_client.post(FORCE_UNLOCK, headers=make_auth_header(ic_user.uid))
    assert resp.status_code == 404
