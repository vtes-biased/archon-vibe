use crate::error::EngineError;
use json::JsonValue;

/// Roles that users can have
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Role {
    IC,
    NC,
    Prince,
    Ethics,
    PTC,
    PT,
    Rulemonger,
    Judge,
    Judgekin,
    DEV,
}

impl Role {
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "IC" => Some(Role::IC),
            "NC" => Some(Role::NC),
            "Prince" => Some(Role::Prince),
            "Ethics" => Some(Role::Ethics),
            "PTC" => Some(Role::PTC),
            "PT" => Some(Role::PT),
            "Rulemonger" => Some(Role::Rulemonger),
            "Judge" => Some(Role::Judge),
            "Judgekin" => Some(Role::Judgekin),
            "DEV" => Some(Role::DEV),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Role::IC => "IC",
            Role::NC => "NC",
            Role::Prince => "Prince",
            Role::Ethics => "Ethics",
            Role::PTC => "PTC",
            Role::PT => "PT",
            Role::Rulemonger => "Rulemonger",
            Role::Judge => "Judge",
            Role::Judgekin => "Judgekin",
            Role::DEV => "DEV",
        }
    }
}

/// Minimal user context needed for permission checks
#[derive(Debug, Clone)]
pub struct UserContext {
    pub roles: Vec<Role>,
    pub country: Option<String>,
    pub vekn_id: Option<String>,
}

impl UserContext {
    pub fn from_json(value: &JsonValue) -> Result<Self, EngineError> {
        let roles: Vec<Role> = value["roles"]
            .members()
            .filter_map(|r| r.as_str().and_then(Role::from_str))
            .collect();

        let country = value["country"].as_str().map(|s| s.to_string());
        let vekn_id = value["vekn_id"].as_str().map(|s| s.to_string());

        Ok(UserContext {
            roles,
            country,
            vekn_id,
        })
    }

    pub fn has_role(&self, role: Role) -> bool {
        self.roles.contains(&role)
    }
}

/// Permission check results with reason
#[derive(Debug, Clone)]
pub struct PermissionResult {
    pub allowed: bool,
    pub reason: Option<String>,
}

impl PermissionResult {
    pub fn allow() -> Self {
        PermissionResult {
            allowed: true,
            reason: None,
        }
    }

    pub fn deny(reason: &str) -> Self {
        PermissionResult {
            allowed: false,
            reason: Some(reason.to_string()),
        }
    }

    pub fn to_json(&self) -> JsonValue {
        json::object! {
            allowed: self.allowed,
            reason: self.reason.clone()
        }
    }
}

/// Check if actor can change a specific role on target user.
///
/// Rules:
/// - IC: can change any role
/// - NC: can promote/demote Prince (same country only)
/// - PTC: can promote/demote PT (any country)
/// - Rulemonger: can promote/demote Judge (any country)
/// - Target must have VEKN ID to have roles
pub fn can_change_role(actor: &UserContext, target: &UserContext, role: Role) -> PermissionResult {
    // Target must have VEKN ID to have roles
    if target.vekn_id.is_none() {
        return PermissionResult::deny("User must have a VEKN ID to be assigned roles");
    }

    // IC can change any role
    if actor.has_role(Role::IC) {
        return PermissionResult::allow();
    }

    // PTC can promote/demote PT (any country)
    if role == Role::PT && actor.has_role(Role::PTC) {
        return PermissionResult::allow();
    }

    // Rulemonger can promote/demote Judge and Judgekin (any country)
    if (role == Role::Judge || role == Role::Judgekin) && actor.has_role(Role::Rulemonger) {
        return PermissionResult::allow();
    }

    // NC can only promote/demote Prince in same country
    if role == Role::Prince && actor.has_role(Role::NC) {
        if actor.country.is_some() && actor.country == target.country {
            return PermissionResult::allow();
        }
        return PermissionResult::deny("NC can only change Prince role in their own country");
    }

    PermissionResult::deny(&format!(
        "You don't have permission to change the {} role",
        role.as_str()
    ))
}

/// Check if actor can manage VEKN IDs for target user (link, force-abandon, merge).
/// Sponsoring is NOT covered here: any official may sponsor cross-country
/// (backend /vekn/sponsor gates on is_official only).
///
/// Rules:
/// - IC: can manage anyone
/// - NC/Prince: can manage same country only
pub fn can_manage_vekn(actor: &UserContext, target: &UserContext) -> PermissionResult {
    // IC can manage anyone
    if actor.has_role(Role::IC) {
        return PermissionResult::allow();
    }

    // NC or Prince can manage same country
    if actor.has_role(Role::NC) || actor.has_role(Role::Prince) {
        if actor.country.is_some() && actor.country == target.country {
            return PermissionResult::allow();
        }
        return PermissionResult::deny("You can only manage VEKN IDs for users in your country");
    }

    PermissionResult::deny("Only IC, NC, or Prince can manage VEKN IDs")
}

/// Check if actor can edit a user's profile fields.
///
/// Rules:
/// - Users can edit their own profile
/// - IC can edit anyone
/// - NC/Prince can edit same country
pub fn can_edit_user(
    actor: &UserContext,
    actor_uid: &str,
    target_uid: &str,
    target: &UserContext,
) -> PermissionResult {
    // Users can edit their own profile
    if actor_uid == target_uid {
        return PermissionResult::allow();
    }

    // IC can edit anyone
    if actor.has_role(Role::IC) {
        return PermissionResult::allow();
    }

    // NC or Prince can edit same country
    if actor.has_role(Role::NC) || actor.has_role(Role::Prince) {
        if actor.country.is_some() && actor.country == target.country {
            return PermissionResult::allow();
        }
        return PermissionResult::deny("You can only edit users in your country");
    }

    PermissionResult::deny("You don't have permission to edit this user")
}

/// A tournament or league reduced to the fields needed for ownership checks.
///
/// The route/frontend fetches the full object and passes only this flat
/// descriptor across the binding boundary — never the whole object.
#[derive(Debug, Clone, Default)]
pub struct OwnedResource {
    pub country: Option<String>,
    pub organizers_uids: Vec<String>,
}

impl OwnedResource {
    pub fn from_json(value: &JsonValue) -> Self {
        OwnedResource {
            country: value["country"].as_str().map(|s| s.to_string()),
            organizers_uids: value["organizers_uids"]
                .members()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect(),
        }
    }
}

/// The "official" roles that can create/manage tournaments and members.
/// Single source for that list — consumed here (Role enum) and by
/// ActorContext::can_manage_tournaments (raw role strings); a role
/// addition/rename must not diverge who can create vs manage tournaments.
pub const OFFICIAL_ROLES: [Role; 3] = [Role::IC, Role::NC, Role::Prince];

pub fn is_official(actor: &UserContext) -> bool {
    OFFICIAL_ROLES.iter().any(|&r| actor.has_role(r))
}

/// IC manages any country; NC/Prince only their own (and must have one).
fn manages_country(actor: &UserContext, target_country: Option<&str>) -> bool {
    if actor.has_role(Role::IC) {
        return true;
    }
    if actor.has_role(Role::NC) || actor.has_role(Role::Prince) {
        return actor.country.is_some() && actor.country.as_deref() == target_country;
    }
    false
}

/// Check if actor can manage users/resources scoped to a country.
pub fn can_manage_country(actor: &UserContext, target_country: Option<&str>) -> PermissionResult {
    if manages_country(actor, target_country) {
        PermissionResult::allow()
    } else {
        PermissionResult::deny("You can only manage users in your own country")
    }
}

/// Check if actor can mark/clear a member's deceased status.
///
/// IC manages any country; NC only their own (Prince excluded — a deceased
/// flag is an administrative member-status call, reserved to IC/NC). Set and
/// clear are symmetric (same permission).
pub fn can_mark_deceased(actor: &UserContext, target_country: Option<&str>) -> PermissionResult {
    if actor.has_role(Role::IC) {
        return PermissionResult::allow();
    }
    if actor.has_role(Role::NC)
        && actor.country.is_some()
        && actor.country.as_deref() == target_country
    {
        return PermissionResult::allow();
    }
    PermissionResult::deny(
        "Only IC, or the member's national coordinator, can change deceased status",
    )
}

/// Check if actor can soft-delete a member (IC only).
///
/// The inverse of marking deceased: reserved to IC, and only ever applied to
/// VEKN-less members (junk/legacy-import shells). That the target must be
/// VEKN-less is a target-state rule enforced at the application layer — a
/// VEKN-bearing member would just be recreated by the next VEKN sync and is
/// handled via deceased status instead.
pub fn can_delete_member(actor: &UserContext) -> PermissionResult {
    if actor.has_role(Role::IC) {
        return PermissionResult::allow();
    }
    PermissionResult::deny("Only IC can delete members")
}

/// Check if actor can create/manage tournaments (IC/NC/Prince).
pub fn can_manage_tournaments(actor: &UserContext) -> PermissionResult {
    if is_official(actor) {
        PermissionResult::allow()
    } else {
        PermissionResult::deny("Only IC, NC, or Prince can manage tournaments")
    }
}

/// Check if actor can create/delete leagues (IC/NC).
pub fn can_manage_leagues(actor: &UserContext) -> PermissionResult {
    if actor.has_role(Role::IC) || actor.has_role(Role::NC) {
        PermissionResult::allow()
    } else {
        PermissionResult::deny("Only IC or NC can manage leagues")
    }
}

/// Check if actor is an organizer of a tournament: an explicit organizer, or an
/// implicit one — IC (any tournament) or NC (same country as the tournament).
pub fn is_organizer(actor: &UserContext, actor_uid: &str, tournament: &OwnedResource) -> bool {
    if tournament.organizers_uids.iter().any(|u| u == actor_uid) {
        return true;
    }
    if actor.has_role(Role::IC) {
        return true;
    }
    actor.has_role(Role::NC)
        && actor.country.is_some()
        && tournament.country.is_some()
        && actor.country.as_deref() == tournament.country.as_deref()
}

/// Check if actor can edit a league: IC, NC (same country), or a league organizer.
pub fn can_edit_league(
    actor: &UserContext,
    actor_uid: &str,
    league: &OwnedResource,
) -> PermissionResult {
    let allowed = actor.has_role(Role::IC)
        || (actor.has_role(Role::NC)
            && actor.country.is_some()
            && actor.country.as_deref() == league.country.as_deref())
        || league.organizers_uids.iter().any(|u| u == actor_uid);
    if allowed {
        PermissionResult::allow()
    } else {
        PermissionResult::deny("You don't have permission to edit this league")
    }
}

/// Context for a sanction lift/delete decision: the sanction level plus the
/// relevant fields of the (caller-fetched) tournament and league.
#[derive(Debug, Clone, Default)]
pub struct SanctionContext {
    pub level: String,
    pub tournament_country: Option<String>,
    pub tournament_state: String,
    pub tournament_organizers_uids: Vec<String>,
    pub league_organizers_uids: Vec<String>,
}

impl SanctionContext {
    pub fn from_json(value: &JsonValue) -> Self {
        SanctionContext {
            level: value["level"].as_str().unwrap_or("").to_string(),
            tournament_country: value["tournament_country"].as_str().map(|s| s.to_string()),
            tournament_state: value["tournament_state"].as_str().unwrap_or("").to_string(),
            tournament_organizers_uids: value["tournament_organizers_uids"]
                .members()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect(),
            league_organizers_uids: value["league_organizers_uids"]
                .members()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect(),
        }
    }
}

/// Check if actor can issue a sanction of `level`.
///
/// - SUSPENSION/PROBATION: IC or Ethics only.
/// - Otherwise (CAUTION/WARNING/SA/DQ): IC, Ethics, or an organizer of the
///   tournament the sanction is attached to.
pub fn can_issue_sanction(
    issuer: &UserContext,
    issuer_uid: &str,
    level: &str,
    tournament: &OwnedResource,
) -> PermissionResult {
    let is_ic_or_ethics = issuer.has_role(Role::IC) || issuer.has_role(Role::Ethics);
    if level == "suspension" || level == "probation" {
        return if is_ic_or_ethics {
            PermissionResult::allow()
        } else {
            PermissionResult::deny("Only IC or Ethics can issue suspensions or probations")
        };
    }
    if is_ic_or_ethics || tournament.organizers_uids.iter().any(|u| u == issuer_uid) {
        return PermissionResult::allow();
    }
    PermissionResult::deny("Only IC, Ethics, or a tournament organizer can issue this sanction")
}

/// Check if actor can lift a sanction.
///
/// - SUSPENSION/PROBATION: IC or Ethics.
/// - Otherwise: IC or Rulemonger (any); NC of the tournament's country; or a
///   league organizer (for a DQ in a league tournament).
pub fn can_lift_sanction(
    user: &UserContext,
    user_uid: &str,
    ctx: &SanctionContext,
) -> PermissionResult {
    if ctx.level == "suspension" || ctx.level == "probation" {
        return if user.has_role(Role::IC) || user.has_role(Role::Ethics) {
            PermissionResult::allow()
        } else {
            PermissionResult::deny("Only IC or Ethics can lift suspensions or probations")
        };
    }
    if user.has_role(Role::IC) || user.has_role(Role::Rulemonger) {
        return PermissionResult::allow();
    }
    // NC of the same country as the tournament
    if user.has_role(Role::NC)
        && user.country.is_some()
        && ctx.tournament_country.is_some()
        && user.country.as_deref() == ctx.tournament_country.as_deref()
    {
        return PermissionResult::allow();
    }
    // League organizer can lift a DQ in their league tournament
    if ctx.level == "disqualification" && ctx.league_organizers_uids.iter().any(|u| u == user_uid) {
        return PermissionResult::allow();
    }
    PermissionResult::deny("You don't have permission to lift this sanction")
}

/// Check if actor can delete a sanction.
///
/// - IC or Ethics: any sanction.
/// - A tournament organizer: organizer-issuable levels (CAUTION/WARNING/SA/DQ)
///   attached to their tournament, while it is not Finished — so a sanction
///   issued by mistake can be removed at the event without escalating.
pub fn can_delete_sanction(
    user: &UserContext,
    user_uid: &str,
    ctx: &SanctionContext,
) -> PermissionResult {
    if user.has_role(Role::IC) || user.has_role(Role::Ethics) {
        return PermissionResult::allow();
    }
    let organizer_issuable = matches!(
        ctx.level.as_str(),
        "caution" | "warning" | "standings_adjustment" | "disqualification"
    );
    if organizer_issuable
        && ctx.tournament_state != "Finished"
        && ctx.tournament_organizers_uids.iter().any(|u| u == user_uid)
    {
        return PermissionResult::allow();
    }
    PermissionResult::deny("You don't have permission to delete this sanction")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ic_can_change_any_role() {
        let ic = UserContext {
            roles: vec![Role::IC],
            country: Some("US".to_string()),
            vekn_id: Some("1000001".to_string()),
        };
        let target = UserContext {
            roles: vec![],
            country: Some("FR".to_string()),
            vekn_id: Some("2000001".to_string()),
        };

        // IC can change any role
        assert!(can_change_role(&ic, &target, Role::Prince).allowed);
        assert!(can_change_role(&ic, &target, Role::NC).allowed);
        assert!(can_change_role(&ic, &target, Role::PT).allowed);
        assert!(can_change_role(&ic, &target, Role::Judge).allowed);
    }

    #[test]
    fn test_nc_can_only_change_prince_same_country() {
        let nc = UserContext {
            roles: vec![Role::NC],
            country: Some("FR".to_string()),
            vekn_id: Some("1000001".to_string()),
        };
        let target_same = UserContext {
            roles: vec![],
            country: Some("FR".to_string()),
            vekn_id: Some("2000001".to_string()),
        };
        let target_diff = UserContext {
            roles: vec![],
            country: Some("US".to_string()),
            vekn_id: Some("3000001".to_string()),
        };

        // NC can change Prince in same country
        assert!(can_change_role(&nc, &target_same, Role::Prince).allowed);

        // NC cannot change Prince in different country
        assert!(!can_change_role(&nc, &target_diff, Role::Prince).allowed);

        // NC cannot change other roles
        assert!(!can_change_role(&nc, &target_same, Role::NC).allowed);
        assert!(!can_change_role(&nc, &target_same, Role::PT).allowed);
    }

    #[test]
    fn test_ptc_can_change_pt_any_country() {
        let ptc = UserContext {
            roles: vec![Role::PTC],
            country: Some("US".to_string()),
            vekn_id: Some("1000001".to_string()),
        };
        let target = UserContext {
            roles: vec![],
            country: Some("FR".to_string()),
            vekn_id: Some("2000001".to_string()),
        };

        // PTC can change PT in any country
        assert!(can_change_role(&ptc, &target, Role::PT).allowed);

        // PTC cannot change other roles
        assert!(!can_change_role(&ptc, &target, Role::Prince).allowed);
        assert!(!can_change_role(&ptc, &target, Role::Judge).allowed);
    }

    #[test]
    fn test_rulemonger_can_change_judge_any_country() {
        let rm = UserContext {
            roles: vec![Role::Rulemonger],
            country: Some("US".to_string()),
            vekn_id: Some("1000001".to_string()),
        };
        let target = UserContext {
            roles: vec![],
            country: Some("FR".to_string()),
            vekn_id: Some("2000001".to_string()),
        };

        // Rulemonger can change Judge and Judgekin in any country
        assert!(can_change_role(&rm, &target, Role::Judge).allowed);
        assert!(can_change_role(&rm, &target, Role::Judgekin).allowed);

        // Rulemonger cannot change other roles
        assert!(!can_change_role(&rm, &target, Role::Prince).allowed);
        assert!(!can_change_role(&rm, &target, Role::PT).allowed);
    }

    #[test]
    fn test_target_needs_vekn_id_for_roles() {
        let ic = UserContext {
            roles: vec![Role::IC],
            country: Some("US".to_string()),
            vekn_id: Some("1000001".to_string()),
        };
        let target_no_vekn = UserContext {
            roles: vec![],
            country: Some("FR".to_string()),
            vekn_id: None,
        };

        // Cannot assign roles to user without VEKN ID
        let result = can_change_role(&ic, &target_no_vekn, Role::Prince);
        assert!(!result.allowed);
        assert!(result.reason.unwrap().contains("VEKN ID"));
    }

    #[test]
    fn test_can_manage_vekn() {
        let ic = UserContext {
            roles: vec![Role::IC],
            country: Some("US".to_string()),
            vekn_id: Some("1000001".to_string()),
        };
        let nc = UserContext {
            roles: vec![Role::NC],
            country: Some("FR".to_string()),
            vekn_id: Some("2000001".to_string()),
        };
        let target_fr = UserContext {
            roles: vec![],
            country: Some("FR".to_string()),
            vekn_id: None,
        };
        let target_us = UserContext {
            roles: vec![],
            country: Some("US".to_string()),
            vekn_id: None,
        };

        // IC can manage anyone
        assert!(can_manage_vekn(&ic, &target_fr).allowed);
        assert!(can_manage_vekn(&ic, &target_us).allowed);

        // NC can only manage same country
        assert!(can_manage_vekn(&nc, &target_fr).allowed);
        assert!(!can_manage_vekn(&nc, &target_us).allowed);
    }

    fn ctx(roles: Vec<Role>, country: Option<&str>) -> UserContext {
        UserContext {
            roles,
            country: country.map(|s| s.to_string()),
            vekn_id: Some("1000001".to_string()),
        }
    }

    #[test]
    fn test_is_official_and_can_manage_tournaments() {
        for role in [Role::IC, Role::NC, Role::Prince] {
            assert!(is_official(&ctx(vec![role], Some("FR"))));
            assert!(can_manage_tournaments(&ctx(vec![role], Some("FR"))).allowed);
        }
        assert!(!is_official(&ctx(vec![Role::Judge], Some("FR"))));
        assert!(!can_manage_tournaments(&ctx(vec![], Some("FR"))).allowed);
    }

    #[test]
    fn test_can_manage_country() {
        // IC manages any country
        assert!(can_manage_country(&ctx(vec![Role::IC], Some("US")), Some("FR")).allowed);
        // NC/Prince only their own
        assert!(can_manage_country(&ctx(vec![Role::NC], Some("FR")), Some("FR")).allowed);
        assert!(!can_manage_country(&ctx(vec![Role::NC], Some("FR")), Some("US")).allowed);
        assert!(can_manage_country(&ctx(vec![Role::Prince], Some("FR")), Some("FR")).allowed);
        // No country → cannot manage
        assert!(!can_manage_country(&ctx(vec![Role::NC], None), None).allowed);
        // Non-official → never
        assert!(!can_manage_country(&ctx(vec![Role::Judge], Some("FR")), Some("FR")).allowed);
    }

    #[test]
    fn test_can_mark_deceased() {
        // IC: any country
        assert!(can_mark_deceased(&ctx(vec![Role::IC], Some("US")), Some("FR")).allowed);
        // NC: same country only
        assert!(can_mark_deceased(&ctx(vec![Role::NC], Some("FR")), Some("FR")).allowed);
        assert!(!can_mark_deceased(&ctx(vec![Role::NC], Some("FR")), Some("US")).allowed);
        // Prince is excluded, even in their own country
        assert!(!can_mark_deceased(&ctx(vec![Role::Prince], Some("FR")), Some("FR")).allowed);
        // NC with no country cannot manage
        assert!(!can_mark_deceased(&ctx(vec![Role::NC], None), None).allowed);
        // Non-official never
        assert!(!can_mark_deceased(&ctx(vec![Role::Judge], Some("FR")), Some("FR")).allowed);
    }

    #[test]
    fn test_can_delete_member() {
        // IC only, country-agnostic
        assert!(can_delete_member(&ctx(vec![Role::IC], Some("US"))).allowed);
        assert!(can_delete_member(&ctx(vec![Role::IC], None)).allowed);
        // NC/Prince/others never
        assert!(!can_delete_member(&ctx(vec![Role::NC], Some("FR"))).allowed);
        assert!(!can_delete_member(&ctx(vec![Role::Prince], Some("FR"))).allowed);
        assert!(!can_delete_member(&ctx(vec![Role::Judge], Some("FR"))).allowed);
        assert!(!can_delete_member(&ctx(vec![], Some("FR"))).allowed);
    }

    #[test]
    fn test_can_manage_leagues() {
        assert!(can_manage_leagues(&ctx(vec![Role::IC], Some("US"))).allowed);
        assert!(can_manage_leagues(&ctx(vec![Role::NC], Some("FR"))).allowed);
        // Prince does NOT manage leagues
        assert!(!can_manage_leagues(&ctx(vec![Role::Prince], Some("FR"))).allowed);
        assert!(!can_manage_leagues(&ctx(vec![], Some("FR"))).allowed);
    }

    #[test]
    fn test_is_organizer() {
        let tournament = OwnedResource {
            country: Some("FR".to_string()),
            organizers_uids: vec!["org-1".to_string()],
        };
        // Explicit organizer
        assert!(is_organizer(&ctx(vec![], Some("US")), "org-1", &tournament));
        // IC is implicit organizer of any tournament
        assert!(is_organizer(
            &ctx(vec![Role::IC], Some("US")),
            "someone",
            &tournament
        ));
        // NC same country
        assert!(is_organizer(
            &ctx(vec![Role::NC], Some("FR")),
            "someone",
            &tournament
        ));
        // NC different country
        assert!(!is_organizer(
            &ctx(vec![Role::NC], Some("US")),
            "someone",
            &tournament
        ));
        // Prince is NOT an implicit organizer
        assert!(!is_organizer(
            &ctx(vec![Role::Prince], Some("FR")),
            "someone",
            &tournament
        ));
        // Unrelated user
        assert!(!is_organizer(
            &ctx(vec![], Some("FR")),
            "nobody",
            &tournament
        ));
    }

    #[test]
    fn test_can_edit_league() {
        let league = OwnedResource {
            country: Some("FR".to_string()),
            organizers_uids: vec!["org-1".to_string()],
        };
        assert!(can_edit_league(&ctx(vec![Role::IC], Some("US")), "x", &league).allowed);
        assert!(can_edit_league(&ctx(vec![Role::NC], Some("FR")), "x", &league).allowed);
        assert!(!can_edit_league(&ctx(vec![Role::NC], Some("US")), "x", &league).allowed);
        // League organizer (no role)
        assert!(can_edit_league(&ctx(vec![], Some("US")), "org-1", &league).allowed);
        // Prince is not a league editor by role
        assert!(!can_edit_league(&ctx(vec![Role::Prince], Some("FR")), "x", &league).allowed);
        assert!(!can_edit_league(&ctx(vec![], Some("FR")), "nobody", &league).allowed);
    }

    #[test]
    fn test_can_issue_sanction() {
        let no_t = OwnedResource::default();
        let t = OwnedResource {
            country: None,
            organizers_uids: vec!["org-1".to_string()],
        };
        // Suspension/probation: IC or Ethics only
        assert!(can_issue_sanction(&ctx(vec![Role::IC], None), "x", "suspension", &no_t).allowed);
        assert!(
            can_issue_sanction(&ctx(vec![Role::Ethics], None), "x", "probation", &no_t).allowed
        );
        assert!(!can_issue_sanction(&ctx(vec![Role::NC], None), "x", "suspension", &no_t).allowed);
        // Organizer cannot issue a suspension
        assert!(!can_issue_sanction(&ctx(vec![], None), "org-1", "suspension", &t).allowed);
        // Tournament-level: IC/Ethics or an organizer
        assert!(can_issue_sanction(&ctx(vec![Role::IC], None), "x", "caution", &no_t).allowed);
        assert!(can_issue_sanction(&ctx(vec![], None), "org-1", "warning", &t).allowed);
        // Non-organizer, no privileged role
        assert!(!can_issue_sanction(&ctx(vec![], None), "nobody", "caution", &t).allowed);
    }

    #[test]
    fn test_can_lift_sanction() {
        let lift = |roles, country, uid: &str, level: &str, t_country, league_orgs: Vec<&str>| {
            can_lift_sanction(
                &ctx(roles, country),
                uid,
                &SanctionContext {
                    level: level.to_string(),
                    tournament_country: t_country,
                    league_organizers_uids: league_orgs.iter().map(|s| s.to_string()).collect(),
                    ..Default::default()
                },
            )
            .allowed
        };
        // Suspension/probation: IC or Ethics
        assert!(lift(vec![Role::IC], None, "x", "suspension", None, vec![]));
        assert!(lift(
            vec![Role::Ethics],
            None,
            "x",
            "probation",
            None,
            vec![]
        ));
        assert!(!lift(
            vec![Role::Rulemonger],
            None,
            "x",
            "suspension",
            None,
            vec![]
        ));
        // Tournament-level: IC or Rulemonger always
        assert!(lift(
            vec![Role::Rulemonger],
            None,
            "x",
            "caution",
            None,
            vec![]
        ));
        // NC of the tournament's country
        assert!(lift(
            vec![Role::NC],
            Some("FR"),
            "x",
            "warning",
            Some("FR".to_string()),
            vec![]
        ));
        assert!(!lift(
            vec![Role::NC],
            Some("US"),
            "x",
            "warning",
            Some("FR".to_string()),
            vec![]
        ));
        // League organizer can lift a DQ
        assert!(lift(
            vec![],
            None,
            "org-1",
            "disqualification",
            None,
            vec!["org-1"]
        ));
        // ...but not a non-DQ sanction
        assert!(!lift(vec![], None, "org-1", "warning", None, vec!["org-1"]));
        // Nobody
        assert!(!lift(vec![], None, "nobody", "caution", None, vec![]));
    }

    #[test]
    fn test_can_delete_sanction() {
        let del = |roles, uid: &str, level: &str, t_state: &str, t_orgs: Vec<&str>| {
            can_delete_sanction(
                &ctx(roles, None),
                uid,
                &SanctionContext {
                    level: level.to_string(),
                    tournament_state: t_state.to_string(),
                    tournament_organizers_uids: t_orgs.iter().map(|s| s.to_string()).collect(),
                    ..Default::default()
                },
            )
            .allowed
        };
        // IC/Ethics: any sanction
        assert!(del(vec![Role::IC], "x", "suspension", "", vec![]));
        assert!(del(vec![Role::Ethics], "x", "warning", "Finished", vec![]));
        // Organizer: issuable levels on their own open tournament
        assert!(del(vec![], "org-1", "caution", "Playing", vec!["org-1"]));
        assert!(del(
            vec![],
            "org-1",
            "disqualification",
            "Waiting",
            vec!["org-1"]
        ));
        // ...but not once the tournament is finished
        assert!(!del(vec![], "org-1", "warning", "Finished", vec!["org-1"]));
        // ...and never suspension/probation
        assert!(!del(
            vec![],
            "org-1",
            "suspension",
            "Playing",
            vec!["org-1"]
        ));
        // Non-organizer without privileged role
        assert!(!del(
            vec![Role::NC],
            "x",
            "caution",
            "Playing",
            vec!["org-1"]
        ));
    }
}
