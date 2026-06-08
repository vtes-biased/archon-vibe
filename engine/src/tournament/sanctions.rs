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

/// Per-seat SA VP adjustments for a `seating` array in round `round_index`:
/// `-1.0` for each active standings_adjustment sanction targeting that seat's
/// player on that round. Length matches `seating`. Single source for the
/// per-table adjustment vector — shared by score-time scoring (SetScore) and the
/// standings/rating recompute, so every path applies SA to GW/TP identically.
pub(super) fn table_sa_adjustments(
    seating: &JsonValue,
    round_index: usize,
    sanctions: &JsonValue,
) -> Vec<f64> {
    let sa = get_sa_sanctions(sanctions);
    seating
        .members()
        .map(|seat| {
            let uid = seat["player_uid"].as_str().unwrap_or("");
            let count = sa
                .iter()
                .filter(|(sa_uid, sa_round)| sa_uid == uid && *sa_round == round_index)
                .count();
            -(count as f64)
        })
        .collect()
}

/// VP penalty magnitude for `user_uid` from active SA sanctions on already-played
/// rounds: a full 1.0 per applicable sanction (JG v2 1.1.3). An SA targeting a
/// not-yet-played round (index >= `rounds_len`) is deferred and contributes 0.
/// Callers subtract this from the player's VP total, which may go negative.
/// Single source for the SA-on-VP rule shared by standings and rating computation.
pub(super) fn sa_vp_penalty(sanctions: &JsonValue, user_uid: &str, rounds_len: usize) -> f64 {
    get_sa_sanctions(sanctions)
        .into_iter()
        .filter(|(uid, round)| uid == user_uid && *round < rounds_len)
        .count() as f64
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
