"""Tests for user API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_user(test_client: AsyncClient):
    """Test creating a new user."""
    response = await test_client.post(
        "/users/",
        params={
            "name": "Test User",
            "country": "US",
            "city": "New York",
            "nickname": "testuser",
            "roles": ["Judge", "Prince"],
        },
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["country"] == "US"
    assert data["city"] == "New York"
    assert data["nickname"] == "testuser"
    assert "Judge" in data["roles"]
    assert "Prince" in data["roles"]
    assert "uid" in data
    assert "modified" in data


@pytest.mark.asyncio
async def test_list_users(test_client: AsyncClient, populated_db):
    """Test listing users with pagination."""
    response = await test_client.get("/users/")
    
    assert response.status_code == 200
    users = response.json()
    
    # Should have all 400 users
    assert len(users) == 400
    
    # Check structure of first user
    first_user = users[0]
    assert "uid" in first_user
    assert "name" in first_user
    assert "modified" in first_user


@pytest.mark.asyncio
async def test_get_user(test_client: AsyncClient, populated_db):
    """Test getting a specific user by UID."""
    # Use the first user from populated data
    test_uid = populated_db[0].uid
    
    response = await test_client.get(f"/users/{test_uid}")
    
    assert response.status_code == 200
    user = response.json()
    assert user["uid"] == test_uid
    assert "name" in user
    assert "country" in user


@pytest.mark.asyncio
async def test_update_user(test_client: AsyncClient, populated_db):
    """Test updating a user's information."""
    # Use the first user from populated data
    test_uid = populated_db[0].uid
    
    # First get the user
    response = await test_client.get(f"/users/{test_uid}")
    assert response.status_code == 200
    original_user = response.json()
    
    # Update the user
    response = await test_client.put(
        f"/users/{test_uid}",
        params={
            "name": "Updated Name",
            "country": "CA",
        },
    )
    
    assert response.status_code == 200
    updated_user = response.json()
    assert updated_user["uid"] == test_uid
    assert updated_user["name"] == "Updated Name"
    assert updated_user["country"] == "CA"
    assert updated_user["modified"] != original_user["modified"]  # Modified timestamp should change

