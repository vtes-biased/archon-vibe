"""Tests for PATCH /auth/me profile update — community_links security boundary."""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from uuid6 import uuid7

from src import db
from src.models import Role, User
from tests.conftest import make_auth_header


async def _insert_user(roles: list[Role], **kwargs) -> User:
    """Insert a user with given roles and return it."""
    uid = str(uuid7())
    user = User(
        uid=uid, modified=datetime.now(UTC), name="Test User",
        country="FR", roles=roles, **kwargs,
    )
    await db.insert_user(user)
    return user


@pytest.mark.asyncio
async def test_non_member_cannot_set_community_links(
    test_client: AsyncClient, test_db
):
    """User without VEKN ID gets 403 when trying to set community_links."""
    user = await _insert_user(roles=[])
    response = await test_client.patch(
        "/auth/me",
        json={
            "community_links": [
                {"type": "discord", "url": "https://discord.gg/test", "label": "Test"}
            ]
        },
        headers=make_auth_header(user.uid),
    )
    assert response.status_code == 403
    assert "vekn" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_nc_can_set_community_links(test_client: AsyncClient, test_db):
    """NC user can successfully set community_links via PATCH /me."""
    user = await _insert_user(roles=[Role.NC], vekn_id="1000001")
    response = await test_client.patch(
        "/auth/me",
        json={
            "community_links": [
                {"type": "discord", "url": "https://discord.gg/vtes", "label": "VTES"},
                {"type": "website", "url": "https://vtes.example.com"},
            ]
        },
        headers=make_auth_header(user.uid),
    )
    assert response.status_code == 200
    data = response.json()
    links = data["user"]["community_links"]
    assert len(links) == 2
    assert links[0]["type"] == "discord"
    assert links[0]["url"] == "https://discord.gg/vtes"
    assert links[1]["type"] == "website"


@pytest.mark.asyncio
async def test_community_links_invalid_type_rejected(
    test_client: AsyncClient, test_db
):
    """Invalid link type returns 422."""
    user = await _insert_user(roles=[Role.NC], vekn_id="1000002")
    response = await test_client.patch(
        "/auth/me",
        json={
            "community_links": [
                {"type": "myspace", "url": "https://myspace.com/test"}
            ]
        },
        headers=make_auth_header(user.uid),
    )
    assert response.status_code == 422
    assert "invalid link type" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_community_links_bad_url_rejected(test_client: AsyncClient, test_db):
    """URL without http(s) scheme returns 422."""
    user = await _insert_user(roles=[Role.NC], vekn_id="1000003")
    response = await test_client.patch(
        "/auth/me",
        json={
            "community_links": [
                {"type": "discord", "url": "ftp://discord.gg/test"}
            ]
        },
        headers=make_auth_header(user.uid),
    )
    assert response.status_code == 422
    assert "invalid url" in response.json()["detail"].lower()
