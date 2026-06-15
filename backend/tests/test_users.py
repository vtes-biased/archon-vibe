"""Tests for user API endpoints."""

from datetime import datetime

import pytest
from httpx import AsyncClient
from src.models import Role

from tests.conftest import make_auth_header


@pytest.mark.asyncio
async def test_create_user(test_client: AsyncClient, populated_db):
    """Test creating a new user (requires IC/NC/Prince auth)."""
    # Find a user with NC or Prince role to act as creator
    admin = next(
        u for u in populated_db if Role.NC in u.roles or Role.PRINCE in u.roles
    )

    response = await test_client.post(
        "/api/users/",
        json={
            "name": "Test User",
            "country": "US",
            "city": "New York",
            "nickname": "testuser",
        },
        headers=make_auth_header(admin.uid),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["country"] == "US"
    assert data["city"] == "New York"
    assert data["nickname"] == "testuser"
    assert "uid" in data
    assert "modified" in data


@pytest.mark.asyncio
async def test_update_user(test_client: AsyncClient, populated_db):
    """Test updating a user's information (requires auth)."""
    # Find an admin who can update users
    admin = next(
        u for u in populated_db if Role.NC in u.roles or Role.PRINCE in u.roles
    )
    target = next(u for u in populated_db if u.uid != admin.uid)
    headers = make_auth_header(admin.uid)

    # Update the user
    response = await test_client.put(
        f"/api/users/{target.uid}",
        json={
            "name": "Updated Name",
            "country": "CA",
        },
        headers=headers,
    )

    assert response.status_code == 200
    updated_user = response.json()
    assert updated_user["uid"] == target.uid
    assert updated_user["name"] == "Updated Name"
    assert updated_user["country"] == "CA"
    assert datetime.fromisoformat(updated_user["modified"]) > target.modified


@pytest.mark.asyncio
async def test_role_change_resyncs_only_for_access_roles(
    test_client: AsyncClient, populated_db
):
    """Only NC/Prince/IC role changes set resync_after; other roles must not.

    Resync clears every client's IndexedDB and forces a snapshot re-fetch
    (~10s blank community page). Only NC/Prince/IC change what a user can see
    or is seen as, so only those warrant it. Granting a non-access role like PT
    must NOT trigger a resync. Guards the regression behind the resync fix.
    """
    from src import db

    # IC can change any role; target needs a vekn_id to be assigned roles.
    admin = next(u for u in populated_db if Role.IC in u.roles)
    target = next(
        u
        for u in populated_db
        if u.uid != admin.uid
        and u.vekn_id
        and not (set(u.roles) & {Role.NC, Role.PRINCE, Role.IC})
    )
    headers = make_auth_header(admin.uid)

    # Non-access role change (add PT) must NOT set resync_after.
    resp = await test_client.put(
        f"/api/users/{target.uid}",
        json={"roles": [*(r.value for r in target.roles), Role.PT.value]},
        headers=headers,
    )
    assert resp.status_code == 200
    after = await db.get_user_by_uid(target.uid)
    assert Role.PT in after.roles
    assert after.resync_after is None

    # Access role change (add Prince) MUST set resync_after.
    resp = await test_client.put(
        f"/api/users/{target.uid}",
        json={"roles": [*(r.value for r in after.roles), Role.PRINCE.value]},
        headers=headers,
    )
    assert resp.status_code == 200
    after = await db.get_user_by_uid(target.uid)
    assert Role.PRINCE in after.roles
    assert after.resync_after is not None


@pytest.mark.asyncio
async def test_create_user_requires_auth(test_client: AsyncClient, populated_db):
    """Test that creating a user without auth returns 401."""
    response = await test_client.post(
        "/api/users/",
        json={"name": "Test", "country": "US"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_user_requires_auth(test_client: AsyncClient, populated_db):
    """Test that updating a user without auth returns 401."""
    response = await test_client.put(
        f"/api/users/{populated_db[0].uid}",
        json={"name": "Nope"},
    )
    assert response.status_code == 401
