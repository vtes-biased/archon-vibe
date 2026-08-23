"""`GET /oauth/authorize` hands back a URL, never an HTTP redirect.

Regression guarded: the consent page calls this endpoint from `fetch` with a
Bearer token, and a fetch cannot read `Location` off a redirect — with
`redirect: "manual"` the response is opaque, its header list empty. When this
returned a 302 the page navigated to the empty string, which reloads the consent
page, which calls this again: a returning user with consent already on file
looped forever instead of being sent back to the app.
"""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from uuid import uuid7

import pytest
from httpx import AsyncClient
from src import db
from src.db_oauth import insert_oauth_client, upsert_oauth_consent
from src.models import OAuthClient, OAuthConsent, OAuthScope, User

from tests.conftest import make_auth_header

REDIRECT_URI = "https://rulings.krcg.org/login/callback"


async def _client_and_user(scopes: list[OAuthScope]) -> tuple[str, User]:
    user = User(
        uid=str(uuid7()), modified=datetime.now(UTC), name="Member", country="US"
    )
    await db.save_user(user)
    client_id = str(uuid7())
    await insert_oauth_client(
        OAuthClient(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            name="Rulings",
            client_id=client_id,
            client_secret_hash="unused-here",
            redirect_uris=[REDIRECT_URI],
            scopes=scopes,
            created_by_uid=user.uid,
        )
    )
    return client_id, user


def _authorize_query(client_id: str) -> dict[str, str]:
    return {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": OAuthScope.PROFILE_READ.value,
        "state": "opaque-state",
        "code_challenge": "x" * 43,
        "code_challenge_method": "S256",
    }


@pytest.mark.asyncio
async def test_existing_consent_returns_redirect_url_not_a_302(
    test_client: AsyncClient, test_db
):
    client_id, user = await _client_and_user([OAuthScope.PROFILE_READ])
    await upsert_oauth_consent(
        OAuthConsent(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            user_uid=user.uid,
            client_id=client_id,
            scopes=[OAuthScope.PROFILE_READ],
        )
    )

    response = await test_client.get(
        "/oauth/authorize",
        params=_authorize_query(client_id),
        headers=make_auth_header(user.uid),
    )

    assert response.status_code == 200
    url = urlparse(response.json()["redirect_url"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == REDIRECT_URI
    query = parse_qs(url.query)
    assert query["code"]
    assert query["state"] == ["opaque-state"]


@pytest.mark.asyncio
async def test_without_consent_the_prompt_payload_carries_no_redirect_url(
    test_client: AsyncClient, test_db
):
    client_id, user = await _client_and_user([OAuthScope.PROFILE_READ])

    response = await test_client.get(
        "/oauth/authorize",
        params=_authorize_query(client_id),
        headers=make_auth_header(user.uid),
    )

    assert response.status_code == 200
    body = response.json()
    # The page branches on redirect_url; the prompt payload must not carry one.
    assert "redirect_url" not in body
    assert body["client_name"] == "Rulings"
    assert body["scopes"] == [OAuthScope.PROFILE_READ.value]
