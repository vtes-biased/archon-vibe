"""Authorization adapter: a thin marshalling layer over the Rust engine (PyO3).

The authorization LOGIC lives once in ``engine/src/permissions.rs`` and is shared
with the frontend via WASM. This module only converts User/Tournament/League
objects into the engine's JSON contract and reads back the decision — it must
NOT re-implement any rule. See engine/src/permissions.rs.
"""

import json

from archon_engine import PyEngine

from .models import League, Sanction, SanctionLevel, Tournament, User
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


def can_mark_deceased(actor: User, target_country: str | None) -> bool:
    """IC manages any country; NC only their own (Prince excluded)."""
    return _allowed(
        _engine.can_mark_deceased(
            json.dumps(user_to_context(actor)), target_country or ""
        )
    )


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


def can_issue_sanction(
    issuer: User, level: SanctionLevel, tournament: Tournament | None
) -> bool:
    """Suspension/probation: IC or Ethics. Else: IC, Ethics, or tournament organizer."""
    organizers = json.dumps(
        {"organizers_uids": tournament.organizers_uids if tournament else []}
    )
    return _allowed(
        _engine.can_issue_sanction(
            json.dumps(user_to_context(issuer)), issuer.uid, str(level), organizers
        )
    )


def can_lift_sanction(
    user: User,
    sanction: Sanction,
    tournament: Tournament | None,
    league: League | None,
) -> bool:
    """IC/Ethics for suspension/probation; else IC/Rulemonger, NC of the
    tournament's country, or a league organizer (for a DQ)."""
    ctx = json.dumps(
        {
            "level": str(sanction.level),
            "tournament_country": tournament.country if tournament else None,
            "league_organizers_uids": league.organizers_uids if league else [],
        }
    )
    return _allowed(
        _engine.can_lift_sanction(json.dumps(user_to_context(user)), user.uid, ctx)
    )


def can_delete_sanction(
    user: User, sanction: Sanction, tournament: Tournament | None
) -> bool:
    """IC/Ethics for any sanction; else an organizer of the sanction's
    tournament, for organizer-issuable levels, while it is not Finished."""
    ctx = json.dumps(
        {
            "level": str(sanction.level),
            "tournament_state": str(tournament.state) if tournament else "",
            "tournament_organizers_uids": (
                tournament.organizers_uids if tournament else []
            ),
        }
    )
    return _allowed(
        _engine.can_delete_sanction(json.dumps(user_to_context(user)), user.uid, ctx)
    )
