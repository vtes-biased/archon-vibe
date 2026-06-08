"""Authorization adapter: a thin marshalling layer over the Rust engine (PyO3).

The authorization LOGIC lives once in ``engine/src/permissions.rs`` and is shared
with the frontend via WASM. This module only converts User/Tournament/League
objects into the engine's JSON contract and reads back the decision — it must
NOT re-implement any rule. See engine/src/permissions.rs.
"""

import json

from archon_engine import PyEngine

from .models import League, Tournament, User
from .utils import user_to_context

_engine = PyEngine()


def _allowed(result_json: str) -> bool:
    return json.loads(result_json)["allowed"]


def _resource(obj: Tournament | League) -> str:
    """Flat ownership descriptor (country + organizers) for the engine boundary."""
    return json.dumps({"country": obj.country, "organizers_uids": obj.organizers_uids})


def is_official(user: User) -> bool:
    """IC/NC/Prince — can create/manage tournaments and members."""
    return _allowed(_engine.can_manage_tournaments(json.dumps(user_to_context(user))))


def can_manage_country(manager: User, target_country: str | None) -> bool:
    """IC manages any country; NC/Prince only their own."""
    return _allowed(
        _engine.can_manage_country(
            json.dumps(user_to_context(manager)), target_country or ""
        )
    )


def can_manage_leagues(user: User) -> bool:
    """IC/NC can create and delete leagues."""
    return _allowed(_engine.can_manage_leagues(json.dumps(user_to_context(user))))


def is_organizer(user: User, tournament: Tournament) -> bool:
    """Explicit organizer, or implicit: IC (any) or NC (same country)."""
    return _allowed(
        _engine.is_organizer(
            json.dumps(user_to_context(user)), user.uid, _resource(tournament)
        )
    )


def can_edit_league(user: User, league: League) -> bool:
    """IC, NC (same country), or a league organizer."""
    return _allowed(
        _engine.can_edit_league(
            json.dumps(user_to_context(user)), user.uid, _resource(league)
        )
    )
