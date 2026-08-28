"""A `event:run` token reaches one tournament and nothing else.

Regression guarded: the OAuth gate used to be a denylist of `/auth/*` and
`/admin/*`, so an event:run token reached `/snapshot` and the unscoped
`/stream` — the granting organizer's whole corpus, private decks included — and
every other event they run. Nothing else in the suite exercises OAuth-token
access to these paths, so this is the only net.

The two credential paths are asserted separately because they are two
implementations of one gate: the `Authorization` header runs the middleware
allowlist, the `token=` query param runs none of it and must therefore refuse an
OAuth token outright.

Asserted at the HTTP boundary across the real middleware and routes against a
real DB, so a behaviour-preserving refactor stays green.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient
from src import db
from src.db_oauth import insert_oauth_client, insert_oauth_token, upsert_oauth_consent
from src.models import (
    OAuthClient,
    OAuthConsent,
    OAuthScope,
    OAuthToken,
    Tournament,
    User,
)
from src.routes.oauth import (
    ACCESS_TOKEN_LIFETIME,
    _create_oauth_jwt,
    _issue_token_pair,
    ph,
)

from tests.conftest import seed_tournament

NOW = datetime.now(UTC)
GRANTED = "trn-scope-granted"
OTHER = "trn-scope-other"


async def _scoped_token(
    user_uid: str,
    tournament_uid: str | None,
    scopes: list[OAuthScope] | None = None,
) -> str:
    jti = str(uuid7())
    scopes = scopes or [OAuthScope.PROFILE_READ, OAuthScope.EVENT_RUN]
    await insert_oauth_token(
        OAuthToken(
            uid=str(uuid7()),
            modified=NOW,
            token_jti=jti,
            client_id="play-platform",
            user_uid=user_uid,
            scopes=scopes,
            tournament_uid=tournament_uid,
            token_type="access",
            expires_at=datetime.now(UTC) + ACCESS_TOKEN_LIFETIME,
        )
    )
    return _create_oauth_jwt(
        user_uid,
        "access",
        scopes,
        "play-platform",
        jti,
        ACCESS_TOKEN_LIFETIME,
        tournament_uid,
    )


async def _seed_organizer_with_two_events() -> User:
    org = User(uid="org-scope", modified=NOW, name="Olivia Organizer")
    await db.save_user(org)
    for uid in (GRANTED, OTHER):
        await seed_tournament(
            Tournament(uid=uid, modified=NOW, name=uid, organizers_uids=["org-scope"])
        )
    return org


async def _drop_events() -> None:
    async with db.get_connection() as conn:
        await conn.execute(
            "DELETE FROM objects WHERE uid = ANY(%s)", ([GRANTED, OTHER],)
        )


@pytest.mark.asyncio
async def test_scoped_token_reaches_its_event_and_nothing_else(
    test_client: AsyncClient, test_db
):
    await _seed_organizer_with_two_events()
    token = await _scoped_token("org-scope", GRANTED)
    auth = {"Authorization": f"Bearer {token}"}
    try:
        assert (
            await test_client.get(f"/api/tournaments/{GRANTED}/decks", headers=auth)
        ).status_code == 200

        # OptionalUser routes fold the middleware's 403 into a 401; either way
        # the request never reaches the handler.
        for method, path, body in (
            ("GET", f"/api/tournaments/{OTHER}/decks", {}),
            ("GET", "/snapshot", {}),
            ("GET", "/stream", {}),
            ("GET", f"/stream?tournament={OTHER}", {}),
            ("POST", "/vekn/claim", {"vekn_id": "1234567"}),
            # Self-granting: `/oauth/*` is otherwise reachable, so without the
            # first-party guard a client keys itself consent for any other event.
            (
                "POST",
                "/oauth/authorize",
                {
                    "client_id": "play-platform",
                    "redirect_uri": "https://play.test/cb",
                    "scope": "event:run",
                    "code_challenge": "x" * 43,
                    "tournament": OTHER,
                    "approved": True,
                },
            ),
            ("PUT", "/sanctions/some-sanction-uid", {}),
            ("DELETE", "/sanctions/some-sanction-uid", {}),
            ("POST", f"/api/tournaments/{GRANTED}/push-vekn", {}),
            ("POST", f"/api/tournaments/{GRANTED}/organizers", {"user_uid": "x"}),
            ("POST", f"/api/tournaments/{GRANTED}/go-offline", {"device_id": "d"}),
            ("POST", f"/api/tournaments/{GRANTED}/qr-checkin", {"code": "x"}),
            ("DELETE", f"/api/tournaments/{GRANTED}", {}),
        ):
            resp = await test_client.request(method, path, headers=auth, json=body)
            assert resp.status_code in (401, 403), f"{method} {path}"

        # Sent with a real body: a missing file 422s before auth resolves, which
        # would pass this assertion without exercising the bar.
        resp = await test_client.post(
            f"/api/tournaments/{GRANTED}/archon-import",
            headers=auth,
            files={"file": ("roster.xlsx", b"not-a-real-workbook")},
        )
        assert resp.status_code in (401, 403), resp.status_code
    finally:
        await _drop_events()


@pytest.mark.asyncio
async def test_a_token_naming_no_event_is_identity_only(
    test_client: AsyncClient, test_db
):
    """`event:run` without a tournament is the identity-only grant: it answers
    `/oauth/userinfo` and reaches no event, its own granted one included."""
    await _seed_organizer_with_two_events()
    token = await _scoped_token("org-scope", None, [OAuthScope.EVENT_RUN])
    auth = {"Authorization": f"Bearer {token}"}
    try:
        assert (
            await test_client.get("/oauth/userinfo", headers=auth)
        ).status_code == 200
        for path in (
            f"/api/tournaments/{GRANTED}/decks",
            f"/stream?tournament={GRANTED}",
        ):
            assert (await test_client.get(path, headers=auth)).status_code in (401, 403)
    finally:
        await _drop_events()


@pytest.mark.asyncio
async def test_oauth_token_is_not_a_stream_query_credential(
    test_client: AsyncClient, test_db
):
    await _seed_organizer_with_two_events()
    token = await _scoped_token("org-scope", GRANTED)
    try:
        for path in (
            f"/snapshot?token={token}",
            f"/stream?token={token}",
            f"/stream?tournament={GRANTED}&token={token}",
        ):
            assert (await test_client.get(path)).status_code == 401, path
    finally:
        await _drop_events()


@pytest.mark.asyncio
async def test_an_identity_only_grant_refreshes(test_client: AsyncClient, test_db):
    """The grant that names no event is renewable like any other. Refresh used to
    refuse it outright, which capped it at one hour with no way to renew."""
    secret = "identity-grant-secret"
    user = User(uid=str(uuid7()), modified=NOW, name="Member")
    await db.save_user(user)
    client = OAuthClient(
        uid=str(uuid7()),
        modified=NOW,
        name="Event app",
        client_id=f"identity-{uuid7()}",
        client_secret_hash=ph.hash(secret),
        redirect_uris=["https://example.test/cb"],
        scopes=[OAuthScope.EVENT_RUN],
        created_by_uid=user.uid,
    )
    await insert_oauth_client(client)
    await upsert_oauth_consent(
        OAuthConsent(
            uid=str(uuid7()),
            modified=NOW,
            user_uid=user.uid,
            client_id=client.client_id,
            scopes=[OAuthScope.EVENT_RUN],
        )
    )
    pair = await _issue_token_pair(
        user_uid=user.uid,
        client_id=client.client_id,
        scopes=[OAuthScope.EVENT_RUN],
        tournament_uid=None,
        parent_token_uid=None,
    )
    response = await test_client.post(
        "/oauth/token",
        data={
            "client_id": client.client_id,
            "client_secret": secret,
            "grant_type": "refresh_token",
            "refresh_token": pair["refresh_token"],
        },
    )
    assert response.status_code == 200, response.text
    assert (
        await test_client.get(
            "/oauth/userinfo",
            headers={"Authorization": f"Bearer {response.json()['access_token']}"},
        )
    ).status_code == 200
