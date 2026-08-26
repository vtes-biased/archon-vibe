"""Thin marshalling layer over the Rust engine (PyO3) — must NOT re-implement any
rule, and no route may check a role directly. A new capability is a row in
``engine/src/permissions.rs``, not a check of its own."""

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


def _resource(obj: Tournament | League) -> str:
    """Flat ownership descriptor for the resolvers that take one directly."""
    return json.dumps({"country": obj.country, "organizers_uids": obj.organizers_uids})


def is_official(user: User) -> bool:
    """Holds the official badge (IC/NC/Prince).

    Identity, not authority — badges and quotas only. Never gate on it: ask for
    the capability the route actually needs.
    """
    return _engine.is_official(json.dumps(user_to_context(user)))


def can_sponsor_member(user: User) -> bool:
    """Bring someone into VEKN: mint a member record, or issue a VEKN ID to an
    account that has none. One authority — both allocate an ID and stamp
    coopted_by. Deliberately cross-country."""
    return _check("sponsor_member", user)


def can_edit_user(actor: User, target: User) -> bool:
    """Edit a user's profile fields."""
    return _check("edit_member_profile", actor, target=target)


def can_change_role(
    actor: User, target: User, role: Role, *, target_has_nda: bool = False
) -> bool:
    """Grant or revoke one role — see the engine's appointment matrix. The NDA
    fact lives in nda_records, not on User, so the caller passes it in; it only
    matters when granting PT (the engine ignores it everywhere else)."""
    target_context = user_to_context(target) | {"has_nda": target_has_nda}
    result = _engine.can_change_role(
        json.dumps(user_to_context(actor)),
        json.dumps(target_context),
        role.value,
    )
    return json.loads(result)["allowed"]


def can_manage_nda(actor: User) -> bool:
    """Request, upload, view and download playtest NDA records."""
    return _check("manage_nda", actor)


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


def can_merge_accounts(actor: User) -> bool:
    """Merge one account into another."""
    return _check("merge_accounts", actor)


def can_mark_deceased(actor: User, target_country: str | None) -> bool:
    """Set or clear a member's deceased status."""
    return _check("mark_deceased", actor, target_country=target_country)


def can_delete_member(actor: User) -> bool:
    """Soft-delete a member. The target-must-be-VEKN-less rule is at the route."""
    return _check("delete_member", actor)


def can_moderate_link(actor: User, link_country: str | None) -> bool:
    """Hide or clear a community link, scoped to the country the link serves
    (self-moderation included)."""
    return _check("moderate_link", actor, target_country=link_country)


def can_promote_link_national(actor: User, link_country: str | None) -> bool:
    """Promote a link to its country's national listing."""
    return _check("promote_link_national", actor, target_country=link_country)


def can_promote_link_global(actor: User) -> bool:
    """Promote a link to the global listing."""
    return _check("promote_link_global", actor)


def can_create_tournament(user: User) -> bool:
    """Create a tournament."""
    return _check("create_tournament", user)


def is_organizer(user: User, tournament: Tournament) -> bool:
    """Run a tournament: an explicit organizer, or implicitly IC/NC."""
    return _check("organize_tournament", user, resource=tournament)


def can_take_tournament_offline(user: User, tournament: Tournament) -> bool:
    """Take a tournament offline, or force-take its lock: run the event AND hold
    the member-creation power the lock carries."""
    result = _engine.can_take_tournament_offline(
        json.dumps(user_to_context(user)), user.uid, _resource(tournament)
    )
    return json.loads(result)["allowed"]


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


def can_run_admin_sync(user: User) -> bool:
    """Trigger and inspect the VEKN/TWDA sync jobs."""
    return _check("run_admin_sync", user)


def unconditional_capabilities(user: User) -> list[str]:
    """Capability names the user holds anywhere, over anyone.

    For remote clients (the Discord bot) that need to know what to offer without
    carrying their own copy of the matrix. Country- and resource-scoped grants
    are absent by construction — they have no answer without a target.
    """
    return json.loads(
        _engine.unconditional_capabilities(json.dumps(user_to_context(user)))
    )
