use json::JsonValue;

pub(super) fn is_sanction_active(s: &JsonValue) -> bool {
    s["lifted_at"].is_null() && s["deleted_at"].is_null()
}

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

/// Resolves each active SA to the round its `-1` VP lands on (JG v2 §1.1.3):
/// the stored `round_number` if the player was seated there, else the
/// most-recently-seated round (finals = sentinel `nrounds`). Stacks; never dedup.
pub(super) fn resolve_sa_effective_rounds(
    tournament: &JsonValue,
    sanctions: &JsonValue,
) -> Vec<(String, usize)> {
    let rounds = &tournament["rounds"];
    let nrounds = rounds.len();
    // An SA anchors only on a table the standings score, so the -1 VP and the GW/TP
    // cascade land on the same round. Finals never lingers cancelled — CancelFinals
    // nulls `finals` wholesale — so presence in seating is enough.
    let seated_in = |uid: &str, r: usize| -> bool {
        if r == nrounds {
            return tournament["finals"]["seating"]
                .members()
                .any(|s| s["player_uid"].as_str() == Some(uid));
        }
        rounds[r].members().any(|table| {
            table["state"].as_str() == Some("Finished")
                && table["seating"]
                    .members()
                    .any(|s| s["player_uid"].as_str() == Some(uid))
        })
    };
    let mut out = Vec::new();
    for (uid, stored) in get_sa_sanctions(sanctions) {
        let effective = if stored <= nrounds && seated_in(&uid, stored) {
            Some(stored)
        } else {
            (0..=nrounds).rev().find(|&r| seated_in(&uid, r))
        };
        if let Some(r) = effective {
            out.push((uid, r));
        }
    }
    out
}

/// -1.0 per resolved SA whose effective round is `round_index`. Length matches
/// `seating`. Shared by SetScore and the standings/rating recompute, so every
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

/// 1.0 per resolved SA (JG v2 §1.1.3); callers subtract this from the VP total,
/// which may go negative. Shares effective rounds with the GW/TP cascade.
pub(super) fn sa_vp_penalty(effective_sas: &[(String, usize)], user_uid: &str) -> f64 {
    effective_sas
        .iter()
        .filter(|(uid, _)| uid == user_uid)
        .count() as f64
}

pub(super) fn has_dq_sanction(sanctions: &JsonValue, player_uid: &str) -> bool {
    sanctions.members().any(|s| {
        is_sanction_active(s)
            && s["level"].as_str() == Some("disqualification")
            && s["user_uid"].as_str() == Some(player_uid)
    })
}

/// Active = not lifted/deleted, and no expiry or `expires_at` still in the
/// future. `now`/`expires_at` must be lexicographically comparable ISO-8601 UTC
/// strings (backend `+00:00`, frontend `…Z`); absent expiry or empty `now` keep it active.
pub(super) fn has_active_suspension(sanctions: &JsonValue, player_uid: &str, now: &str) -> bool {
    sanctions.members().any(|s| {
        is_sanction_active(s)
            && s["level"].as_str() == Some("suspension")
            && s["user_uid"].as_str() == Some(player_uid)
            && !suspension_expired(s, now)
    })
}

/// A suspension is expired when it carries an `expires_at` at or before `now`.
/// Absent expiry (permanent) or empty `now` (no clock) → not expired.
fn suspension_expired(s: &JsonValue, now: &str) -> bool {
    match s["expires_at"].as_str() {
        Some(exp) if !now.is_empty() => exp <= now,
        _ => false,
    }
}
