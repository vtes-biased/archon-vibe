"""A member's last login method cannot be removed.

Regression guarded: a VEKN record with no auth method reads as unclaimed, so a
removal that empties it hands the account to whoever claims the id or typed its
address. The refusal is the server's, asserted at the HTTP boundary against a
real DB — the profile hiding the button is UX only.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient
from src import db
from src.models import AuthMethod, AuthMethodType, User

from tests.conftest import make_auth_header


def _method(user_uid: str, method_type: AuthMethodType) -> AuthMethod:
    now = datetime.now(UTC)
    return AuthMethod(
        uid=str(uuid7()),
        modified=now,
        user_uid=user_uid,
        method_type=method_type,
        identifier=str(uuid7()),
        verified=True,
        created_at=now,
    )


@pytest.mark.asyncio
async def test_last_login_method_is_refused(test_client: AsyncClient, test_db):
    user = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Member")
    await db.save_user(user)
    passkey = _method(user.uid, AuthMethodType.PASSKEY)
    discord = _method(user.uid, AuthMethodType.DISCORD)
    await db.insert_auth_method(passkey)
    await db.insert_auth_method(discord)
    headers = make_auth_header(user.uid)

    resp = await test_client.delete(f"/auth/me/methods/{passkey.uid}", headers=headers)
    assert resp.status_code == 204

    resp = await test_client.delete(f"/auth/me/methods/{discord.uid}", headers=headers)
    assert resp.status_code == 409
    assert [m.uid for m in await db.get_auth_methods_for_user(user.uid)] == [
        discord.uid
    ]
