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
    pub fn from_json(value: &JsonValue) -> Result<Self, String> {
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

/// Check if actor can manage VEKN IDs for target user (sponsor, link, force-abandon, merge).
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
}
