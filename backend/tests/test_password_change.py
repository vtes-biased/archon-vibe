"""Tests for POST /auth/me/password — the in-session password change."""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient
from src import db
from src.accounts import reassign_auth_methods
from src.models import User

from tests.conftest import make_auth_header


@pytest.mark.asyncio
async def test_changed_password_is_what_login_reads(test_client: AsyncClient, test_db):
    registered = await test_client.post(
        "/auth/register",
        json={
            "email": "Rotate@example.com",
            "password": "original-secret",
            "name": "Rotator",
        },
    )
    assert registered.status_code == 201
    session = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    changed = await test_client.post(
        "/auth/me/password",
        json={"password": "rotated-secret"},
        headers=session,
    )
    assert changed.status_code == 204

    accepted = await test_client.post(
        "/auth/login",
        json={"email": "rotate@example.com", "password": "rotated-secret"},
    )
    assert accepted.status_code == 200

    refused = await test_client.post(
        "/auth/login",
        json={"email": "rotate@example.com", "password": "original-secret"},
    )
    assert refused.status_code == 401


@pytest.mark.asyncio
async def test_no_email_credential_is_refused(test_client: AsyncClient, test_db):
    user = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Linkless")
    await db.save_user(user)

    response = await test_client.post(
        "/auth/me/password",
        json={"password": "no-credential-here"},
        headers=make_auth_header(user.uid),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_every_email_login_a_merge_left_behind_is_rewritten(
    test_client: AsyncClient, test_db
):
    async def _register(email: str, password: str) -> tuple[str, dict[str, str]]:
        response = await test_client.post(
            "/auth/register",
            json={"email": email, "password": password, "name": "Merged"},
        )
        assert response.status_code == 201
        session = {"Authorization": f"Bearer {response.json()['access_token']}"}
        me = await test_client.get("/auth/me", headers=session)
        return me.json()["user"]["uid"], session

    survivor_uid, survivor_session = await _register("keep@example.com", "keep-secret")
    absorbed_uid, _ = await _register("absorbed@example.com", "absorbed-secret")
    assert await reassign_auth_methods(absorbed_uid, survivor_uid) == 1

    changed = await test_client.post(
        "/auth/me/password",
        json={"password": "merged-secret"},
        headers=survivor_session,
    )
    assert changed.status_code == 204

    for email in ("keep@example.com", "absorbed@example.com"):
        accepted = await test_client.post(
            "/auth/login", json={"email": email, "password": "merged-secret"}
        )
        assert accepted.status_code == 200, email
