"""Removing a scope from a client takes it back from every member who granted it.

Regression guarded: a refresh re-issues the token's own scopes and a remembered
consent auto-approves a later authorize, so an edit that only rewrote the client
row would leave the removed scope live in both. Asserted at the HTTP boundary
against a real DB and the real routes.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient
from src import db
from src.db_oauth import get_oauth_consent, upsert_oauth_consent
from src.models import OAuthConsent, OAuthScope, Role, User
from src.routes.oauth import _issue_token_pair

from tests.conftest import make_auth_header

KEPT = [OAuthScope.PROFILE_READ]
GRANTED = [OAuthScope.PROFILE_READ, OAuthScope.PROFILE_EMAIL]


@pytest.mark.asyncio
async def test_removing_a_scope_kills_its_lineages_and_its_consent(
    test_client: AsyncClient, test_db
):
    dev = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Dev",
        country="US",
        roles=[Role.DEV],
    )
    member = User(
        uid=str(uuid7()), modified=datetime.now(UTC), name="Member", country="US"
    )
    await db.save_user(dev)
    await db.save_user(member)
    session = make_auth_header(dev.uid)

    registered = await test_client.post(
        "/oauth/clients",
        headers=session,
        json={
            "name": "Mailer",
            "redirect_uris": ["https://example.test/cb"],
            "scopes": [s.value for s in GRANTED],
            "email_purpose": "Sends the round pairings",
        },
    )
    assert registered.status_code == 201, registered.text
    client_id = registered.json()["client_id"]
    credentials = {
        "client_id": client_id,
        "client_secret": registered.json()["client_secret"],
    }

    await upsert_oauth_consent(
        OAuthConsent(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            user_uid=member.uid,
            client_id=client_id,
            scopes=GRANTED,
        )
    )
    email_pair, kept_pair = [
        await _issue_token_pair(
            user_uid=member.uid,
            client_id=client_id,
            scopes=scopes,
            tournament_uid=None,
            parent_token_uid=None,
        )
        for scopes in (GRANTED, KEPT)
    ]

    reworded = await test_client.patch(
        f"/oauth/clients/{client_id}",
        headers=session,
        json={
            "redirect_uris": ["https://example.test/cb"],
            "scopes": [s.value for s in GRANTED],
            "email_purpose": "Something else",
        },
    )
    assert reworded.status_code == 400

    edited = await test_client.patch(
        f"/oauth/clients/{client_id}",
        headers=session,
        json={
            "redirect_uris": ["https://example.test/new"],
            "scopes": [s.value for s in KEPT],
        },
    )
    assert edited.status_code == 200, edited.text

    consent = await get_oauth_consent(member.uid, client_id, None)
    assert consent is not None and consent.scopes == KEPT

    def bearer(pair: dict) -> dict:
        return {"Authorization": f"Bearer {pair['access_token']}"}

    assert (
        await test_client.get("/oauth/userinfo", headers=bearer(email_pair))
    ).status_code == 401
    assert (
        await test_client.get("/oauth/userinfo", headers=bearer(kept_pair))
    ).status_code == 200

    refreshed = await test_client.post(
        "/oauth/token",
        data=credentials
        | {"grant_type": "refresh_token", "refresh_token": email_pair["refresh_token"]},
    )
    assert refreshed.status_code == 400
    refreshed = await test_client.post(
        "/oauth/token",
        data=credentials
        | {"grant_type": "refresh_token", "refresh_token": kept_pair["refresh_token"]},
    )
    assert refreshed.status_code == 200, refreshed.text
