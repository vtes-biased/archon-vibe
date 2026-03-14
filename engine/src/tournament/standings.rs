//! Standings computation and management.

use json::JsonValue;

use super::sanctions::get_sa_sanctions;

/// Player standing: (user_uid, gw, vp, tp, toss, finalist)
pub(super) struct Standing {
    pub user_uid: String,
    pub gw: f64,
    pub vp: f64,
    pub tp: f64,
    pub toss: u32,
    pub finalist: bool,
}

/// Compute standings from all rounds. Sorted by GW desc, VP desc, TP desc, toss desc.
/// Applies SA overflow: if a player has an SA sanction for a round where their raw VP < 1.0,
/// the overflow (1.0 - raw_vp) is subtracted from their total VP.
pub(super) fn compute_standings(tournament: &JsonValue, sanctions: &JsonValue) -> Vec<Standing> {
    let mut map: std::collections::HashMap<String, (f64, f64, f64)> =
        std::collections::HashMap::new();

    // Sum results across all rounds
    for round in tournament["rounds"].members() {
        for table in round.members() {
            for seat in table["seating"].members() {
                let uid = seat["player_uid"].as_str().unwrap_or("").to_string();
                if uid.is_empty() {
                    continue;
                }
                let entry = map.entry(uid).or_insert((0.0, 0.0, 0.0));
                entry.0 += seat["result"]["gw"].as_f64().unwrap_or(0.0);
                entry.1 += seat["result"]["vp"].as_f64().unwrap_or(0.0);
                entry.2 += seat["result"]["tp"].as_f64().unwrap_or(0.0);
            }
        }
    }

    // Apply SA overflow: for each SA sanction, if the player's raw VP in that round < 1.0,
    // subtract the overflow from total VP
    let sa_sanctions = get_sa_sanctions(sanctions);
    for (sa_uid, sa_round) in &sa_sanctions {
        if *sa_round >= tournament["rounds"].len() {
            continue;
        }
        // Find the player's raw VP in that round
        let mut round_vp = 0.0;
        for table in tournament["rounds"][*sa_round].members() {
            for seat in table["seating"].members() {
                if seat["player_uid"].as_str() == Some(sa_uid.as_str()) {
                    round_vp = seat["result"]["vp"].as_f64().unwrap_or(0.0);
                }
            }
        }
        if round_vp < 1.0 {
            if let Some(entry) = map.get_mut(sa_uid) {
                entry.1 -= 1.0 - round_vp; // subtract overflow
            }
        }
    }

    // Build standings with toss and finalist from player records
    let mut standings: Vec<Standing> = map
        .into_iter()
        .map(|(uid, (gw, vp, tp))| {
            let player = tournament["players"]
                .members()
                .find(|p| p["user_uid"].as_str() == Some(&uid));
            let toss = player.and_then(|p| p["toss"].as_u32()).unwrap_or(0);
            let finalist = player
                .and_then(|p| p["finalist"].as_bool())
                .unwrap_or(false);
            Standing {
                user_uid: uid,
                gw,
                vp,
                tp,
                toss,
                finalist,
            }
        })
        .collect();

    standings.sort_by(|a, b| {
        b.gw.partial_cmp(&a.gw)
            .unwrap()
            .then(b.vp.partial_cmp(&a.vp).unwrap())
            .then(b.tp.partial_cmp(&a.tp).unwrap())
            .then(b.toss.cmp(&a.toss))
    });

    standings
}

/// Compute standings and store them on the tournament JSON object.
/// Guard: does NOT overwrite standings if rounds are empty (preserves VEKN-synced data).
pub(super) fn update_standings(tournament: &mut JsonValue, sanctions: &JsonValue) {
    if tournament["rounds"].is_empty() {
        return;
    }
    let standings = compute_standings(tournament, sanctions);
    let arr: Vec<JsonValue> = standings
        .into_iter()
        .map(|s| {
            json::object! {
                "user_uid" => s.user_uid,
                "gw" => s.gw,
                "vp" => s.vp,
                "tp" => s.tp,
                "toss" => s.toss,
                "finalist" => s.finalist,
            }
        })
        .collect();
    tournament["standings"] = JsonValue::Array(arr);
}

/// Check if top 5 has unbroken ties (players at the cutoff boundary with same scores and no toss differentiation)
pub(super) fn top5_has_ties(standings: &[Standing]) -> bool {
    if standings.len() < 5 {
        return false;
    }
    // Check all pairs in top 5 for ties not broken by toss
    for i in 0..5 {
        for j in (i + 1)..5 {
            let a = &standings[i];
            let b = &standings[j];
            if a.gw == b.gw && a.vp == b.vp && a.tp == b.tp && a.toss == b.toss {
                return true;
            }
        }
    }
    // Also check if #5 ties with #6+
    if standings.len() > 5 {
        let fifth = &standings[4];
        for s in &standings[5..] {
            if s.gw == fifth.gw && s.vp == fifth.vp && s.tp == fifth.tp && s.toss == fifth.toss {
                return true;
            }
        }
    }
    false
}
