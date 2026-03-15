"""Tests for user API endpoints."""

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
        params={
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
async def test_list_users(test_client: AsyncClient, populated_db):
    """Test listing users via v1 API (requires auth)."""
    admin = next(
        u for u in populated_db
        if (Role.NC in u.roles or Role.PRINCE in u.roles) and u.vekn_id
    )
    response = await test_client.get(
        "/api/v1/users/", headers=make_auth_header(admin.uid)
    )

    assert response.status_code == 200
    users = response.json()

    # All users visible at member level
    assert len(users) == 400

    # Check structure of first user
    first_user = users[0]
    assert "uid" in first_user
    assert "name" in first_user
    assert "modified" in first_user


@pytest.mark.asyncio
async def test_get_user(test_client: AsyncClient, populated_db):
    """Test getting a specific user by UID via v1 API (requires auth)."""
    admin = next(
        u for u in populated_db
        if (Role.NC in u.roles or Role.PRINCE in u.roles) and u.vekn_id
    )
    # Target must have vekn_id to be visible at member level via v1 API
    test_uid = next(u.uid for u in populated_db if u.vekn_id)

    response = await test_client.get(
        f"/api/v1/users/{test_uid}", headers=make_auth_header(admin.uid)
    )

    assert response.status_code == 200
    user = response.json()
    assert user["uid"] == test_uid
    assert "name" in user
    assert "country" in user


@pytest.mark.asyncio
async def test_update_user(test_client: AsyncClient, populated_db):
    """Test updating a user's information (requires auth)."""
    # Find an admin who can update users (must have vekn_id for v1 API access)
    admin = next(
        u for u in populated_db
        if (Role.NC in u.roles or Role.PRINCE in u.roles) and u.vekn_id
    )
    # Target must have a vekn_id to be visible at member level
    target = next(u for u in populated_db if u.vekn_id and u.uid != admin.uid)
    headers = make_auth_header(admin.uid)

    # First get the user via v1 API
    response = await test_client.get(
        f"/api/v1/users/{target.uid}", headers=headers
    )
    assert response.status_code == 200
    original_user = response.json()

    # Update the user
    response = await test_client.put(
        f"/api/users/{target.uid}",
        params={
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
    assert updated_user["modified"] != original_user["modified"]


@pytest.mark.asyncio
async def test_create_user_requires_auth(test_client: AsyncClient, populated_db):
    """Test that creating a user without auth returns 401."""
    response = await test_client.post(
        "/api/users/",
        params={"name": "Test", "country": "US"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_user_requires_auth(test_client: AsyncClient, populated_db):
    """Test that updating a user without auth returns 401."""
    response = await test_client.put(
        f"/api/users/{populated_db[0].uid}",
        params={"name": "Nope"},
    )
    assert response.status_code == 401
