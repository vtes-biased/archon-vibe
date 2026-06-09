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
