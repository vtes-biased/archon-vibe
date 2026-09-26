"""`/oauth/userinfo` hands out a verified address only under `profile:email`.

A client keys accounts on what it gets here, so an unverified address — the
self-edited `contact_email` or an unconfirmed password signup — would hand one
member's account elsewhere to whoever typed their address. Asserted at the HTTP
boundary against a real DB.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient
from src import db
from src.db_oauth import insert_oauth_token
from src.models import AuthMethod, AuthMethodType, OAuthScope, OAuthToken, User
from src.routes.oauth import ACCESS_TOKEN_LIFETIME, _create_oauth_jwt

NOW = datetime.now(UTC)


async def _token(user_uid: str, scopes: list[OAuthScope]) -> dict[str, str]:
    jti = str(uuid7())
    await insert_oauth_token(
        OAuthToken(
            uid=str(uuid7()),
            modified=NOW,
            token_jti=jti,
            client_id="forum",
            user_uid=user_uid,
            scopes=scopes,
            token_type="access",
            expires_at=NOW + ACCESS_TOKEN_LIFETIME,
        )
    )
    jwt = _create_oauth_jwt(
        user_uid, "access", scopes, "forum", jti, ACCESS_TOKEN_LIFETIME, None
    )
    return {"Authorization": f"Bearer {jwt}"}


async def _method(user_uid: str, kind: AuthMethodType, ident: str, **kw) -> None:
    await db.insert_auth_method(
        AuthMethod(
            uid=str(uuid7()),
            modified=NOW,
            user_uid=user_uid,
            method_type=kind,
            identifier=ident,
            **kw,
        )
    )


async def _email(test_client: AsyncClient, user_uid: str, scopes) -> str | None:
    resp = await test_client.get(
        "/oauth/userinfo", headers=await _token(user_uid, scopes)
    )
    assert resp.status_code == 200
    return resp.json().get("email")


@pytest.mark.asyncio
async def test_userinfo_email_is_verified_and_scoped(test_client: AsyncClient):
    await db.save_user(
        User(uid="m-mail", modified=NOW, name="M", contact_email="record@x.test")
    )
    await _method("m-mail", AuthMethodType.EMAIL, "typed@x.test", verified=False)
    await _method(
        "m-mail", AuthMethodType.DISCORD, "123", verified=True, email="disc@x.test"
    )
    assert await _email(test_client, "m-mail", [OAuthScope.PROFILE_READ]) is None
    email_scope = [OAuthScope.PROFILE_EMAIL]
    assert await _email(test_client, "m-mail", email_scope) == "disc@x.test"

    await _method("m-mail", AuthMethodType.EMAIL, "login@x.test", verified=True)
    assert await _email(test_client, "m-mail", email_scope) == "login@x.test"

    await db.save_user(
        User(uid="m-record", modified=NOW, name="R", contact_email="only@x.test")
    )
    assert await _email(test_client, "m-record", email_scope) is None
