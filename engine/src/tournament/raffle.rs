//! Raffle pool computation and deck public flag logic.

use super::standings::compute_preliminary_standings;
use crate::error::EngineError;
use json::JsonValue;

/// Players eligible for a raffle: anyone seated in a round so far, plus anyone
/// currently present (state Checked-in or Playing) who hasn't been seated yet — so
/// a raffle held at check-in, before the first round exists, still draws from the
/// checked-in players (and a checked-in player sitting out a round stays raffleable).
/// Sorted for determinism.
fn get_raffle_base_uids(tournament: &JsonValue) -> Vec<String> {
    let mut base = std::collections::HashSet::new();
    for round in tournament["rounds"].members() {
        for table in round.members() {
            for seat in table["seating"].members() {
                if let Some(uid) = seat["player_uid"].as_str() {
                    if !uid.is_empty() {
                        base.insert(uid.to_string());
                    }
                }
            }
        }
    }
    for p in tournament["players"].members() {
        let s = p["state"].as_str();
        if s == Some("Checked-in") || s == Some("Playing") {
            if let Some(uid) = p["user_uid"].as_str() {
                if !uid.is_empty() {
                    base.insert(uid.to_string());
                }
            }
        }
    }
    let mut result: Vec<String> = base.into_iter().collect();
    result.sort();
    result
}

/// Filter raffle pool based on pool type and exclude_drawn flag.
/// NOTE: Pool filtering logic duplicated in frontend RaffleSection.svelte eligibleForPool()
pub(super) fn get_raffle_pool(
    tournament: &JsonValue,
    sanctions: &JsonValue,
    pool: &str,
    exclude_drawn: bool,
) -> Result<Vec<String>, EngineError> {
    let base = get_raffle_base_uids(tournament);
    if base.is_empty() {
        return Err(EngineError::RaffleNonePlayed);
    }

    // Build standings map: uid -> (gw, vp). Computed live from round results —
    // the stored tournament["standings"] only refreshes on FinishRound and would
    // miss GW/VP earned in the round in progress (scored via SetScore).
    let standings_map: std::collections::HashMap<String, (f64, f64)> =
        compute_preliminary_standings(tournament, sanctions)
            .into_iter()
            .map(|s| (s.user_uid, (s.gw, s.vp)))
            .collect();

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
        "AllPlayers" => base.clone(),
        "NonFinalists" => base
            .iter()
            .filter(|uid| !finalists.contains(*uid))
            .cloned()
            .collect(),
        "GameWinners" => base
            .iter()
            .filter(|uid| standings_map.get(*uid).is_some_and(|(gw, _)| *gw > 0.0))
            .cloned()
            .collect(),
        "NoGameWin" => base
            .iter()
            .filter(|uid| standings_map.get(*uid).is_none_or(|(gw, _)| *gw == 0.0))
            .cloned()
            .collect(),
        "NoVictoryPoint" => base
            .iter()
            .filter(|uid| standings_map.get(*uid).is_none_or(|(_, vp)| *vp == 0.0))
            .cloned()
            .collect(),
        _ => return Err(EngineError::internal(format!("Unknown pool: {}", pool))),
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
