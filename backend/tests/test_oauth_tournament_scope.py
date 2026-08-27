"""A `user:impersonate` token reaches one tournament and nothing else.

Regression guarded: the OAuth gate used to be a denylist of `/auth/*` and
`/admin/*`, so an impersonate token reached `/snapshot` and the unscoped
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
from src.db_oauth import insert_oauth_token
from src.models import OAuthScope, OAuthToken, Tournament, User
from src.routes.oauth import ACCESS_TOKEN_LIFETIME, _create_oauth_jwt

from tests.conftest import seed_tournament

NOW = datetime.now(UTC)
GRANTED = "trn-scope-granted"
OTHER = "trn-scope-other"


async def _scoped_token(user_uid: str, tournament_uid: str | None) -> str:
    jti = str(uuid7())
    scopes = [OAuthScope.PROFILE_READ, OAuthScope.USER_IMPERSONATE]
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
                    "scope": "user:impersonate",
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
            ("DELETE", f"/api/tournaments/{GRANTED}", {}),
        ):
            resp = await test_client.request(method, path, headers=auth, json=body)
            assert resp.status_code in (401, 403), f"{method} {path}"
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
