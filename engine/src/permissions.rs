//! Authorization: every rule in the stack, expressed as one declarative table.
//!
//! A capability names a distinct authority ("edit a member's profile", "issue a
//! suspension"). [`CAPABILITIES`] maps each one to the roles that hold it and the
//! scope they hold it in; [`ROLE_APPOINTMENTS`] does the same for who may grant
//! or revoke each role. Both are data — a change to the role matrix edits a row,
//! not a function.
//!
//! Everything below the tables is either the evaluator ([`check`]) or a resolver:
//! a thin function for the handful of rules that need a precondition the table
//! cannot express (a sanction's level, a tournament's state, a target's own
//! roles). Deny by default: a capability with no matching grant is refused.
//!
//! This module is the only place a role literal may be used to *decide* access.
//! Backend routes and frontend gates are callers; see backend/src/permissions.py
//! and frontend/src/lib/engine.ts.

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

    /// Every variant, so the tables below can be checked for completeness.
    pub const ALL: [Role; 10] = [
        Role::IC,
        Role::NC,
        Role::Prince,
        Role::Ethics,
        Role::PTC,
        Role::PT,
        Role::Rulemonger,
        Role::Judge,
        Role::Judgekin,
        Role::DEV,
    ];
}

// Short names for the tables — they only read as a matrix without the prefix.
use Role::{Ethics, Judge, Judgekin, Prince, Rulemonger, DEV, IC, NC, PT, PTC};

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

    fn has_any(&self, roles: &[Role]) -> bool {
        roles.iter().any(|&r| self.has_role(r))
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

/// A tournament or league reduced to the fields needed for ownership checks.
///
/// The route/frontend fetches the full object and passes only this flat
/// descriptor across the binding boundary — never the whole object.
#[derive(Debug, Clone, Default)]
pub struct OwnedResource {
    pub country: Option<String>,
    pub organizers_uids: Vec<String>,
    /// League-only: same-country Princes may attach their own tournaments
    /// (attach-only — grants no other league rights).
    pub open_to_country_princes: bool,
}

impl OwnedResource {
    pub fn from_json(value: &JsonValue) -> Self {
        OwnedResource {
            country: value["country"].as_str().map(|s| s.to_string()),
            organizers_uids: value["organizers_uids"]
                .members()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect(),
            open_to_country_princes: value["open_to_country_princes"].as_bool().unwrap_or(false),
        }
    }

    fn has_organizer(&self, uid: &str) -> bool {
        self.organizers_uids.iter().any(|u| u == uid)
    }
}

// ============================================================================
// Capabilities
// ============================================================================

/// A distinct authority somebody may hold. One variant per thing the stack gates
/// on; every variant must have exactly one [`CAPABILITIES`] row (asserted below).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Capability {
    // Members
    CreateMember,
    EditMemberProfile,
    DeleteMember,
    MarkDeceased,
    ManageVekn,
    SponsorVekn,
    MergeAccounts,
    // Tournaments & leagues
    CreateTournament,
    OrganizeTournament,
    ForceUnlockTournament,
    ManageLeagues,
    EditLeague,
    // Community links
    ModerateLink,
    PromoteLinkNational,
    PromoteLinkGlobal,
    // Sanctions
    IssueRestrictedSanction,
    IssueTournamentSanction,
    LiftRestrictedSanction,
    LiftTournamentSanction,
    LiftLeagueDisqualification,
    ModifySanction,
    DeleteAnySanction,
    DeleteOrganizerSanction,
    // Admin
    ManagePromos,
    RecordPromoIntake,
    ViewFullPromoLedger,
    ManageOauthClients,
    RunAdminSync,
}

impl Capability {
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(s: &str) -> Option<Self> {
        CAPABILITIES
            .iter()
            .find(|r| r.name == s)
            .map(|r| r.capability)
    }

    pub fn as_str(&self) -> &'static str {
        rule_for(*self).name
    }
}

/// One row of the capability table: who holds this authority, and in what scope.
///
/// The grants are OR-ed — the actor needs one of them. An empty list or a false
/// flag grants nothing, so a row that lists nothing denies everyone.
pub struct Rule {
    pub capability: Capability,
    /// Wire name, used by the PyO3/WASM `check_permission` entry point.
    pub name: &'static str,
    /// Roles that hold the capability everywhere.
    pub global: &'static [Role],
    /// Roles that hold it only over their own country: the actor must have a
    /// country and it must equal the request's `target_country`.
    pub same_country: &'static [Role],
    /// The actor acting on themselves (`target_uid` == `actor_uid`).
    pub self_service: bool,
    /// An organizer of the request's resource (tournament or league).
    pub organizer: bool,
    /// User-facing denial.
    pub deny: &'static str,
    /// Denial used instead when the actor holds a `same_country` role but the
    /// countries differ — "you, but not here" rather than "not you".
    pub deny_scope: Option<&'static str>,
}

/// The "official" roles that create tournaments and members. Shared by the three
/// rows below and by `ActorContext::can_manage_tournaments` (raw role strings),
/// so a role addition/rename cannot make "create" and "manage" diverge.
pub const OFFICIAL_ROLES: [Role; 3] = [IC, NC, Prince];

/// **The permission matrix.** Deny by default; a role appears here or it has no
/// authority. Owner-approved matrix of 2026-08-04 — see .pst/details/538.
pub const CAPABILITIES: &[Rule] = &[
    // ---- Members ----------------------------------------------------------
    Rule {
        capability: Capability::CreateMember,
        name: "create_member",
        global: &OFFICIAL_ROLES,
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC, NC, or Prince can create members",
        deny_scope: None,
    },
    Rule {
        capability: Capability::EditMemberProfile,
        name: "edit_member_profile",
        global: &[IC],
        same_country: &[NC],
        self_service: true,
        organizer: false,
        deny: "You don't have permission to edit this user",
        deny_scope: Some("You can only edit users in your country"),
    },
    Rule {
        capability: Capability::DeleteMember,
        name: "delete_member",
        global: &[IC],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC can delete members",
        deny_scope: None,
    },
    Rule {
        capability: Capability::MarkDeceased,
        name: "mark_deceased",
        global: &[IC],
        same_country: &[NC],
        self_service: false,
        organizer: false,
        deny: "Only IC, or the member's national coordinator, can change deceased status",
        deny_scope: None,
    },
    Rule {
        capability: Capability::ManageVekn,
        name: "manage_vekn",
        global: &[IC],
        same_country: &[NC],
        self_service: false,
        organizer: false,
        deny: "Only IC, or the member's national coordinator, can manage VEKN IDs",
        deny_scope: Some("You can only manage VEKN IDs for users in your country"),
    },
    // Deliberately cross-country: any official may sponsor a VEKN ID anywhere.
    Rule {
        capability: Capability::SponsorVekn,
        name: "sponsor_vekn",
        global: &OFFICIAL_ROLES,
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC, NC, or Prince can sponsor VEKN IDs",
        deny_scope: None,
    },
    // IC-only: the merge unions both accounts' roles, so anyone who could merge
    // could land a role by absorbing a shell that carries it.
    Rule {
        capability: Capability::MergeAccounts,
        name: "merge_accounts",
        global: &[IC],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC can merge accounts",
        deny_scope: None,
    },
    // ---- Tournaments & leagues -------------------------------------------
    Rule {
        capability: Capability::CreateTournament,
        name: "create_tournament",
        global: &OFFICIAL_ROLES,
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC, NC, or Prince can manage tournaments",
        deny_scope: None,
    },
    // Implicit organizers: IC anywhere, NC over their own country.
    Rule {
        capability: Capability::OrganizeTournament,
        name: "organize_tournament",
        global: &[IC],
        same_country: &[NC],
        self_service: false,
        organizer: true,
        deny: "You are not an organizer of this tournament",
        deny_scope: None,
    },
    Rule {
        capability: Capability::ForceUnlockTournament,
        name: "force_unlock_tournament",
        global: &[IC],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC can force-unlock a tournament",
        deny_scope: None,
    },
    Rule {
        capability: Capability::ManageLeagues,
        name: "manage_leagues",
        global: &[IC, NC],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC or NC can manage leagues",
        deny_scope: None,
    },
    Rule {
        capability: Capability::EditLeague,
        name: "edit_league",
        global: &[IC],
        same_country: &[NC],
        self_service: false,
        organizer: true,
        deny: "You don't have permission to edit this league",
        deny_scope: None,
    },
    // ---- Community links --------------------------------------------------
    // Officials pin and clear their own links through the same grant — an NC is
    // trivially in their own country — so no self-service row is needed.
    Rule {
        capability: Capability::ModerateLink,
        name: "moderate_link",
        global: &[IC],
        same_country: &[NC],
        self_service: false,
        organizer: false,
        deny: "You don't have permission to moderate this member's links",
        deny_scope: Some("You can only moderate links for members in your country"),
    },
    Rule {
        capability: Capability::PromoteLinkNational,
        name: "promote_link_national",
        global: &[IC],
        same_country: &[NC],
        self_service: false,
        organizer: false,
        deny: "Only IC, or the member's national coordinator, can promote a link nationally",
        deny_scope: None,
    },
    Rule {
        capability: Capability::PromoteLinkGlobal,
        name: "promote_link_global",
        global: &[IC],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC can promote a link globally",
        deny_scope: None,
    },
    // ---- Sanctions --------------------------------------------------------
    // "Restricted" = suspension/probation; see `restricted_level`.
    Rule {
        capability: Capability::IssueRestrictedSanction,
        name: "issue_restricted_sanction",
        global: &[IC, Ethics],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC or Ethics can issue suspensions or probations",
        deny_scope: None,
    },
    Rule {
        capability: Capability::IssueTournamentSanction,
        name: "issue_tournament_sanction",
        global: &[IC, Ethics],
        same_country: &[],
        self_service: false,
        organizer: true,
        deny: "Only IC, Ethics, or a tournament organizer can issue this sanction",
        deny_scope: None,
    },
    Rule {
        capability: Capability::LiftRestrictedSanction,
        name: "lift_restricted_sanction",
        global: &[IC, Ethics],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC or Ethics can lift suspensions or probations",
        deny_scope: None,
    },
    Rule {
        capability: Capability::LiftTournamentSanction,
        name: "lift_tournament_sanction",
        global: &[IC, Rulemonger],
        same_country: &[NC],
        self_service: false,
        organizer: false,
        deny: "You don't have permission to lift this sanction",
        deny_scope: None,
    },
    Rule {
        capability: Capability::LiftLeagueDisqualification,
        name: "lift_league_disqualification",
        global: &[],
        same_country: &[],
        self_service: false,
        organizer: true,
        deny: "You don't have permission to lift this sanction",
        deny_scope: None,
    },
    Rule {
        capability: Capability::ModifySanction,
        name: "modify_sanction",
        global: &[IC, Ethics],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC or Ethics can modify a sanction",
        deny_scope: None,
    },
    Rule {
        capability: Capability::DeleteAnySanction,
        name: "delete_any_sanction",
        global: &[IC, Ethics],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "You don't have permission to delete this sanction",
        deny_scope: None,
    },
    Rule {
        capability: Capability::DeleteOrganizerSanction,
        name: "delete_organizer_sanction",
        global: &[],
        same_country: &[],
        self_service: false,
        organizer: true,
        deny: "You don't have permission to delete this sanction",
        deny_scope: None,
    },
    // ---- Admin ------------------------------------------------------------
    Rule {
        capability: Capability::ManagePromos,
        name: "manage_promos",
        global: &[IC],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC can manage promos",
        deny_scope: None,
    },
    // NC records intakes and sees the whole ledger regardless of country.
    Rule {
        capability: Capability::RecordPromoIntake,
        name: "record_promo_intake",
        global: &[IC, NC],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC or NC can record promo intakes",
        deny_scope: None,
    },
    Rule {
        capability: Capability::ViewFullPromoLedger,
        name: "view_full_promo_ledger",
        global: &[IC, NC],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC or NC can view the full promo ledger",
        deny_scope: None,
    },
    Rule {
        capability: Capability::ManageOauthClients,
        name: "manage_oauth_clients",
        global: &[IC, DEV],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC or DEV can manage OAuth clients",
        deny_scope: None,
    },
    // Trigger and inspect the VEKN/TWDA sync jobs.
    Rule {
        capability: Capability::RunAdminSync,
        name: "run_admin_sync",
        global: &[IC],
        same_country: &[],
        self_service: false,
        organizer: false,
        deny: "Only IC can trigger a sync",
        deny_scope: None,
    },
];

/// Who may grant or revoke a role. Same shape as [`CAPABILITIES`]: `global`
/// applies anywhere, `same_country` only over the actor's own country.
pub struct Appointment {
    /// The role being granted or revoked.
    pub role: Role,
    pub global: &'static [Role],
    pub same_country: &'static [Role],
}

/// **The appointment matrix.** Every [`Role::ALL`] variant has a row (asserted
/// below) — a role missing from here would silently become unassignable.
pub const ROLE_APPOINTMENTS: &[Appointment] = &[
    Appointment {
        role: Prince,
        global: &[IC],
        same_country: &[NC],
    },
    Appointment {
        role: PT,
        global: &[IC, PTC],
        same_country: &[],
    },
    Appointment {
        role: Judge,
        global: &[IC, Rulemonger],
        same_country: &[],
    },
    Appointment {
        role: Judgekin,
        global: &[IC, Rulemonger],
        same_country: &[],
    },
    // Council-level roles and DEV: IC only.
    Appointment {
        role: IC,
        global: &[IC],
        same_country: &[],
    },
    Appointment {
        role: NC,
        global: &[IC],
        same_country: &[],
    },
    Appointment {
        role: Ethics,
        global: &[IC],
        same_country: &[],
    },
    Appointment {
        role: PTC,
        global: &[IC],
        same_country: &[],
    },
    Appointment {
        role: Rulemonger,
        global: &[IC],
        same_country: &[],
    },
    Appointment {
        role: DEV,
        global: &[IC],
        same_country: &[],
    },
];

// ============================================================================
// Evaluator
// ============================================================================

/// What a capability is being asked about. Only fill the fields the capability's
/// row actually uses — an absent field simply matches no grant.
#[derive(Debug, Clone)]
pub struct Request<'a> {
    pub actor: &'a UserContext,
    pub actor_uid: &'a str,
    pub target_uid: Option<&'a str>,
    pub target_country: Option<&'a str>,
    pub resource: Option<&'a OwnedResource>,
}

impl<'a> Request<'a> {
    pub fn new(actor: &'a UserContext, actor_uid: &'a str) -> Self {
        Request {
            actor,
            actor_uid,
            target_uid: None,
            target_country: None,
            resource: None,
        }
    }

    pub fn target_uid(mut self, uid: &'a str) -> Self {
        self.target_uid = Some(uid);
        self
    }

    pub fn target_country(mut self, country: Option<&'a str>) -> Self {
        self.target_country = country;
        self
    }

    pub fn resource(mut self, resource: &'a OwnedResource) -> Self {
        self.resource = Some(resource);
        self
    }

    /// The actor's country, when they have one and it matches the target's.
    fn in_own_country(&self) -> bool {
        self.actor.country.is_some() && self.actor.country.as_deref() == self.target_country
    }
}

pub fn rule_for(capability: Capability) -> &'static Rule {
    CAPABILITIES
        .iter()
        .find(|r| r.capability == capability)
        .expect("every Capability has a CAPABILITIES row (asserted by test)")
}

/// Evaluate one capability against one request. The single decision point:
/// every rule in the stack resolves to a call of this.
pub fn check(capability: Capability, req: &Request) -> PermissionResult {
    let rule = rule_for(capability);

    if rule.self_service && req.target_uid == Some(req.actor_uid) {
        return PermissionResult::allow();
    }
    if req.actor.has_any(rule.global) {
        return PermissionResult::allow();
    }
    if req.actor.has_any(rule.same_country) {
        if req.in_own_country() {
            return PermissionResult::allow();
        }
        // Held the role, wrong country — say so rather than "not you".
        if let Some(scoped) = rule.deny_scope {
            return PermissionResult::deny(scoped);
        }
    }
    if rule.organizer && req.resource.is_some_and(|r| r.has_organizer(req.actor_uid)) {
        return PermissionResult::allow();
    }
    PermissionResult::deny(rule.deny)
}

/// Convenience for the many call sites that only need the boolean.
pub fn allows(capability: Capability, req: &Request) -> bool {
    check(capability, req).allowed
}

/// Every capability the actor holds unconditionally — anywhere, over anyone.
///
/// What a remote client (the Discord bot) needs to decide what to offer without
/// carrying its own copy of the matrix. Country- and resource-scoped grants are
/// deliberately absent: they have no answer without a target, so a client that
/// wants one must ask for that specific case.
pub fn unconditional_capabilities(actor: &UserContext) -> Vec<&'static str> {
    CAPABILITIES
        .iter()
        .filter(|rule| actor.has_any(rule.global))
        .map(|rule| rule.name)
        .collect()
}

// ============================================================================
// Resolvers — rules with a precondition the table cannot express
// ============================================================================

fn appointment_for(role: Role) -> &'static Appointment {
    ROLE_APPOINTMENTS
        .iter()
        .find(|a| a.role == role)
        .expect("every Role has a ROLE_APPOINTMENTS row (asserted by test)")
}

/// Check if actor can grant or revoke `role` on target.
///
/// [`ROLE_APPOINTMENTS`] plus one target-state precondition: roles hang off a
/// VEKN ID, so a member without one cannot hold any.
pub fn can_change_role(actor: &UserContext, target: &UserContext, role: Role) -> PermissionResult {
    if target.vekn_id.is_none() {
        return PermissionResult::deny("User must have a VEKN ID to be assigned roles");
    }
    let appointment = appointment_for(role);
    if actor.has_any(appointment.global) {
        return PermissionResult::allow();
    }
    if actor.has_any(appointment.same_country) {
        if actor.country.is_some() && actor.country == target.country {
            return PermissionResult::allow();
        }
        return PermissionResult::deny(&format!(
            "You can only change the {} role in your own country",
            role.as_str()
        ));
    }
    PermissionResult::deny(&format!(
        "You don't have permission to change the {} role",
        role.as_str()
    ))
}

/// Official roles, highest authority first. Their country scopes a FULL-data
/// overlay, so changing it takes the authority that could change that role.
const OFFICIAL_ROLES_BY_AUTHORITY: [Role; 3] = [IC, NC, Prince];

/// Check if actor can change target's country.
///
/// For an official target, gated by the authority that could change their
/// highest official role — a self-service country change by an NC/Prince is an
/// unauthorized data-scope change. A non-official target is unrestricted
/// (ordinary self-service / same-country admin edit, already gated by
/// [`Capability::EditMemberProfile`]).
pub fn can_change_country(actor: &UserContext, target: &UserContext) -> PermissionResult {
    match OFFICIAL_ROLES_BY_AUTHORITY
        .iter()
        .find(|&&r| target.has_role(r))
    {
        // can_change_role's vekn_id precondition is unreachable here: an
        // official always has one (roles can't be assigned without it).
        Some(&highest) => can_change_role(actor, target, highest),
        None => PermissionResult::allow(),
    }
}

/// Whether a member holds the official badge (IC/NC/Prince).
///
/// Identity, not authority: this answers "is this person an official", and is
/// for badges and quotas only. Never gate on it — ask for the capability.
pub fn is_official(actor: &UserContext) -> bool {
    actor.has_any(&OFFICIAL_ROLES)
}

/// Check if actor is an organizer of a tournament: an explicit organizer, or an
/// implicit one — IC (any tournament) or NC (same country as the tournament).
pub fn is_organizer(actor: &UserContext, actor_uid: &str, tournament: &OwnedResource) -> bool {
    allows(
        Capability::OrganizeTournament,
        &Request::new(actor, actor_uid)
            .target_country(tournament.country.as_deref())
            .resource(tournament),
    )
}

/// Check if actor can edit a league: IC, NC (same country), or a league organizer.
pub fn can_edit_league(
    actor: &UserContext,
    actor_uid: &str,
    league: &OwnedResource,
) -> PermissionResult {
    check(
        Capability::EditLeague,
        &Request::new(actor, actor_uid)
            .target_country(league.country.as_deref())
            .resource(league),
    )
}

/// Check if actor can attach a tournament to a league: anyone who can edit the
/// league, or — when the league is open to country princes — a Prince of the
/// league's country. Attach-only: this never grants league edit rights, and a
/// worldwide league (no country) has no "country princes" to open up to.
pub fn can_link_tournament_to_league(
    actor: &UserContext,
    actor_uid: &str,
    league: &OwnedResource,
) -> PermissionResult {
    if can_edit_league(actor, actor_uid, league).allowed {
        return PermissionResult::allow();
    }
    if league.open_to_country_princes
        && actor.has_role(Prince)
        && actor.country.is_some()
        && actor.country.as_deref() == league.country.as_deref()
    {
        return PermissionResult::allow();
    }
    PermissionResult::deny("You don't have permission to attach tournaments to this league")
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

    fn league(&self) -> OwnedResource {
        OwnedResource {
            organizers_uids: self.league_organizers_uids.clone(),
            ..Default::default()
        }
    }

    fn tournament(&self) -> OwnedResource {
        OwnedResource {
            country: self.tournament_country.clone(),
            organizers_uids: self.tournament_organizers_uids.clone(),
            ..Default::default()
        }
    }
}

/// Levels only the Ethics chain may hand out or lift, at any level of the game.
fn restricted_level(level: &str) -> bool {
    level == "suspension" || level == "probation"
}

/// Levels a tournament organizer may issue, and so may also delete.
fn organizer_issuable(level: &str) -> bool {
    matches!(
        level,
        "caution" | "warning" | "standings_adjustment" | "disqualification"
    )
}

/// Check if actor can issue a sanction of `level`.
pub fn can_issue_sanction(
    issuer: &UserContext,
    issuer_uid: &str,
    level: &str,
    tournament: &OwnedResource,
) -> PermissionResult {
    let capability = if restricted_level(level) {
        Capability::IssueRestrictedSanction
    } else {
        Capability::IssueTournamentSanction
    };
    check(
        capability,
        &Request::new(issuer, issuer_uid).resource(tournament),
    )
}

/// Check if actor can lift a sanction.
///
/// Restricted levels are the Ethics chain's alone. Otherwise the tournament-level
/// grant applies, widened for a disqualification to the organizers of the league
/// the tournament belongs to.
pub fn can_lift_sanction(
    user: &UserContext,
    user_uid: &str,
    ctx: &SanctionContext,
) -> PermissionResult {
    if restricted_level(&ctx.level) {
        return check(
            Capability::LiftRestrictedSanction,
            &Request::new(user, user_uid),
        );
    }
    let result = check(
        Capability::LiftTournamentSanction,
        &Request::new(user, user_uid).target_country(ctx.tournament_country.as_deref()),
    );
    if result.allowed || ctx.level != "disqualification" {
        return result;
    }
    let league = ctx.league();
    check(
        Capability::LiftLeagueDisqualification,
        &Request::new(user, user_uid).resource(&league),
    )
}

/// Check if actor can delete a sanction.
///
/// IC/Ethics for any of them; an organizer only for what they could have issued,
/// and only while the tournament is unfinished — so a mistake can be undone at
/// the event without escalating.
pub fn can_delete_sanction(
    user: &UserContext,
    user_uid: &str,
    ctx: &SanctionContext,
) -> PermissionResult {
    let result = check(Capability::DeleteAnySanction, &Request::new(user, user_uid));
    if result.allowed || !organizer_issuable(&ctx.level) || ctx.tournament_state == "Finished" {
        return result;
    }
    let tournament = ctx.tournament();
    check(
        Capability::DeleteOrganizerSanction,
        &Request::new(user, user_uid).resource(&tournament),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ctx(roles: Vec<Role>, country: Option<&str>) -> UserContext {
        UserContext {
            roles,
            country: country.map(|s| s.to_string()),
            vekn_id: Some("1000001".to_string()),
        }
    }

    /// Evaluate a capability for an actor over a target country.
    fn over_country(cap: Capability, actor: &UserContext, country: Option<&str>) -> bool {
        allows(cap, &Request::new(actor, "actor").target_country(country))
    }

    // ---- Table integrity --------------------------------------------------

    #[test]
    fn test_every_capability_has_exactly_one_rule() {
        for rule in CAPABILITIES {
            let matches = CAPABILITIES
                .iter()
                .filter(|r| r.capability == rule.capability)
                .count();
            assert_eq!(matches, 1, "duplicate row for {:?}", rule.capability);
            // Round-trips through the wire name used by the bindings.
            assert_eq!(Capability::from_str(rule.name), Some(rule.capability));
        }
    }

    #[test]
    fn test_every_role_can_be_appointed_by_someone() {
        for role in Role::ALL {
            let appointment = appointment_for(role);
            assert!(
                !appointment.global.is_empty() || !appointment.same_country.is_empty(),
                "{} is unassignable",
                role.as_str()
            );
        }
    }

    #[test]
    fn test_ic_holds_every_capability() {
        // "IC may do anything" is the matrix's first line, and `require_role`
        // grants IC implicitly — the table must not contradict that.
        let ic = ctx(vec![IC], Some("US"));
        for rule in CAPABILITIES {
            // Role-less rows (lift_league_disqualification, delete_organizer_sanction)
            // widen an organizer's reach on top of a primary capability IC already
            // holds — they grant nobody anything by role, IC included.
            if rule.global.is_empty() && rule.same_country.is_empty() {
                continue;
            }
            assert!(ic.has_any(rule.global), "IC lacks {}", rule.name);
        }
    }

    #[test]
    fn test_unprivileged_user_holds_nothing() {
        let nobody = ctx(vec![Judge], Some("FR"));
        for rule in CAPABILITIES {
            if rule.self_service {
                continue; // covered by the per-capability tests
            }
            let req = Request::new(&nobody, "actor").target_country(Some("FR"));
            assert!(
                !allows(rule.capability, &req),
                "a bare Judge holds {}",
                rule.name
            );
        }
    }

    // ---- Evaluator semantics ---------------------------------------------

    #[test]
    fn test_same_country_needs_a_country_on_both_sides() {
        let cap = Capability::EditMemberProfile;
        assert!(over_country(cap, &ctx(vec![NC], Some("FR")), Some("FR")));
        assert!(!over_country(cap, &ctx(vec![NC], Some("FR")), Some("US")));
        // A countryless actor never matches, not even a countryless target.
        assert!(!over_country(cap, &ctx(vec![NC], None), None));
    }

    #[test]
    fn test_scoped_denial_distinguishes_wrong_country_from_no_role() {
        let req = |actor| Request::new(actor, "actor").target_country(Some("US"));
        let nc = ctx(vec![NC], Some("FR"));
        let judge = ctx(vec![Judge], Some("FR"));
        assert_eq!(
            check(Capability::EditMemberProfile, &req(&nc))
                .reason
                .unwrap(),
            "You can only edit users in your country"
        );
        assert_eq!(
            check(Capability::EditMemberProfile, &req(&judge))
                .reason
                .unwrap(),
            "You don't have permission to edit this user"
        );
    }

    #[test]
    fn test_self_service() {
        let user = ctx(vec![], Some("FR"));
        let req = |uid| Request::new(&user, "me").target_uid(uid);
        assert!(allows(Capability::EditMemberProfile, &req("me")));
        assert!(!allows(Capability::EditMemberProfile, &req("someone-else")));
        // A capability without self_service is not self-reachable.
        assert!(!allows(Capability::DeleteMember, &req("me")));
    }

    // ---- Members ----------------------------------------------------------

    #[test]
    fn test_edit_member_profile() {
        let cap = Capability::EditMemberProfile;
        assert!(over_country(cap, &ctx(vec![IC], Some("US")), Some("FR")));
        assert!(over_country(cap, &ctx(vec![NC], Some("FR")), Some("FR")));
        assert!(!over_country(cap, &ctx(vec![NC], Some("US")), Some("FR")));
        // A Prince holds no member-data authority, not even at home.
        assert!(!over_country(
            cap,
            &ctx(vec![Prince], Some("FR")),
            Some("FR")
        ));
        assert!(!over_country(
            cap,
            &ctx(vec![Judge], Some("FR")),
            Some("FR")
        ));
    }

    #[test]
    fn test_manage_vekn() {
        let cap = Capability::ManageVekn;
        assert!(over_country(cap, &ctx(vec![IC], Some("US")), Some("FR")));
        assert!(over_country(cap, &ctx(vec![NC], Some("FR")), Some("FR")));
        assert!(!over_country(cap, &ctx(vec![NC], Some("FR")), Some("US")));
        assert!(!over_country(
            cap,
            &ctx(vec![Prince], Some("FR")),
            Some("FR")
        ));
        assert!(!over_country(cap, &ctx(vec![], Some("FR")), Some("FR")));
    }

    #[test]
    fn test_create_member_and_sponsor_are_cross_country() {
        for cap in [Capability::CreateMember, Capability::SponsorVekn] {
            for role in OFFICIAL_ROLES {
                assert!(over_country(cap, &ctx(vec![role], Some("FR")), Some("US")));
            }
            assert!(!over_country(
                cap,
                &ctx(vec![Judge], Some("FR")),
                Some("FR")
            ));
        }
    }

    #[test]
    fn test_mark_deceased() {
        let cap = Capability::MarkDeceased;
        assert!(over_country(cap, &ctx(vec![IC], Some("US")), Some("FR")));
        assert!(over_country(cap, &ctx(vec![NC], Some("FR")), Some("FR")));
        assert!(!over_country(cap, &ctx(vec![NC], Some("FR")), Some("US")));
        // Prince is excluded, even in their own country: it's an administrative
        // member-status call.
        assert!(!over_country(
            cap,
            &ctx(vec![Prince], Some("FR")),
            Some("FR")
        ));
    }

    #[test]
    fn test_delete_member_is_ic_only() {
        let cap = Capability::DeleteMember;
        assert!(over_country(cap, &ctx(vec![IC], None), Some("FR")));
        assert!(!over_country(cap, &ctx(vec![NC], Some("FR")), Some("FR")));
        assert!(!over_country(
            cap,
            &ctx(vec![Prince], Some("FR")),
            Some("FR")
        ));
    }

    // ---- Role appointment -------------------------------------------------

    #[test]
    fn test_ic_can_change_any_role() {
        let ic = ctx(vec![IC], Some("US"));
        let target = ctx(vec![], Some("FR"));
        for role in Role::ALL {
            assert!(can_change_role(&ic, &target, role).allowed);
        }
    }

    #[test]
    fn test_nc_can_only_change_prince_same_country() {
        let nc = ctx(vec![NC], Some("FR"));
        let same = ctx(vec![], Some("FR"));
        let other = ctx(vec![], Some("US"));
        assert!(can_change_role(&nc, &same, Prince).allowed);
        assert!(!can_change_role(&nc, &other, Prince).allowed);
        assert!(!can_change_role(&nc, &same, NC).allowed);
        assert!(!can_change_role(&nc, &same, PT).allowed);
    }

    #[test]
    fn test_ptc_and_rulemonger_appoint_anywhere() {
        let target = ctx(vec![], Some("FR"));
        let ptc = ctx(vec![PTC], Some("US"));
        assert!(can_change_role(&ptc, &target, PT).allowed);
        assert!(!can_change_role(&ptc, &target, Prince).allowed);
        assert!(!can_change_role(&ptc, &target, Judge).allowed);

        let rm = ctx(vec![Rulemonger], Some("US"));
        assert!(can_change_role(&rm, &target, Judge).allowed);
        assert!(can_change_role(&rm, &target, Judgekin).allowed);
        assert!(!can_change_role(&rm, &target, Prince).allowed);
        assert!(!can_change_role(&rm, &target, PT).allowed);
    }

    #[test]
    fn test_target_needs_vekn_id_for_roles() {
        let ic = ctx(vec![IC], Some("US"));
        let target = UserContext {
            roles: vec![],
            country: Some("FR".to_string()),
            vekn_id: None,
        };
        let result = can_change_role(&ic, &target, Prince);
        assert!(!result.allowed);
        assert!(result.reason.unwrap().contains("VEKN ID"));
    }

    #[test]
    fn test_can_change_country() {
        let ic = ctx(vec![IC], Some("US"));
        let nc_fr = ctx(vec![NC], Some("FR"));
        let plain = ctx(vec![], Some("FR"));
        let prince_fr = ctx(vec![Prince], Some("FR"));
        let nc_target = ctx(vec![NC], Some("FR"));

        // A non-official target is unrestricted at this gate.
        assert!(can_change_country(&plain, &plain).allowed);
        // An official target takes the authority over their highest role.
        assert!(can_change_country(&ic, &nc_target).allowed);
        assert!(!can_change_country(&nc_fr, &nc_target).allowed);
        // NC may move a Prince of their own country, not another's.
        assert!(can_change_country(&nc_fr, &prince_fr).allowed);
        assert!(!can_change_country(&nc_fr, &ctx(vec![Prince], Some("US"))).allowed);
        // Highest role wins: an NC+Prince target needs NC-level authority.
        assert!(!can_change_country(&nc_fr, &ctx(vec![NC, Prince], Some("FR"))).allowed);
    }

    // ---- Tournaments & leagues -------------------------------------------

    #[test]
    fn test_create_tournament() {
        for role in OFFICIAL_ROLES {
            assert!(over_country(
                Capability::CreateTournament,
                &ctx(vec![role], Some("FR")),
                None
            ));
        }
        assert!(!over_country(
            Capability::CreateTournament,
            &ctx(vec![], Some("FR")),
            None
        ));
    }

    #[test]
    fn test_manage_leagues_excludes_prince() {
        let cap = Capability::ManageLeagues;
        assert!(over_country(cap, &ctx(vec![IC], Some("US")), None));
        assert!(over_country(cap, &ctx(vec![NC], Some("FR")), None));
        assert!(!over_country(cap, &ctx(vec![Prince], Some("FR")), None));
        assert!(!over_country(cap, &ctx(vec![], Some("FR")), None));
    }

    #[test]
    fn test_is_organizer() {
        let tournament = OwnedResource {
            country: Some("FR".to_string()),
            organizers_uids: vec!["org-1".to_string()],
            ..Default::default()
        };
        assert!(is_organizer(&ctx(vec![], Some("US")), "org-1", &tournament));
        assert!(is_organizer(&ctx(vec![IC], Some("US")), "x", &tournament));
        assert!(is_organizer(&ctx(vec![NC], Some("FR")), "x", &tournament));
        assert!(!is_organizer(&ctx(vec![NC], Some("US")), "x", &tournament));
        // Prince is NOT an implicit organizer
        assert!(!is_organizer(
            &ctx(vec![Prince], Some("FR")),
            "x",
            &tournament
        ));
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
            ..Default::default()
        };
        assert!(can_edit_league(&ctx(vec![IC], Some("US")), "x", &league).allowed);
        assert!(can_edit_league(&ctx(vec![NC], Some("FR")), "x", &league).allowed);
        assert!(!can_edit_league(&ctx(vec![NC], Some("US")), "x", &league).allowed);
        assert!(can_edit_league(&ctx(vec![], Some("US")), "org-1", &league).allowed);
        assert!(!can_edit_league(&ctx(vec![Prince], Some("FR")), "x", &league).allowed);
        assert!(!can_edit_league(&ctx(vec![], Some("FR")), "nobody", &league).allowed);
    }

    #[test]
    fn test_can_link_tournament_to_league() {
        let league = |country: Option<&str>, open: bool| OwnedResource {
            country: country.map(|s| s.to_string()),
            organizers_uids: vec!["org-1".to_string()],
            open_to_country_princes: open,
        };
        // League editors (IC/NC-same-country/organizer) can always link
        assert!(
            can_link_tournament_to_league(
                &ctx(vec![IC], Some("US")),
                "x",
                &league(Some("FR"), false)
            )
            .allowed
        );
        assert!(
            can_link_tournament_to_league(&ctx(vec![], None), "org-1", &league(Some("FR"), false))
                .allowed
        );
        // Prince same-country: only with the flag
        assert!(
            can_link_tournament_to_league(
                &ctx(vec![Prince], Some("FR")),
                "x",
                &league(Some("FR"), true)
            )
            .allowed
        );
        assert!(
            !can_link_tournament_to_league(
                &ctx(vec![Prince], Some("FR")),
                "x",
                &league(Some("FR"), false)
            )
            .allowed
        );
        // Prince other-country: never
        assert!(
            !can_link_tournament_to_league(
                &ctx(vec![Prince], Some("US")),
                "x",
                &league(Some("FR"), true)
            )
            .allowed
        );
        // Worldwide league (no country): the flag is inert
        assert!(
            !can_link_tournament_to_league(
                &ctx(vec![Prince], Some("FR")),
                "x",
                &league(None, true)
            )
            .allowed
        );
        // The flag never grants edit rights
        assert!(
            !can_edit_league(
                &ctx(vec![Prince], Some("FR")),
                "x",
                &league(Some("FR"), true)
            )
            .allowed
        );
    }

    // ---- Community links --------------------------------------------------

    #[test]
    fn test_link_moderation_scopes() {
        assert!(over_country(
            Capability::ModerateLink,
            &ctx(vec![NC], Some("FR")),
            Some("FR")
        ));
        assert!(!over_country(
            Capability::ModerateLink,
            &ctx(vec![NC], Some("US")),
            Some("FR")
        ));
        // Princes do not moderate links at all.
        assert!(!over_country(
            Capability::ModerateLink,
            &ctx(vec![Prince], Some("FR")),
            Some("FR")
        ));
        // Promotion narrows as it widens in reach: national is NC, global is IC.
        assert!(over_country(
            Capability::PromoteLinkNational,
            &ctx(vec![NC], Some("FR")),
            Some("FR")
        ));
        assert!(!over_country(
            Capability::PromoteLinkNational,
            &ctx(vec![Prince], Some("FR")),
            Some("FR")
        ));
        assert!(!over_country(
            Capability::PromoteLinkGlobal,
            &ctx(vec![NC], Some("FR")),
            Some("FR")
        ));
    }

    #[test]
    fn test_officials_moderate_their_own_links() {
        // Officials pin their own links through the ordinary grant, not a
        // self-service exemption — so an unprivileged member gets no such reach.
        let nc = ctx(vec![NC], Some("FR"));
        let member = ctx(vec![], Some("FR"));
        let own = |actor| {
            allows(
                Capability::ModerateLink,
                &Request::new(actor, "me")
                    .target_uid("me")
                    .target_country(Some("FR")),
            )
        };
        assert!(own(&nc));
        assert!(!own(&member));
    }

    // ---- Sanctions --------------------------------------------------------

    #[test]
    fn test_can_issue_sanction() {
        let no_t = OwnedResource::default();
        let t = OwnedResource {
            organizers_uids: vec!["org-1".to_string()],
            ..Default::default()
        };
        assert!(can_issue_sanction(&ctx(vec![IC], None), "x", "suspension", &no_t).allowed);
        assert!(can_issue_sanction(&ctx(vec![Ethics], None), "x", "probation", &no_t).allowed);
        assert!(!can_issue_sanction(&ctx(vec![NC], None), "x", "suspension", &no_t).allowed);
        // Organizer cannot issue a suspension
        assert!(!can_issue_sanction(&ctx(vec![], None), "org-1", "suspension", &t).allowed);
        // Tournament-level: IC/Ethics or an organizer
        assert!(can_issue_sanction(&ctx(vec![IC], None), "x", "caution", &no_t).allowed);
        assert!(can_issue_sanction(&ctx(vec![], None), "org-1", "warning", &t).allowed);
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
        assert!(lift(vec![IC], None, "x", "suspension", None, vec![]));
        assert!(lift(vec![Ethics], None, "x", "probation", None, vec![]));
        assert!(!lift(
            vec![Rulemonger],
            None,
            "x",
            "suspension",
            None,
            vec![]
        ));
        // Tournament-level: IC or Rulemonger always
        assert!(lift(vec![Rulemonger], None, "x", "caution", None, vec![]));
        // NC of the tournament's country
        assert!(lift(
            vec![NC],
            Some("FR"),
            "x",
            "warning",
            Some("FR".to_string()),
            vec![]
        ));
        assert!(!lift(
            vec![NC],
            Some("US"),
            "x",
            "warning",
            Some("FR".to_string()),
            vec![]
        ));
        // League organizer can lift a DQ, but nothing else
        assert!(lift(
            vec![],
            None,
            "org-1",
            "disqualification",
            None,
            vec!["org-1"]
        ));
        assert!(!lift(vec![], None, "org-1", "warning", None, vec!["org-1"]));
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
        assert!(del(vec![IC], "x", "suspension", "", vec![]));
        assert!(del(vec![Ethics], "x", "warning", "Finished", vec![]));
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
        assert!(!del(vec![NC], "x", "caution", "Playing", vec!["org-1"]));
    }

    // ---- Admin ------------------------------------------------------------

    #[test]
    fn test_admin_capabilities() {
        let cap_holders = [
            (Capability::ForceUnlockTournament, vec![IC]),
            (Capability::ManagePromos, vec![IC]),
            (Capability::RecordPromoIntake, vec![IC, NC]),
            (Capability::ViewFullPromoLedger, vec![IC, NC]),
            (Capability::ManageOauthClients, vec![IC, DEV]),
            (Capability::RunAdminSync, vec![IC]),
            (Capability::MergeAccounts, vec![IC]),
            (Capability::ModifySanction, vec![IC, Ethics]),
        ];
        for (cap, holders) in cap_holders {
            for role in &holders {
                assert!(
                    over_country(cap, &ctx(vec![*role], Some("US")), Some("FR")),
                    "{} should hold {}",
                    role.as_str(),
                    rule_for(cap).name
                );
            }
            for role in Role::ALL {
                if holders.contains(&role) || rule_for(cap).same_country.contains(&role) {
                    continue;
                }
                assert!(
                    !over_country(cap, &ctx(vec![role], Some("US")), Some("FR")),
                    "{} should not hold {}",
                    role.as_str(),
                    rule_for(cap).name
                );
            }
        }
    }
}
