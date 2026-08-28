"""The public API's standing claims, asserted against the app itself: it is
read-only behind a token, its reference page renders, the schema it documents is
the projection it actually serves, and a daemon identity opens it while the app
stays shut to that same token."""

import re
from datetime import UTC, datetime
from uuid import uuid7

import msgspec
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from src.access_levels import compute_api
from src.db_oauth import (
    get_oauth_client_by_client_id,
    insert_oauth_client,
    update_oauth_client,
)
from src.models import (
    DeckObject,
    League,
    OAuthClient,
    OAuthScope,
    ObjectType,
    Player,
    Tournament,
    User,
)
from src.public_api import db as public_db
from src.public_api.main import app
from src.public_api.schemas import COMPONENTS
from src.routes.oauth import ph

_WRITES = ("POST", "PUT", "PATCH", "DELETE")
_UNDOCUMENTED = ("/docs", "/openapi.json")


def _paths() -> list[str]:
    # The document also carries the app's Member API endpoints, which this
    # app does not serve — asserting on those would only exercise its 404 handler.
    documented = [
        re.sub(r"\{[^}]+\}", "x", path)
        for path, operations in app.openapi()["paths"].items()
        if any("Public API" in op.get("tags", []) for op in operations.values())
    ]
    assert documented
    return [*documented, *_UNDOCUMENTED]


def _every_field(struct, **overrides) -> dict:
    full = {field.name: None for field in msgspec.structs.fields(struct)}
    full.update(overrides)
    return full


# A maximal object of each type — every field the struct declares — so the key
# set the projection returns is the whole of what the column can ever carry.
_SAMPLES = {
    ObjectType.TOURNAMENT: (
        "Tournament",
        _every_field(Tournament, players=[_every_field(Player)]),
    ),
    ObjectType.USER: ("User", _every_field(User, vekn_id="1000001")),
    ObjectType.LEAGUE: ("League", _every_field(League)),
    ObjectType.DECK: ("DeckObject", _every_field(DeckObject, public=True)),
}


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://api"
    ) as api:
        yield api


@pytest_asyncio.fixture
async def live_api(test_db):
    # The API's pool is its own — nothing else in this process opens it.
    await public_db.open_pool()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://api"
    ) as api:
        yield api
    await public_db.close_pool()


async def _register(name: str, scopes: list[OAuthScope]) -> tuple[str, str]:
    secret = f"secret-for-{name}"
    client_id = f"client-{name}-{uuid7()}"
    await insert_oauth_client(
        OAuthClient(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            name=name,
            client_id=client_id,
            client_secret_hash=ph.hash(secret),
            redirect_uris=[],
            scopes=scopes,
            created_by_uid="tests",
        )
    )
    return client_id, secret


def _grant(client_id: str, secret: str) -> dict:
    return {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": secret,
    }


async def _mint(app_client, client_id: str, secret: str):
    return await app_client.post("/oauth/token", json=_grant(client_id, secret))


class TestReadOnlyAndGated:
    @pytest.mark.asyncio
    async def test_no_route_accepts_a_write(self, client):
        for path in _paths():
            for method in _WRITES:
                response = await client.request(method, path)
                assert response.status_code == 405, f"{method} {path}"

    @pytest.mark.asyncio
    async def test_no_data_route_answers_without_a_token(self, client):
        for path in _paths():
            if path in _UNDOCUMENTED:
                continue
            assert (await client.get(path)).status_code == 401, path

    @pytest.mark.asyncio
    async def test_the_reference_page_and_its_schema_are_open(self, client):
        assert "scalar" in (await client.get("/docs")).text.lower()
        schemas = (await client.get("/openapi.json")).json()["components"]["schemas"]
        assert set(COMPONENTS) <= set(schemas)


class TestDocumentedSchemaMatchesProjection:
    @pytest.mark.parametrize("obj_type", sorted(_SAMPLES))
    def test_documented_properties_are_the_projected_keys(self, obj_type):
        name, sample = _SAMPLES[obj_type]
        projected = compute_api(obj_type, sample)
        assert set(projected) == set(COMPONENTS[name]["properties"])

    def test_documented_player_properties_are_the_projected_keys(self):
        _, sample = _SAMPLES[ObjectType.TOURNAMENT]
        projected = compute_api(ObjectType.TOURNAMENT, sample)
        assert set(projected["players"][0]) == set(COMPONENTS["Player"]["properties"])


class TestDaemonIdentity:
    @pytest.mark.asyncio
    async def test_a_daemon_token_reads_the_api(self, test_client, live_api):
        client_id, secret = await _register("daemon", [OAuthScope.API_READ])
        minted = await _mint(test_client, client_id, secret)
        assert minted.status_code == 200, minted.text
        body = minted.json()
        assert body["scope"] == "api:read"
        assert "refresh_token" not in body

        headers = {"Authorization": f"Bearer {body['access_token']}"}
        assert (
            await live_api.get("/v1/tournaments", headers=headers)
        ).status_code == 200

    @pytest.mark.asyncio
    async def test_the_app_refuses_the_token_it_minted(self, test_client):
        client_id, secret = await _register("app-refuses", [OAuthScope.API_READ])
        token = (await _mint(test_client, client_id, secret)).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert (
            await test_client.get("/oauth/userinfo", headers=headers)
        ).status_code == 401

    @pytest.mark.asyncio
    async def test_deactivating_the_client_kills_a_live_token(
        self, test_client, live_api
    ):
        client_id, secret = await _register("revoked", [OAuthScope.API_READ])
        token = (await _mint(test_client, client_id, secret)).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert (
            await live_api.get("/v1/tournaments", headers=headers)
        ).status_code == 200

        record = await get_oauth_client_by_client_id(client_id)
        await update_oauth_client(msgspec.structs.replace(record, active=False))
        assert (
            await live_api.get("/v1/tournaments", headers=headers)
        ).status_code == 401

    @pytest.mark.asyncio
    async def test_the_rfc_form_encoding_mints_the_same_token(
        self, test_client, live_api
    ):
        client_id, secret = await _register("form", [OAuthScope.API_READ])
        minted = await test_client.post("/oauth/token", data=_grant(client_id, secret))
        assert minted.status_code == 200, minted.text
        headers = {"Authorization": f"Bearer {minted.json()['access_token']}"}
        assert (
            await live_api.get("/v1/tournaments", headers=headers)
        ).status_code == 200

    @pytest.mark.asyncio
    async def test_a_client_without_the_scope_cannot_mint(self, test_client):
        client_id, secret = await _register("no-scope", [OAuthScope.PROFILE_READ])
        assert (await _mint(test_client, client_id, secret)).status_code == 400
