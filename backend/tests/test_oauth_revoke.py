"""`POST /oauth/revoke` hands a token pair back without the user's profile page.

Regression guarded: the endpoint has no in-repo client — it was removed once for
exactly that reason — so nothing else in the suite would notice it breaking. It
pins the two claims the access page makes for it: revoking one token kills the
whole rotation lineage, the pair it was rotated from included, and a token the
server does not know still answers 200 per RFC 7009.

Asserted at the HTTP boundary against a real DB and the real routes.
"""

from datetime import UTC, datetime
from uuid import uuid7

import jwt
import pytest
from httpx import AsyncClient
from src import db
from src.db_oauth import (
    get_oauth_token_by_jti,
    insert_oauth_client,
    upsert_oauth_consent,
)
from src.middleware.auth import JWT_ALGORITHM, JWT_SECRET
from src.models import OAuthClient, OAuthConsent, OAuthScope, User
from src.routes.oauth import _issue_token_pair, ph

CLIENT_SECRET = "s3cr3t-client-secret"


@pytest.mark.asyncio
async def test_revoke_kills_the_lineage_and_shrugs_at_an_unknown_token(
    test_client: AsyncClient, test_db
):
    user = User(
        uid=str(uuid7()), modified=datetime.now(UTC), name="Member", country="US"
    )
    await db.save_user(user)
    client = OAuthClient(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Third party",
        client_id=f"revoke-test-{uuid7()}",
        client_secret_hash=ph.hash(CLIENT_SECRET),
        redirect_uris=["https://example.test/cb"],
        scopes=[OAuthScope.PROFILE_READ],
        created_by_uid=user.uid,
    )
    await insert_oauth_client(client)
    await upsert_oauth_consent(
        OAuthConsent(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            user_uid=user.uid,
            client_id=client.client_id,
            scopes=[OAuthScope.PROFILE_READ],
        )
    )
    credentials = {"client_id": client.client_id, "client_secret": CLIENT_SECRET}

    first = await _issue_token_pair(
        user_uid=user.uid,
        client_id=client.client_id,
        scopes=[OAuthScope.PROFILE_READ],
        parent_token_uid=None,
    )
    response = await test_client.post(
        "/oauth/token",
        data=credentials
        | {"grant_type": "refresh_token", "refresh_token": first["refresh_token"]},
    )
    assert response.status_code == 200
    second = response.json()

    # Handing back one half of the rotated pair kills all four tokens.
    response = await test_client.post(
        "/oauth/revoke", data=credentials | {"token": second["refresh_token"]}
    )
    assert response.status_code == 200
    for label, pair in (("first", first), ("second", second)):
        for name in ("access_token", "refresh_token"):
            claims = jwt.decode(pair[name], JWT_SECRET, algorithms=[JWT_ALGORITHM])
            record = await get_oauth_token_by_jti(claims["jti"])
            assert record is not None and record.revoked, f"{label} {name}"

    # An unknown token is not an error, and neither is a token already revoked.
    for token in ("not-a-jwt", second["refresh_token"]):
        response = await test_client.post(
            "/oauth/revoke", data=credentials | {"token": token}
        )
        assert response.status_code == 200

    response = await test_client.post(
        "/oauth/revoke",
        data=credentials | {"client_secret": "wrong", "token": first["access_token"]},
    )
    assert response.status_code == 401
