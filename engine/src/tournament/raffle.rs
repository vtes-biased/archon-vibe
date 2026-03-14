//! Raffle pool computation and deck public flag logic.

use json::JsonValue;

/// Get the set of player UIDs who appeared in any round seating (sorted for determinism).
fn get_played_uids(tournament: &JsonValue) -> Vec<String> {
    let mut played = std::collections::HashSet::new();
    for round in tournament["rounds"].members() {
        for table in round.members() {
            for seat in table["seating"].members() {
                if let Some(uid) = seat["player_uid"].as_str() {
                    if !uid.is_empty() {
                        played.insert(uid.to_string());
                    }
                }
            }
        }
    }
    let mut result: Vec<String> = played.into_iter().collect();
    result.sort();
    result
}

/// Filter raffle pool based on pool type and exclude_drawn flag.
/// NOTE: Pool filtering logic duplicated in frontend RaffleSection.svelte eligibleForPool()
pub(super) fn get_raffle_pool(
    tournament: &JsonValue,
    pool: &str,
    exclude_drawn: bool,
) -> Result<Vec<String>, String> {
    let played = get_played_uids(tournament);
    if played.is_empty() {
        return Err("No players have played yet".to_string());
    }

    // Build standings map: uid -> (gw, vp)
    let mut standings_map: std::collections::HashMap<String, (f64, f64)> =
        std::collections::HashMap::new();
    for s in tournament["standings"].members() {
        if let Some(uid) = s["user_uid"].as_str() {
            let gw = s["gw"].as_f64().unwrap_or(0.0);
            let vp = s["vp"].as_f64().unwrap_or(0.0);
            standings_map.insert(uid.to_string(), (gw, vp));
        }
    }

    // Finalists set
    let finalists: std::collections::HashSet<String> = if !tournament["finals"].is_null() {
        tournament["finals"]["seating"]
            .members()
            .filter_map(|s| s["player_uid"].as_str().map(|u| u.to_string()))
            .collect()
    } else {
        std::collections::HashSet::new()
    };

    let mut eligible: Vec<String> = match pool {
        "AllPlayers" => played.clone(),
        "NonFinalists" => played
            .iter()
            .filter(|uid| !finalists.contains(*uid))
            .cloned()
            .collect(),
        "GameWinners" => played
            .iter()
            .filter(|uid| standings_map.get(*uid).is_some_and(|(gw, _)| *gw > 0.0))
            .cloned()
            .collect(),
        "NoGameWin" => played
            .iter()
            .filter(|uid| standings_map.get(*uid).is_none_or(|(gw, _)| *gw == 0.0))
            .cloned()
            .collect(),
        "NoVictoryPoint" => played
            .iter()
            .filter(|uid| standings_map.get(*uid).is_none_or(|(_, vp)| *vp == 0.0))
            .cloned()
            .collect(),
        _ => return Err(format!("Unknown pool: {}", pool)),
    };

    if exclude_drawn {
        let drawn: std::collections::HashSet<String> = tournament["raffles"]
            .members()
            .flat_map(|d| d["winners"].members())
            .filter_map(|w| w.as_str().map(|s| s.to_string()))
            .collect();
        eligible.retain(|uid| !drawn.contains(uid));
    }

    Ok(eligible)
}

/// Compute whether a deck should be public based on tournament state and decklists_mode.
pub(super) fn compute_deck_public(tournament: &JsonValue, player_uid: &str) -> bool {
    let state = tournament["state"].as_str().unwrap_or("");
    if state != "Finished" {
        return false;
    }
    let mode = tournament["decklists_mode"].as_str().unwrap_or("Winner");
    match mode {
        "All" => true,
        "Finalists" => {
            // Check if player is a finalist or winner
            tournament["winner"].as_str() == Some(player_uid)
                || tournament["players"].members().any(|p| {
                    p["user_uid"].as_str() == Some(player_uid)
                        && p["finalist"].as_bool().unwrap_or(false)
                })
        }
        _ => tournament["winner"].as_str() == Some(player_uid),
    }
}
