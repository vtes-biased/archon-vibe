//! Sanctions helper functions.

use json::JsonValue;

/// Check if a sanction is active (not lifted, not deleted).
pub(super) fn is_sanction_active(s: &JsonValue) -> bool {
    s["lifted_at"].is_null() && s["deleted_at"].is_null()
}

/// Get active SA (standings_adjustment) sanctions: returns (user_uid, round_number) pairs.
pub(super) fn get_sa_sanctions(sanctions: &JsonValue) -> Vec<(String, usize)> {
    let mut result = Vec::new();
    for s in sanctions.members() {
        if !is_sanction_active(s) {
            continue;
        }
        if s["level"].as_str() != Some("standings_adjustment") {
            continue;
        }
        let uid = s["user_uid"].as_str().unwrap_or("").to_string();
        let round = s["round_number"].as_usize().unwrap_or(0);
        if !uid.is_empty() {
            result.push((uid, round));
        }
    }
    result
}

/// Check if a player has an active DQ sanction (in-tournament).
pub(super) fn has_dq_sanction(sanctions: &JsonValue, player_uid: &str) -> bool {
    sanctions.members().any(|s| {
        is_sanction_active(s)
            && s["level"].as_str() == Some("disqualification")
            && s["user_uid"].as_str() == Some(player_uid)
    })
}

/// Check if a player has an active suspension.
pub(super) fn has_active_suspension(sanctions: &JsonValue, player_uid: &str) -> bool {
    sanctions.members().any(|s| {
        is_sanction_active(s)
            && s["level"].as_str() == Some("suspension")
            && s["user_uid"].as_str() == Some(player_uid)
    })
}
