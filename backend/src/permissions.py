"""Authorization adapter: a thin marshalling layer over the Rust engine (PyO3).

The authorization LOGIC lives once in ``engine/src/permissions.rs`` as a
capability table, shared with the frontend via WASM. This module only names the
capability and marshals the request — it must NOT re-implement any rule, and no
route may check a role directly. One function per capability; a route that needs
a new one adds a row to the engine table, not a check of its own.
"""

import json

from archon_engine import PyEngine

from .models import League, Role, Sanction, SanctionLevel, Tournament, User
from .utils import user_to_context

_engine = PyEngine()


def _check(
    capability: str,
    actor: User,
    *,
    target: User | None = None,
    target_country: str | None = None,
    resource: Tournament | League | None = None,
) -> bool:
    """Ask the engine whether ``actor`` holds ``capability`` in this context.

    Fill only what the capability reads; an absent field matches no grant. A
    ``target`` supplies both its uid (self-service) and its country (same-country
    scope), so it is never combined with an explicit ``target_country``.
    """
    request = {
        "actor": user_to_context(actor),
        "actor_uid": actor.uid,
        "target_uid": target.uid if target else None,
        "target_country": target.country if target else target_country,
    }
    if resource is not None:
        request["resource"] = {
            "country": resource.country,
            "organizers_uids": resource.organizers_uids,
        }
        # For a resource-scoped capability, "same country" means the resource's
        # — an NC is an implicit organizer of their country's tournaments.
        if target is None and target_country is None:
            request["target_country"] = resource.country
    result = _engine.check_permission(capability, json.dumps(request))
    return json.loads(result)["allowed"]


def is_official(user: User) -> bool:
    """Holds the official badge (IC/NC/Prince).

    Identity, not authority — badges and quotas only. Never gate on it: ask for
    the capability the route actually needs.
    """
    return _engine.is_official(json.dumps(user_to_context(user)))


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def can_create_member(user: User) -> bool:
    """Create a member record."""
    return _check("create_member", user)


def can_edit_user(actor: User, target: User) -> bool:
    """Edit a user's profile fields."""
    return _check("edit_member_profile", actor, target=target)


def can_change_role(actor: User, target: User, role: Role) -> bool:
    """Grant or revoke one role — see the engine's appointment matrix."""
    result = _engine.can_change_role(
        json.dumps(user_to_context(actor)),
        json.dumps(user_to_context(target)),
        role.value,
    )
    return json.loads(result)["allowed"]


def can_change_country(actor: User, target: User) -> bool:
    """Move a member between countries. For an official target this takes the
    authority that could change their highest official role."""
    result = _engine.can_change_country(
        json.dumps(user_to_context(actor)),
        json.dumps(user_to_context(target)),
    )
    return json.loads(result)["allowed"]


def can_manage_vekn(actor: User, target: User) -> bool:
    """Link or force-abandon a target's VEKN ID."""
    return _check("manage_vekn", actor, target=target)


def can_sponsor_vekn(user: User) -> bool:
    """Sponsor a new VEKN ID — deliberately cross-country."""
    return _check("sponsor_vekn", user)


def can_merge_accounts(actor: User) -> bool:
    """Merge one account into another."""
    return _check("merge_accounts", actor)


def can_mark_deceased(actor: User, target_country: str | None) -> bool:
    """Set or clear a member's deceased status."""
    return _check("mark_deceased", actor, target_country=target_country)


def can_delete_member(actor: User) -> bool:
    """Soft-delete a member. The target-must-be-VEKN-less rule is at the route."""
    return _check("delete_member", actor)


# ---------------------------------------------------------------------------
# Community links
# ---------------------------------------------------------------------------


def can_moderate_link(actor: User, target: User) -> bool:
    """Hide or clear a member's community link (self-moderation included)."""
    return _check("moderate_link", actor, target=target)


def can_promote_link_national(actor: User, target: User) -> bool:
    """Promote a link to the national listing."""
    return _check("promote_link_national", actor, target=target)


def can_promote_link_global(actor: User) -> bool:
    """Promote a link to the global listing."""
    return _check("promote_link_global", actor)


# ---------------------------------------------------------------------------
# Tournaments and leagues
# ---------------------------------------------------------------------------


def can_create_tournament(user: User) -> bool:
    """Create a tournament."""
    return _check("create_tournament", user)


def is_organizer(user: User, tournament: Tournament) -> bool:
    """Run a tournament: an explicit organizer, or implicitly IC/NC."""
    return _check("organize_tournament", user, resource=tournament)


def can_force_unlock_tournament(user: User) -> bool:
    """Break an offline device lock."""
    return _check("force_unlock_tournament", user)


def can_manage_leagues(user: User) -> bool:
    """Create and delete leagues."""
    return _check("manage_leagues", user)


def can_edit_league(user: User, league: League) -> bool:
    """Edit a league."""
    return _check("edit_league", user, resource=league)


def can_link_tournament_to_league(user: User, league: League) -> bool:
    """A league editor, or a same-country Prince when the league is open to them."""
    descriptor = json.dumps(
        {
            "country": league.country,
            "organizers_uids": league.organizers_uids,
            "open_to_country_princes": league.open_to_country_princes,
        }
    )
    result = _engine.can_link_tournament_to_league(
        json.dumps(user_to_context(user)), user.uid, descriptor
    )
    return json.loads(result)["allowed"]


# ---------------------------------------------------------------------------
# Sanctions
# ---------------------------------------------------------------------------


def can_issue_sanction(
    issuer: User, level: SanctionLevel, tournament: Tournament | None
) -> bool:
    """Issue a sanction — the level decides which capability applies."""
    organizers = json.dumps(
        {"organizers_uids": tournament.organizers_uids if tournament else []}
    )
    result = _engine.can_issue_sanction(
        json.dumps(user_to_context(issuer)), issuer.uid, str(level), organizers
    )
    return json.loads(result)["allowed"]


def can_lift_sanction(
    user: User,
    sanction: Sanction,
    tournament: Tournament | None,
    league: League | None,
) -> bool:
    """Lift a sanction — level plus the tournament/league it hangs off."""
    ctx = json.dumps(
        {
            "level": str(sanction.level),
            "tournament_country": tournament.country if tournament else None,
            "league_organizers_uids": league.organizers_uids if league else [],
        }
    )
    result = _engine.can_lift_sanction(json.dumps(user_to_context(user)), user.uid, ctx)
    return json.loads(result)["allowed"]


def can_modify_sanction(user: User) -> bool:
    """Edit an issued sanction's content."""
    return _check("modify_sanction", user)


def can_delete_sanction(
    user: User, sanction: Sanction, tournament: Tournament | None
) -> bool:
    """Delete a sanction — organizers only for what they could have issued, and
    only while the tournament is unfinished."""
    ctx = json.dumps(
        {
            "level": str(sanction.level),
            "tournament_state": str(tournament.state) if tournament else "",
            "tournament_organizers_uids": (
                tournament.organizers_uids if tournament else []
            ),
        }
    )
    result = _engine.can_delete_sanction(
        json.dumps(user_to_context(user)), user.uid, ctx
    )
    return json.loads(result)["allowed"]


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


def can_manage_promos(user: User) -> bool:
    """Create, edit and allocate promos."""
    return _check("manage_promos", user)


def can_record_promo_intake(user: User) -> bool:
    """Record a promo intake."""
    return _check("record_promo_intake", user)


def can_view_full_promo_ledger(user: User) -> bool:
    """See the whole promo ledger rather than one's own entries."""
    return _check("view_full_promo_ledger", user)


def can_manage_oauth_clients(user: User) -> bool:
    """Register and revoke OAuth clients."""
    return _check("manage_oauth_clients", user)
