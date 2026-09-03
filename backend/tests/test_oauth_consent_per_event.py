"""One member grants one client `event:run` on two events.

Regression guarded: the consent table's unique index was keyed on (user, client)
from before grants became per event, so a member's second event for the same
client — the Discord bot's `/setup` on a second tournament — failed the INSERT
with a unique violation and the consent page showed a 500. The grant is keyed on
(client, user, tournament) and `GET /oauth/consents` answers one row per event.

Asserted at the HTTP boundary against the real DB: the index lives in the
schema file, so only a real table exercises it.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient
from src import db
from src.db_oauth import insert_oauth_client
from src.models import OAuthClient, OAuthScope, Tournament, User

from tests.conftest import make_auth_header, seed_tournament

NOW = datetime.now(UTC)
REDIRECT_URI = "https://bot.test/oauth/callback"
FIRST = "trn-consent-first"
SECOND = "trn-consent-second"


@pytest.mark.asyncio
async def test_a_member_grants_one_client_two_events(test_client: AsyncClient, test_db):
    user = User(uid=str(uuid7()), modified=NOW, name="Member")
    await db.save_user(user)
    client_id = f"bot-{uuid7()}"
    await insert_oauth_client(
        OAuthClient(
            uid=str(uuid7()),
            modified=NOW,
            name="Discord bot",
            client_id=client_id,
            client_secret_hash="unused-here",
            redirect_uris=[REDIRECT_URI],
            scopes=[OAuthScope.PROFILE_READ, OAuthScope.EVENT_RUN],
            created_by_uid=user.uid,
        )
    )
    for uid in (FIRST, SECOND):
        await seed_tournament(
            Tournament(uid=uid, modified=NOW, name=uid, organizers_uids=[user.uid])
        )
    auth = make_auth_header(user.uid)
    try:
        for tournament in (FIRST, SECOND):
            response = await test_client.post(
                "/oauth/authorize",
                headers=auth,
                json={
                    "client_id": client_id,
                    "redirect_uri": REDIRECT_URI,
                    "scope": "profile:read event:run",
                    "state": "opaque-state",
                    "code_challenge": "x" * 43,
                    "tournament": tournament,
                    "approved": True,
                },
            )
            assert response.status_code == 200, response.text
            assert "code=" in response.json()["redirect_url"]

        consents = (await test_client.get("/oauth/consents", headers=auth)).json()
        assert sorted(
            c["tournament"] for c in consents if c["client_id"] == client_id
        ) == [
            FIRST,
            SECOND,
        ]
    finally:
        async with db.get_connection() as conn:
            await conn.execute(
                "DELETE FROM objects WHERE uid = ANY(%s)", ([FIRST, SECOND],)
            )
            await conn.execute(
                "DELETE FROM oauth_consents WHERE data->>'client_id' = %s", (client_id,)
            )
