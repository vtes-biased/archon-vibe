"""OAuth consent-management endpoints are first-party (session) only.

Regression guarded: a third-party app holding the member's own OAuth access
token must never be able to enumerate or revoke that member's grants to *other*
apps. Dropping the `_require_first_party` guard on either endpoint is a silent
lateral access-control hole (the app could list every app the user authorized,
and revoke a competitor's consent + kill its tokens). Nothing else in the suite
exercises OAuth-token access to these endpoints, so this is the only net.

Asserted at the HTTP boundary across the real auth middleware + routes against a
real DB — a behavior-preserving refactor of how the guard is implemented stays
green; only an actual loss of the boundary turns it red.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient

from src import db
from src.db_oauth import insert_oauth_token
from src.models import OAuthScope, OAuthToken, User
from src.routes.oauth import ACCESS_TOKEN_LIFETIME, _create_oauth_jwt

from tests.conftest import make_auth_header


@pytest.mark.asyncio
async def test_consent_management_rejects_third_party_oauth_token(
    test_client: AsyncClient, test_db
):
    user = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Member", country="US")
    await db.save_user(user)

    # A live third-party access token for this member, recorded so the
    # middleware's revocation check accepts it (profile:read → /oauth/* only).
    jti = str(uuid7())
    client_id = "third-party-app"
    await insert_oauth_token(
        OAuthToken(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            token_jti=jti,
            client_id=client_id,
            user_uid=user.uid,
            scopes=[OAuthScope.PROFILE_READ],
            token_type="access",
            expires_at=datetime.now(UTC) + ACCESS_TOKEN_LIFETIME,
        )
    )
    oauth_header = {
        "Authorization": "Bearer "
        + _create_oauth_jwt(
            user.uid, "access", [OAuthScope.PROFILE_READ], client_id, jti, ACCESS_TOKEN_LIFETIME
        )
    }

    # Positive control: the member's first-party session reaches the endpoint.
    assert (
        await test_client.get("/oauth/consents", headers=make_auth_header(user.uid))
    ).status_code == 200

    # The third-party OAuth token is refused on both list and revoke.
    assert (
        await test_client.get("/oauth/consents", headers=oauth_header)
    ).status_code == 403
    assert (
        await test_client.delete(f"/oauth/consents/{client_id}", headers=oauth_header)
    ).status_code == 403
