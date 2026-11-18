"""Tests for POST /auth/me/password — the in-session password change."""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from argon2 import PasswordHasher
from httpx import AsyncClient
from src import db
from src.accounts import reassign_auth_methods
from src.models import AuthMethod, AuthMethodType, User

from tests.conftest import make_auth_header


async def _password_user(email: str, password: str) -> str:
    now = datetime.now(UTC)
    user = User(uid=str(uuid7()), modified=now, name="Password")
    await db.save_user(user)
    await db.insert_auth_method(
        AuthMethod(
            uid=str(uuid7()),
            modified=now,
            user_uid=user.uid,
            method_type=AuthMethodType.EMAIL,
            identifier=email,
            credential_hash=PasswordHasher().hash(password),
            verified=True,
            created_at=now,
            last_used_at=now,
        )
    )
    return user.uid


@pytest.mark.asyncio
async def test_changed_password_is_what_login_reads(test_client: AsyncClient, test_db):
    session = make_auth_header(
        await _password_user("rotate@example.com", "original-secret")
    )

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
    assert accepted.status_code == 201

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
    survivor_uid = await _password_user("keep@example.com", "keep-secret")
    absorbed_uid = await _password_user("absorbed@example.com", "absorbed-secret")
    assert await reassign_auth_methods(absorbed_uid, survivor_uid) == 1

    changed = await test_client.post(
        "/auth/me/password",
        json={"password": "merged-secret"},
        headers=make_auth_header(survivor_uid),
    )
    assert changed.status_code == 204

    for email in ("keep@example.com", "absorbed@example.com"):
        accepted = await test_client.post(
            "/auth/login", json={"email": email, "password": "merged-secret"}
        )
        assert accepted.status_code == 201, email
