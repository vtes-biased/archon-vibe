"""Authorization adapter: a thin marshalling layer over the Rust engine (PyO3).

The authorization LOGIC lives once in ``engine/src/permissions.rs`` and is shared
with the frontend via WASM. This module only converts User/Tournament/League
objects into the engine's JSON contract and reads back the decision — it must
NOT re-implement any rule. See engine/src/permissions.rs.
"""

import json

from archon_engine import PyEngine

from .models import League, Role, Sanction, SanctionLevel, Tournament, User
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


def can_edit_user(actor: User, target: User) -> bool:
    """Edit a user's profile fields: self, IC (anyone), or NC/Prince (same country)."""
    return _allowed(
        _engine.can_edit_user(
            json.dumps(user_to_context(actor)),
            actor.uid,
            target.uid,
            json.dumps(user_to_context(target)),
        )
    )


def can_change_role(actor: User, target: User, role: Role) -> bool:
    """IC any; NC only Prince same-country; PTC→PT; Rulemonger→Judge/Judgekin."""
    return _allowed(
        _engine.can_change_role(
            json.dumps(user_to_context(actor)),
            json.dumps(user_to_context(target)),
            role.value,
        )
    )


# Official roles, highest authority first. Their country scopes a FULL-data
# overlay, so changing it takes the authority that could change that role.
_OFFICIAL_ROLES = (Role.IC, Role.NC, Role.PRINCE)


def can_change_country(actor: User, target: User) -> bool:
    """Whether ``actor`` may change ``target``'s country.

    For an official target, gated by the authority that could change their
    highest official role (``can_change_role``) — a self-service country change
    by an NC/Prince is an unauthorized data-scope change. A non-official target
    is unrestricted (ordinary self-service / same-country admin edit).

    Highest role = strictest gate (an NC+Prince target needs NC-level authority).
    can_change_role's vekn_id precondition is unreachable here: an official always
    has a vekn_id (roles can't be assigned without one).
    """
    highest = next((r for r in _OFFICIAL_ROLES if r in target.roles), None)
    return highest is None or can_change_role(actor, target, highest)


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


def can_delete_member(actor: User) -> bool:
    """IC only. The target-must-be-VEKN-less rule is enforced at the route."""
    return _allowed(_engine.can_delete_member(json.dumps(user_to_context(actor))))


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
