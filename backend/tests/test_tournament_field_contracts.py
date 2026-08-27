"""The hand-maintained field lists in `routes/tournaments.py`, pinned."""

import msgspec
import pytest
from archon_engine import PyEngine
from src.models import Tournament, TournamentConfig
from src.routes.tournaments import (
    _ACTION_TRUTHY_ONLY,
    CreateTournamentRequest,
    TournamentActionRequest,
)

# Carried by TournamentConfig but not organizer-editable: identity and soft-delete
# stamps, the lifecycle state the events own, and the organizer roster managed by
# AddOrganizer/RemoveOrganizer.
NON_CONFIG_FIELDS = {"uid", "modified", "deleted_at", "state", "organizers_uids"}

ENGINE = PyEngine()

SAMPLE_CONFIG = {
    "name": "Sample Event",
    "format": "Limited",
    "rank": "",
    "online": True,
    "start": "2026-03-01T10:00:00",
    "finish": "2026-03-01T20:00:00",
    "timezone": "Europe/Paris",
    "country": "FR",
    "venue": "Sample Venue",
    "venue_url": "https://example.invalid/venue",
    "address": "1 Sample Street",
    "map_url": "https://example.invalid/map",
    "proxies": True,
    "multideck": True,
    "decklist_required": True,
    "description": "Sample description",
    "standings_mode": "Public",
    "decklists_mode": "All",
    "max_rounds": 3,
    "max_players": 40,
    "open_rounds": True,
    "self_organized_rounds": True,
    "table_rooms": [{"name": "Cellar", "count": 2}],
    "league_uid": "league-0001",
    "round_time": 7200,
    "finals_time": 5400,
}

ACTOR = {
    "uid": "organizer-1",
    "roles": ["IC"],
    "is_organizer": True,
    "can_organize_league_uids": ["league-0001"],
}


@pytest.fixture(scope="module")
def config_fields() -> set[str]:
    return set(ENGINE.config_fields())


def test_python_config_model_matches_engine(config_fields):
    model_fields = {f.name for f in msgspec.structs.fields(TournamentConfig)}
    assert model_fields - NON_CONFIG_FIELDS == config_fields


def test_create_request_matches_engine(config_fields):
    assert set(CreateTournamentRequest.model_fields) == config_fields


def test_sample_covers_every_config_field(config_fields):
    assert set(SAMPLE_CONFIG) == config_fields


def test_engine_create_carries_every_config_field():
    config = SAMPLE_CONFIG | {"uid": "t-sample", "now": "2026-01-01T00:00:00Z"}
    created = msgspec.json.decode(
        ENGINE.create_tournament(
            msgspec.json.encode(config).decode(),
            msgspec.json.encode(ACTOR).decode(),
        ),
        type=Tournament,
    )
    for field, value in SAMPLE_CONFIG.items():
        assert msgspec.to_builtins(getattr(created, field)) == value, field


_ACTION_ANY_VALUE = {
    "round",
    "table",
    "table1",
    "seat1",
    "table2",
    "seat2",
    "seat",
    "toss",
    "non_competing",
    "waitlisted",
    "player_uids",
    "config",
    "deck",
    "multideck",
    "exclude_drawn",
    "count",
    "seed",
    "winner",
    "players",
    "reported_player_count",
}


def test_every_action_field_is_classified():
    assert not (_ACTION_TRUTHY_ONLY & _ACTION_ANY_VALUE)
    assert _ACTION_TRUTHY_ONLY | _ACTION_ANY_VALUE == set(
        TournamentActionRequest.model_fields
    ) - {"type"}
