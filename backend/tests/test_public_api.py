"""The public API's standing claims, asserted against the app itself: it is
read-only behind a token, its reference page renders, and the schema it documents
is the projection it actually serves."""

import re

import msgspec
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from src.access_levels import compute_api
from src.models import DeckObject, League, ObjectType, Player, Tournament, User
from src.public_api.main import app
from src.public_api.schemas import COMPONENTS

_WRITES = ("POST", "PUT", "PATCH", "DELETE")
_UNDOCUMENTED = ("/docs", "/openapi.json")


def _paths() -> list[str]:
    documented = [re.sub(r"\{[^}]+\}", "x", path) for path in app.openapi()["paths"]]
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
