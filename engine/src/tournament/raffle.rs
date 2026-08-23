//! Raffle pool computation and deck public flag logic.

use super::standings::compute_preliminary_standings;
use crate::error::EngineError;
use crate::model::{finals_table, player, raffle_draw, seat, table, tournament};
use json::JsonValue;

/// Raffle-eligible: seated so far, plus checked-in/playing players not yet seated —
/// so a pre-round-1 raffle still draws from check-in. Sorted for determinism.
fn get_raffle_base_uids(tournament: &JsonValue) -> Vec<String> {
    let mut base = std::collections::HashSet::new();
    for round in tournament[tournament::ROUNDS].members() {
        for table in round.members() {
            for seat in table[table::SEATING].members() {
                if let Some(uid) = seat[seat::PLAYER_UID].as_str() {
                    if !uid.is_empty() {
                        base.insert(uid.to_string());
                    }
                }
            }
        }
    }
    for p in tournament[tournament::PLAYERS].members() {
        let s = p[player::STATE].as_str();
        if s == Some("Checked-in") || s == Some("Playing") {
            if let Some(uid) = p[player::USER_UID].as_str() {
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

pub fn get_raffle_pool(
    tournament: &JsonValue,
    sanctions: &JsonValue,
    pool: &str,
    exclude_drawn: bool,
) -> Result<Vec<String>, EngineError> {
    let base = get_raffle_base_uids(tournament);

    // Computed live, not from tournament["standings"]: that only refreshes on
    // FinishRound and would miss VP/GW from an in-progress round's SetScore.
    let standings_map: std::collections::HashMap<String, (f64, f64)> =
        compute_preliminary_standings(tournament, sanctions)
            .into_iter()
            .map(|s| (s.user_uid, (s.gw, s.vp)))
            .collect();

    let finalists: std::collections::HashSet<String> = if !tournament[tournament::FINALS].is_null()
    {
        tournament[tournament::FINALS][finals_table::SEATING]
            .members()
            .filter_map(|s| s[seat::PLAYER_UID].as_str().map(|u| u.to_string()))
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
        let drawn: std::collections::HashSet<String> = tournament[tournament::RAFFLES]
            .members()
            .flat_map(|d| d[raffle_draw::WINNERS].members())
            .filter_map(|w| w.as_str().map(|s| s.to_string()))
            .collect();
        eligible.retain(|uid| !drawn.contains(uid));
    }

    Ok(eligible)
}

pub(super) fn compute_deck_public(tournament: &JsonValue, player_uid: &str) -> bool {
    let state = tournament[tournament::STATE].as_str().unwrap_or("");
    if state != "Finished" {
        return false;
    }
    let mode = tournament[tournament::DECKLISTS_MODE]
        .as_str()
        .unwrap_or("Winner");
    match mode {
        "All" => true,
        "Finalists" => {
            tournament[tournament::WINNER].as_str() == Some(player_uid)
                || tournament[tournament::PLAYERS].members().any(|p| {
                    p[player::USER_UID].as_str() == Some(player_uid)
                        && p[player::FINALIST].as_bool().unwrap_or(false)
                })
        }
        _ => tournament[tournament::WINNER].as_str() == Some(player_uid),
    }
}
