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

/// Resolve each active SA to the round its `-1` VP actually lands on, per JG v2
/// §1.1.3: the player's current game if one is in progress, else their most
/// recently played game — never a future round. The stored `round_number` is the
/// fixed issue-time record of the game the judge ruled on; we honor it when the
/// player was seated in a non-cancelled table of that round, otherwise we redirect
/// to the player's most-recently-*seated* round (highest round index with a
/// non-cancelled seat). An SA whose player was never seated in a non-cancelled
/// round contributes nothing and is dropped (a player who has yet to play — or
/// whose only game was soft-cancelled — has no game to penalize).
///
/// One entry per active SA — two SAs on one player stack to `-2`; do not dedup.
/// This is the SINGLE source both consumers read (`table_sa_adjustments` for the
/// per-table GW/TP cascade and `sa_vp_penalty` for the VP total), so they always
/// agree on the effective round. Finals is never scanned, so SA never lands there.
pub(super) fn resolve_sa_effective_rounds(
    tournament: &JsonValue,
    sanctions: &JsonValue,
) -> Vec<(String, usize)> {
    let rounds = &tournament["rounds"];
    let nrounds = rounds.len();
    // A soft-cancelled table is not a played game, so a seat there can't anchor an
    // SA — both the honor-stored check and the redirect fallback skip Cancelled
    // tables, keeping the effective round one the GW/TP cascade actually visits
    // (standings skips Cancelled tables) so VP and GW/TP land on the same round.
    let seated_in = |uid: &str, r: usize| -> bool {
        rounds[r].members().any(|table| {
            table["state"].as_str() != Some("Cancelled")
                && table["seating"]
                    .members()
                    .any(|s| s["player_uid"].as_str() == Some(uid))
        })
    };
    let mut out = Vec::new();
    for (uid, stored) in get_sa_sanctions(sanctions) {
        let effective = if stored < nrounds && seated_in(&uid, stored) {
            Some(stored)
        } else {
            (0..nrounds).rev().find(|&r| seated_in(&uid, r))
        };
        if let Some(r) = effective {
            out.push((uid, r));
        }
    }
    out
}

/// Per-seat SA VP adjustments for a `seating` array in round `round_index`:
/// `-1.0` for each resolved SA whose effective round is `round_index` (see
/// [`resolve_sa_effective_rounds`]). Length matches `seating`. Shared by
/// score-time scoring (SetScore) and the standings/rating recompute, so every
/// path applies SA to GW/TP identically.
pub(super) fn table_sa_adjustments(
    seating: &JsonValue,
    round_index: usize,
    effective_sas: &[(String, usize)],
) -> Vec<f64> {
    seating
        .members()
        .map(|seat| {
            let uid = seat["player_uid"].as_str().unwrap_or("");
            let count = effective_sas
                .iter()
                .filter(|(sa_uid, sa_round)| sa_uid == uid && *sa_round == round_index)
                .count();
            -(count as f64)
        })
        .collect()
}

/// VP penalty magnitude for `user_uid`: a full 1.0 per resolved SA (JG v2 §1.1.3).
/// Every entry in `effective_sas` already landed on a real played round, so there
/// is no deferral here. Callers subtract this from the player's VP total, which
/// may go negative. Shares [`resolve_sa_effective_rounds`] with the GW/TP cascade.
pub(super) fn sa_vp_penalty(effective_sas: &[(String, usize)], user_uid: &str) -> f64 {
    effective_sas
        .iter()
        .filter(|(uid, _)| uid == user_uid)
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
