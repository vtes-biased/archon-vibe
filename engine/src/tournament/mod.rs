//! Tournament business logic engine.
//!
//! Processes tournament events and returns updated tournament state.
//! Same code runs in WASM (frontend offline) and PyO3 (backend).

use json::JsonValue;

use crate::seating;

mod helpers;
mod parsing;
mod raffle;
mod sanctions;
mod scoring;
mod standings;
#[cfg(test)]
mod tests;
mod types;

// Re-export items used by lib.rs
pub use scoring::{check_table_vps, compute_gw, compute_tp};
pub use standings::{compute_final_standings, compute_rating_vp_gw};
pub use types::{
    ActorContext, PlayerState, SeatScore, TableState, TournamentEvent, TournamentState,
};

// Used within the module
use types::VpError;

// Import everything needed for apply_event from submodules
use crate::error::EngineError;
use helpers::{
    all_rounds_finished, count_player_rounds_played, find_player_index, is_deck_locked,
    player_exists, players_in_other_active_rounds, require_can_edit_results, require_organizer,
    require_state, require_state_or_finished, validate_enum,
};
use raffle::{compute_deck_public, get_raffle_pool};
use sanctions::{has_active_suspension, has_dq_sanction, table_sa_adjustments};
use scoring::compute_gw_finals;
use standings::{compute_preliminary_standings, top5_has_ties, update_standings};

// ============================================================================
// TOURNAMENT ENGINE
// ============================================================================

/// Validate config fields shared between UpdateConfig and CreateTournament.
fn validate_config_fields(config: &JsonValue) -> Result<(), EngineError> {
    if let Some(f) = config["format"].as_str() {
        validate_enum(f, &["Standard", "V5", "Limited"], "format")?;
    }
    if let Some(r) = config["rank"].as_str() {
        validate_enum(
            r,
            &["", "National Championship", "Continental Championship"],
            "rank",
        )?;
    }
    if let Some(s) = config["standings_mode"].as_str() {
        validate_enum(
            s,
            &["Private", "Cutoff", "Top 10", "Public"],
            "standings_mode",
        )?;
    }
    if let Some(d) = config["decklists_mode"].as_str() {
        validate_enum(d, &["Winner", "Finalists", "All"], "decklists_mode")?;
    }
    if config.has_key("name") {
        if let Some(n) = config["name"].as_str() {
            if n.trim().is_empty() {
                return Err(EngineError::NameRequired);
            }
        }
    }
    Ok(())
}

/// Create a new tournament from config and actor context.
/// Returns the tournament JSON string.
pub fn create_tournament(config_json: &str, actor_json: &str) -> Result<String, EngineError> {
    let config = json::parse(config_json)?;
    let actor = ActorContext::from_json(&json::parse(actor_json)?)?;

    if !actor.can_manage_tournaments() {
        return Err(EngineError::CreateForbidden);
    }

    validate_config_fields(&config)?;

    // Name is required for creation
    let name = config["name"].as_str().ok_or("name is required")?;
    if name.trim().is_empty() {
        return Err(EngineError::NameRequired);
    }

    let uid = config["uid"].as_str().unwrap_or("").to_string();
    let now = config["now"].as_str().unwrap_or("").to_string();

    let tournament = json::object! {
        "uid" => if uid.is_empty() { json::JsonValue::Null } else { uid.into() },
        "modified" => if now.is_empty() { json::JsonValue::Null } else { now.clone().into() },
        "name" => name,
        "format" => config["format"].as_str().unwrap_or("Standard"),
        "rank" => config["rank"].as_str().unwrap_or(""),
        "online" => config["online"].as_bool().unwrap_or(false),
        "start" => config["start"].clone(),
        "finish" => config["finish"].clone(),
        "timezone" => config["timezone"].as_str().unwrap_or(""),
        "country" => config["country"].clone(),
        "state" => "Planned",
        "organizers_uids" => json::array![actor.uid.clone()],
        "venue" => config["venue"].as_str().unwrap_or(""),
        "venue_url" => config["venue_url"].as_str().unwrap_or(""),
        "address" => config["address"].as_str().unwrap_or(""),
        "map_url" => config["map_url"].as_str().unwrap_or(""),
        "proxies" => config["proxies"].as_bool().unwrap_or(false),
        "multideck" => config["multideck"].as_bool().unwrap_or(false),
        "decklist_required" => config["decklist_required"].as_bool().unwrap_or(false),
        "description" => config["description"].as_str().unwrap_or(""),
        "standings_mode" => config["standings_mode"].as_str().unwrap_or("Private"),
        "decklists_mode" => config["decklists_mode"].as_str().unwrap_or("Winner"),
        "max_rounds" => config["max_rounds"].as_u32().unwrap_or(0),
        "league_uid" => config["league_uid"].clone(),
        "round_time" => config["round_time"].as_u32().unwrap_or(0),
        "finals_time" => config["finals_time"].as_u32().unwrap_or(0),
        "players" => json::array![],
        "rounds" => json::array![],
        "finals" => json::JsonValue::Null,
        "winner" => "",
        "standings" => json::array![],
    };

    Ok(tournament.dump())
}

/// Process a tournament event and return updated tournament + deck side-effects.
///
/// # Arguments
/// * `tournament_json` - Current tournament state as JSON
/// * `event_json` - Event to process
/// * `actor_json` - Actor performing the action
/// * `sanctions_json` - Array of sanctions: [{user_uid, level, round_number, lifted_at, deleted_at}]
/// * `decks_json` - Array of existing deck metadata: [{user_uid, round, uid}]
///
/// # Returns
/// * JSON: `{"tournament": {...}, "deck_ops": [...]}`
/// * Error message on failure
pub fn process_tournament_event(
    tournament_json: &str,
    event_json: &str,
    actor_json: &str,
    sanctions_json: &str,
    decks_json: &str,
) -> Result<String, EngineError> {
    let mut tournament = json::parse(tournament_json)?;
    let event_value = json::parse(event_json)?;
    let actor_value = json::parse(actor_json)?;
    let sanctions = json::parse(sanctions_json)?;
    let decks = json::parse(decks_json)?;

    let event = TournamentEvent::from_json(&event_value)?;
    let actor = ActorContext::from_json(&actor_value)?;

    // Process the event
    let mut deck_ops = JsonValue::new_array();
    apply_event(
        &mut tournament,
        &event,
        &actor,
        &sanctions,
        &decks,
        &mut deck_ops,
    )?;

    let result = json::object! {
        "tournament" => tournament,
        "deck_ops" => deck_ops,
    };
    Ok(result.dump())
}

/// Recompute `standings` from the tournament's rounds + current `sanctions` and
/// return the updated tournament JSON.
///
/// Issuing, lifting, or deleting a standings_adjustment is NOT a `TournamentEvent`
/// (sanctions are their own object type), so those paths can't recompute standings
/// through `process_tournament_event`. This is the recompute they call instead —
/// the same `update_standings` that every event ends with — so the SA VP penalty
/// and per-table GW/TP refresh live, not only on the next tournament action.
/// No-op when rounds are empty (guarded in `update_standings` to preserve
/// VEKN-synced standings). Returns the bare tournament object (no `deck_ops`).
pub fn update_standings_json(
    tournament_json: &str,
    sanctions_json: &str,
) -> Result<String, EngineError> {
    let mut tournament = json::parse(tournament_json)?;
    let sanctions = json::parse(sanctions_json)?;
    update_standings(&mut tournament, &sanctions);
    Ok(tournament.dump())
}

fn apply_event(
    tournament: &mut JsonValue,
    event: &TournamentEvent,
    actor: &ActorContext,
    sanctions: &JsonValue,
    decks: &JsonValue,
    deck_ops: &mut JsonValue,
) -> Result<(), EngineError> {
    let state = TournamentState::from_str(tournament["state"].as_str().unwrap_or("Planned"))
        .ok_or("Invalid tournament state")?;

    match event {
        TournamentEvent::OpenRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Planned)?;
            tournament["state"] = "Registration".into();
            Ok(())
        }

        TournamentEvent::CloseRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Registration)?;
            tournament["state"] = "Waiting".into();
            Ok(())
        }

        TournamentEvent::CancelRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Registration)?;
            tournament["state"] = "Planned".into();
            Ok(())
        }

        TournamentEvent::ReopenRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Waiting)?;
            tournament["state"] = "Registration".into();
            // Reset Checked-in players back to Registered
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Checked-in") {
                    players[i]["state"] = "Registered".into();
                }
            }
            Ok(())
        }

        TournamentEvent::ReopenTournament => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Finished)?;
            tournament["state"] = "Waiting".into();
            // Clear finals and winner so organizer can redo finals. winner is "" (not
            // null): the backend Tournament model types it `str` (""=no winner), so a
            // null fails msgspec validation and 500s the action.
            tournament["finals"] = json::Null;
            tournament["winner"] = "".into();
            // Reset Finished players back to Checked-in (DQ'd stay DQ'd)
            // Also clear finalist flag so new finals can be started cleanly
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Finished") {
                    players[i]["state"] = "Checked-in".into();
                }
                players[i]["finalist"] = false.into();
                // Disqualified players stay Disqualified (no reset)
            }
            update_standings(tournament, sanctions);
            // Reset all deck public flags since tournament is no longer finished
            for d in decks.members() {
                let deck_uid = d["uid"].as_str().unwrap_or("");
                if !deck_uid.is_empty() {
                    let op = json::object! {
                        "op" => "set_public",
                        "deck_uid" => deck_uid,
                        "public" => false,
                    };
                    let _ = deck_ops.push(op);
                }
            }
            Ok(())
        }

        TournamentEvent::Register {
            user_uid,
            vekn_id,
            display_name,
        } => {
            require_state(state, TournamentState::Registration)?;

            // Require VEKN ID
            if vekn_id.as_ref().is_none_or(|v| v.is_empty()) {
                return Err(EngineError::VeknIdRequired);
            }

            // Check not already registered
            if player_exists(&tournament["players"], user_uid) {
                return Err(EngineError::AlreadyRegistered);
            }

            // Block players with DQ or suspension sanctions
            if has_dq_sanction(sanctions, user_uid) {
                return Err(EngineError::PlayerDisqualified);
            }
            if has_active_suspension(sanctions, user_uid) {
                return Err(EngineError::PlayerSuspended);
            }

            // Add player
            let mut player = json::object! {
                user_uid: user_uid.as_str(),
                state: "Registered",
                payment_status: "Pending",
                toss: 0,
                result: { gw: 0, vp: 0.0, tp: 0 },
                finalist: false,
            };
            if let Some(dn) = display_name {
                if !dn.is_empty() {
                    player["display_name"] = dn.as_str().into();
                }
            }
            tournament["players"].push(player)?;
            Ok(())
        }

        TournamentEvent::Unregister { user_uid } => {
            require_state(state, TournamentState::Registration)?;

            // Self-only: player can only unregister themselves
            if actor.uid != *user_uid {
                return Err(EngineError::UnregisterOnlySelf);
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, user_uid).ok_or(EngineError::PlayerNotFound)?;
            players.array_remove(idx);
            Ok(())
        }

        TournamentEvent::AddPlayer {
            user_uid,
            vekn_id,
            display_name,
        } => {
            require_organizer(actor)?;
            if state != TournamentState::Planned
                && state != TournamentState::Registration
                && state != TournamentState::Waiting
                && state != TournamentState::Playing
                && state != TournamentState::Finished
            {
                return Err(EngineError::CannotAddPlayers);
            }

            // Require VEKN ID
            if vekn_id.as_ref().is_none_or(|v| v.is_empty()) {
                return Err(EngineError::VeknIdRequired);
            }

            if player_exists(&tournament["players"], user_uid) {
                return Err(EngineError::AlreadyRegistered);
            }

            // Block players with DQ or suspension sanctions
            if has_dq_sanction(sanctions, user_uid) {
                return Err(EngineError::PlayerDisqualified);
            }
            if has_active_suspension(sanctions, user_uid) {
                return Err(EngineError::PlayerSuspended);
            }

            // Auto check-in when adding during Waiting state
            let auto_checkin = state == TournamentState::Waiting;
            let player_state = if auto_checkin {
                "Checked-in"
            } else {
                "Registered"
            };
            let mut player = json::object! {
                user_uid: user_uid.as_str(),
                state: player_state,
                payment_status: "Pending",
                toss: 0,
                result: { gw: 0, vp: 0.0, tp: 0 },
                finalist: false,
            };
            if let Some(dn) = display_name {
                if !dn.is_empty() {
                    player["display_name"] = dn.as_str().into();
                }
            }
            if auto_checkin
                && tournament["decklist_required"].as_bool().unwrap_or(false)
                && !decks
                    .members()
                    .any(|d| d["user_uid"].as_str() == Some(user_uid.as_str()))
            {
                player["missing_decklist"] = true.into();
            }
            tournament["players"].push(player)?;
            Ok(())
        }

        TournamentEvent::RemovePlayer { user_uid } => {
            require_organizer(actor)?;
            if state != TournamentState::Planned
                && state != TournamentState::Registration
                && state != TournamentState::Waiting
                && state != TournamentState::Finished
            {
                return Err(EngineError::CannotRemovePlayers);
            }
            if !tournament["rounds"].is_empty() {
                return Err(EngineError::UseDropOut);
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, user_uid).ok_or(EngineError::PlayerNotFound)?;
            players.array_remove(idx);
            Ok(())
        }

        TournamentEvent::DropOut { player_uid } => {
            if state != TournamentState::Waiting && state != TournamentState::Playing {
                return Err(EngineError::CannotDropOut);
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, player_uid).ok_or(EngineError::PlayerNotFound)?;
            let player_state = PlayerState::from_str(players[idx]["state"].as_str().unwrap_or(""))
                .ok_or("Invalid player state")?;

            if player_state == PlayerState::Finished {
                return Err(EngineError::PlayerAlreadyFinished);
            }

            // Permission: self or organizer
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err(EngineError::DropOutForbidden);
            }

            players[idx]["state"] = "Finished".into();
            Ok(())
        }

        TournamentEvent::CheckIn {
            player_uid,
            vekn_id,
            display_name,
        } => {
            require_state_or_finished(state, TournamentState::Waiting)?;

            // Permission: organizer or self (player checking themselves in)
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err(EngineError::CheckInForbidden);
            }

            let idx = match find_player_index(&tournament["players"], player_uid) {
                Some(idx) => idx,
                None => {
                    if state != TournamentState::Waiting {
                        return Err(EngineError::PlayerNotFound);
                    }
                    // Require VEKN ID for auto-registration (same as Register)
                    if vekn_id.as_ref().is_none_or(|v| v.is_empty()) {
                        return Err(EngineError::VeknIdRequired);
                    }
                    if has_dq_sanction(sanctions, player_uid) {
                        return Err(EngineError::PlayerDisqualified);
                    }
                    if has_active_suspension(sanctions, player_uid) {
                        return Err(EngineError::PlayerSuspended);
                    }
                    let mut player = json::object! {
                        user_uid: player_uid.as_str(),
                        state: "Registered",
                        payment_status: "Pending",
                        toss: 0,
                        result: { gw: 0, vp: 0.0, tp: 0 },
                        finalist: false,
                    };
                    if let Some(dn) = display_name {
                        if !dn.is_empty() {
                            player["display_name"] = dn.as_str().into();
                        }
                    }
                    tournament["players"].push(player)?;
                    tournament["players"].len() - 1
                }
            };

            // Block disqualified players from checking in
            if tournament["players"][idx]["state"].as_str() == Some("Disqualified") {
                return Err(EngineError::PlayerDisqualified);
            }

            // Block players with DQ or suspension sanctions
            if has_dq_sanction(sanctions, player_uid) {
                return Err(EngineError::PlayerDisqualified);
            }
            if has_active_suspension(sanctions, player_uid) {
                return Err(EngineError::PlayerSuspended);
            }

            // Open rounds: a player at their per-player cap can't check in for a new round — but a
            // capped DROP-OUT being reinstated returns to Completed (finals-eligible), not rejected.
            let was_finished = tournament["players"][idx]["state"].as_str() == Some("Finished");
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let at_cap =
                max_rounds > 0 && count_player_rounds_played(tournament, player_uid) >= max_rounds;
            if at_cap && !was_finished {
                return Err(EngineError::PlayerReachedMaxRounds);
            }
            if at_cap {
                // Reinstating a capped drop-out: done with prelims, finals-eligible, no new round.
                tournament["players"][idx]["state"] = "Completed".into();
                return Ok(());
            }

            // Check for missing decklist when required (uses decks parameter)
            let missing_decklist = tournament["decklist_required"].as_bool().unwrap_or(false) && {
                let pk = player_uid.as_str();
                !decks.members().any(|d| d["user_uid"].as_str() == Some(pk))
            };

            tournament["players"][idx]["state"] = "Checked-in".into();
            if missing_decklist {
                tournament["players"][idx]["missing_decklist"] = true.into();
            }

            Ok(())
        }

        TournamentEvent::CheckOut { player_uid } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            let idx = find_player_index(&tournament["players"], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;

            if tournament["players"][idx]["state"].as_str() != Some("Checked-in") {
                return Err(EngineError::PlayerNotCheckedIn);
            }

            tournament["players"][idx]["state"] = if state == TournamentState::Finished {
                "Finished"
            } else {
                "Registered"
            }
            .into();
            Ok(())
        }

        TournamentEvent::CheckInAll => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            // Open rounds: never re-arm a player who already reached their per-player cap
            // (they normally rest in Completed, but Registered/Finished-at-cap can arise after
            // a reopen or a post-cap drop-out). Compute the capped set before the mutable borrow.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let capped: std::collections::HashSet<String> = if max_rounds > 0 {
                tournament["players"]
                    .members()
                    .filter_map(|p| p["user_uid"].as_str().map(String::from))
                    .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                    .collect()
            } else {
                std::collections::HashSet::new()
            };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                let ps = players[i]["state"].as_str().unwrap_or("");
                if ps == "Disqualified" {
                    continue;
                }
                let uid = players[i]["user_uid"].as_str().unwrap_or("");
                if has_dq_sanction(sanctions, uid) || has_active_suspension(sanctions, uid) {
                    continue;
                }
                if capped.contains(uid) {
                    continue;
                }
                if ps == "Registered" || (state == TournamentState::Finished && ps == "Finished") {
                    players[i]["state"] = "Checked-in".into();
                }
            }
            Ok(())
        }

        TournamentEvent::ResetCheckIn => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Checked-in") {
                    players[i]["state"] = if state == TournamentState::Finished {
                        "Finished"
                    } else {
                        "Registered"
                    }
                    .into();
                }
            }
            Ok(())
        }

        TournamentEvent::SetPaymentStatus { player_uid, status } => {
            require_organizer(actor)?;
            match status.as_str() {
                "Pending" | "Paid" | "Refunded" | "Cancelled" => {}
                _ => {
                    return Err(EngineError::internal(format!(
                        "Invalid payment status: {}",
                        status
                    )))
                }
            }
            let idx = find_player_index(&tournament["players"], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            tournament["players"][idx]["payment_status"] = status.as_str().into();
            Ok(())
        }

        TournamentEvent::MarkAllPaid => {
            require_organizer(actor)?;
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["payment_status"].as_str() == Some("Pending") {
                    players[i]["payment_status"] = "Paid".into();
                }
            }
            Ok(())
        }

        TournamentEvent::StartRound {
            seating: submitted_seating,
        } => {
            require_organizer(actor)?;
            let is_online = tournament["online"].as_bool().unwrap_or(false);
            if is_online {
                // Online: allow starting a round while Playing (parallel rounds)
                if state != TournamentState::Waiting
                    && state != TournamentState::Playing
                    && state != TournamentState::Finished
                {
                    return Err(EngineError::WrongState {
                        expected: "Waiting".to_string(),
                        current: state.as_str().to_string(),
                    });
                }
            } else {
                require_state_or_finished(state, TournamentState::Waiting)?;
            }

            // Cannot start prelim round after finals
            if !tournament["finals"].is_null() {
                return Err(EngineError::PrelimAfterFinals);
            }

            // Open rounds: max_rounds is a PER-PLAYER cap, not a tournament-wide total.
            // The tournament may run more rounds than max_rounds (different player subsets each
            // round); players who reached their cap are simply not seated again.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);

            // Get available players: Checked-in, plus Playing for online parallel rounds —
            // excluding any who already reached their per-player round cap.
            let checked_in: Vec<String> = tournament["players"]
                .members()
                .filter(|p| {
                    let s = p["state"].as_str();
                    s == Some("Checked-in") || (is_online && s == Some("Playing"))
                })
                .filter_map(|p| p["user_uid"].as_str().map(|s| s.to_string()))
                .filter(|uid| {
                    max_rounds == 0 || count_player_rounds_played(tournament, uid) < max_rounds
                })
                .collect();

            let n = checked_in.len();
            if n < 4 {
                return Err(EngineError::NotEnoughPlayers);
            }

            // Get previous rounds for seating optimization
            let previous_rounds: Vec<Vec<Vec<String>>> = tournament["rounds"]
                .members()
                .map(|round| {
                    round
                        .members()
                        .map(|table| {
                            table["seating"]
                                .members()
                                .filter_map(|seat| {
                                    seat["player_uid"].as_str().map(|s| s.to_string())
                                })
                                .collect()
                        })
                        .collect()
                })
                .collect();

            // Select which players to seat (handles awkward counts like 6, 7, 11)
            let players_to_seat = seating::select_players_for_round(&checked_in, &previous_rounds);

            // Use submitted seating if provided, otherwise compute
            let new_round: Vec<Vec<String>> = if let Some(submitted) = submitted_seating {
                // Validate submitted seating against the selected subset
                let seat_set: std::collections::HashSet<&str> =
                    players_to_seat.iter().map(|s| s.as_str()).collect();
                let mut seen: std::collections::HashSet<&str> = std::collections::HashSet::new();
                for table in submitted.iter() {
                    if table.len() < 4 || table.len() > 5 {
                        return Err(EngineError::InvalidTableSize { size: table.len() });
                    }
                    for uid in table {
                        if !seat_set.contains(uid.as_str()) {
                            return Err(EngineError::PlayerNotInSubset {
                                player: uid.to_string(),
                            });
                        }
                        if !seen.insert(uid.as_str()) {
                            return Err(EngineError::DuplicatePlayer);
                        }
                    }
                }
                if seen.len() != players_to_seat.len() {
                    return Err(EngineError::SeatingIncomplete);
                }
                submitted.clone()
            } else {
                let seed = seating::seed_for_round(
                    tournament["uid"].as_str().unwrap_or(""),
                    previous_rounds.len(),
                );
                let (computed, _score) =
                    seating::compute_next_round(&players_to_seat, &previous_rounds, seed)?;
                computed
            };

            // Build tables JSON
            let tables: Vec<JsonValue> = new_round
                .iter()
                .map(|table| {
                    let seating: Vec<JsonValue> = table
                        .iter()
                        .map(|player_uid| {
                            json::object! {
                                player_uid: player_uid.as_str(),
                                result: { gw: 0, vp: 0.0, tp: 0 },
                                judge_uid: "",
                            }
                        })
                        .collect();
                    json::object! {
                        seating: seating,
                        state: "In Progress",
                        override: json::Null,
                    }
                })
                .collect();

            tournament["rounds"].push(JsonValue::Array(tables))?;
            if state != TournamentState::Finished {
                tournament["state"] = "Playing".into();
            }

            // Build set of seated player UIDs
            let seated_uids: std::collections::HashSet<String> = new_round
                .iter()
                .flat_map(|table| table.iter().cloned())
                .collect();

            // Mark seated players as Playing, drop registered-but-not-checked-in players
            // Checked-in players not seated (stagger sit-outs) stay Checked-in
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                match players[i]["state"].as_str() {
                    Some("Checked-in") => {
                        if let Some(uid) = players[i]["user_uid"].as_str() {
                            if seated_uids.contains(uid) {
                                players[i]["state"] = "Playing".into();
                            }
                            // else: sitting out, stay Checked-in
                        }
                    }
                    Some("Registered") => players[i]["state"] = "Finished".into(),
                    _ => {}
                }
            }

            Ok(())
        }

        TournamentEvent::FinishRound { round } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundToFinish);
            }

            let target_round_idx = round.unwrap_or(rounds.len() - 1);
            if target_round_idx >= rounds.len() {
                return Err(EngineError::InvalidRound);
            }

            let target_round = &rounds[target_round_idx];

            // Check all tables are finished
            let unfinished: Vec<usize> = target_round
                .members()
                .enumerate()
                .filter(|(_, t)| t["state"].as_str() != Some("Finished"))
                .map(|(i, _)| i)
                .collect();

            if !unfinished.is_empty() {
                return Err(EngineError::TablesNotFinished {
                    tables: unfinished
                        .iter()
                        .map(|i| (i + 1).to_string())
                        .collect::<Vec<_>>()
                        .join(", "),
                });
            }

            // Move players back — only if not in another active round
            let target_state = if state == TournamentState::Finished {
                "Finished"
            } else {
                "Checked-in"
            };
            let still_playing = players_in_other_active_rounds(tournament, target_round_idx);
            // Open rounds: a player who just reached their per-player cap retires to Completed
            // (done with prelims, still finals-eligible) instead of being re-armed as Checked-in.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let maxed: std::collections::HashSet<String> =
                if max_rounds > 0 && state != TournamentState::Finished {
                    tournament["players"]
                        .members()
                        .filter_map(|p| p["user_uid"].as_str().map(String::from))
                        .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                        .collect()
                } else {
                    std::collections::HashSet::new()
                };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Playing") {
                    if let Some(uid) = players[i]["user_uid"].as_str() {
                        if !still_playing.contains(uid) {
                            players[i]["state"] = if maxed.contains(uid) {
                                "Completed"
                            } else {
                                target_state
                            }
                            .into();
                        }
                    }
                }
            }

            if state != TournamentState::Finished && all_rounds_finished(tournament) {
                tournament["state"] = "Waiting".into();
            }
            // else: stay Playing (other rounds still in progress)
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::CancelRound { round } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundToCancel);
            }

            let len = rounds.len();
            // Can only cancel the last round (removing mid-array would shift indices)
            if let Some(idx) = round {
                if *idx != len - 1 {
                    return Err(EngineError::OnlyLastRoundCancellable);
                }
            }

            // Remove last round
            rounds.array_remove(len - 1);

            // Move playing players back — only if not in another active round.
            // Note: exclude_round=len-1 no longer exists in the array, which is
            // correct — we want to check ALL remaining rounds (indices 0..len-2).
            let target_state = if state == TournamentState::Finished {
                "Finished"
            } else {
                "Checked-in"
            };
            let still_playing = players_in_other_active_rounds(tournament, len - 1);
            // Cancelling a round lowers per-player counts; re-arm any Completed (capped) player
            // now back under their cap so they aren't stranded out of the remaining rounds.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let rearm: std::collections::HashSet<String> =
                if max_rounds > 0 && state != TournamentState::Finished {
                    tournament["players"]
                        .members()
                        .filter(|p| p["state"].as_str() == Some("Completed"))
                        .filter_map(|p| p["user_uid"].as_str().map(String::from))
                        .filter(|uid| count_player_rounds_played(tournament, uid) < max_rounds)
                        .collect()
                } else {
                    std::collections::HashSet::new()
                };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                let st = players[i]["state"].as_str();
                let uid = players[i]["user_uid"].as_str().map(String::from);
                if st == Some("Playing") {
                    if let Some(uid) = uid {
                        if !still_playing.contains(&uid) {
                            players[i]["state"] = target_state.into();
                        }
                    }
                } else if st == Some("Completed") {
                    if let Some(uid) = uid {
                        if rearm.contains(&uid) {
                            players[i]["state"] = target_state.into();
                        }
                    }
                }
            }

            if state != TournamentState::Finished
                && (all_rounds_finished(tournament) || tournament["rounds"].is_empty())
            {
                tournament["state"] = "Waiting".into();
            }
            // else: stay Playing (other rounds still in progress)
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::SwapSeats {
            round,
            table1,
            seat1,
            table2,
            seat2,
        } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            // Finals sentinel: round == rounds.len() && table1 == 0 && table2 == 0
            let is_finals = *round == tournament["rounds"].len()
                && !tournament["finals"].is_null()
                && *table1 == 0
                && *table2 == 0;

            if is_finals {
                let seating = &mut tournament["finals"]["seating"];
                if *seat1 >= seating.len() || *seat2 >= seating.len() {
                    return Err(EngineError::InvalidSeat);
                }
                let uid1 = seating[*seat1]["player_uid"]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                let uid2 = seating[*seat2]["player_uid"]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                seating[*seat1]["player_uid"] = uid2.as_str().into();
                seating[*seat2]["player_uid"] = uid1.as_str().into();
            } else {
                let rounds = &mut tournament["rounds"];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                let round_tables = &mut rounds[*round];
                if *table1 >= round_tables.len() || *table2 >= round_tables.len() {
                    return Err(EngineError::InvalidTable);
                }
                if *seat1 >= round_tables[*table1]["seating"].len()
                    || *seat2 >= round_tables[*table2]["seating"].len()
                {
                    return Err(EngineError::InvalidSeat);
                }
                let uid1 = round_tables[*table1]["seating"][*seat1]["player_uid"]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                let uid2 = round_tables[*table2]["seating"][*seat2]["player_uid"]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                round_tables[*table1]["seating"][*seat1]["player_uid"] = uid2.as_str().into();
                round_tables[*table2]["seating"][*seat2]["player_uid"] = uid1.as_str().into();
            }

            Ok(())
        }

        TournamentEvent::AlterSeating { round, seating } => {
            require_organizer(actor)?;
            if state != TournamentState::Playing
                && state != TournamentState::Finished
                && state != TournamentState::Waiting
            {
                return Err(EngineError::CannotAlterSeating);
            }

            let rounds_len = tournament["rounds"].len();
            let is_finals = *round == rounds_len && !tournament["finals"].is_null();

            // Validate no duplicate players in new seating
            {
                let all_uids: Vec<&String> = seating.iter().flat_map(|t| t.iter()).collect();
                let unique: std::collections::HashSet<&String> = all_uids.iter().copied().collect();
                if all_uids.len() != unique.len() {
                    return Err(EngineError::DuplicatePlayer);
                }
            }

            if is_finals {
                // Replace finals seating player UIDs
                let finals = &mut tournament["finals"]["seating"];
                if seating.len() != 1 {
                    return Err(EngineError::FinalsOneTable);
                }
                let new_players = &seating[0];
                if new_players.len() != finals.len() {
                    return Err(EngineError::FinalsPlayerCount);
                }
                // Verify same set of players
                let old_set: std::collections::HashSet<String> = (0..finals.len())
                    .map(|i| finals[i]["player_uid"].as_str().unwrap_or("").to_string())
                    .collect();
                let new_set: std::collections::HashSet<&String> = new_players.iter().collect();
                if old_set.len() != new_set.len()
                    || !new_players.iter().all(|uid| old_set.contains(uid))
                {
                    return Err(EngineError::FinalsPlayerSet);
                }
                for (i, uid) in new_players.iter().enumerate() {
                    finals[i]["player_uid"] = uid.as_str().into();
                }
            } else {
                // Round seating
                if *round >= rounds_len {
                    return Err(EngineError::InvalidRound);
                }

                // Validation phase (immutable borrows)
                // The payload is positional: tables 0..table_count match the existing
                // tables by index (results/overrides are preserved per index), extra
                // tables are appended. Empty tables are draft workspaces, dropped after
                // the rebuild; non-empty tables must seat 4 or 5 players.
                let table_count = tournament["rounds"][*round].len();
                if seating.len() < table_count {
                    return Err(EngineError::TableCountMismatch);
                }
                for table in seating.iter() {
                    if !table.is_empty() && !(4..=5).contains(&table.len()) {
                        return Err(EngineError::InvalidTableSize { size: table.len() });
                    }
                }

                // Build map: player_uid -> (old_table, old_result, judge_uid) from current state
                let mut old_results: std::collections::HashMap<String, (usize, JsonValue, String)> =
                    std::collections::HashMap::new();
                for t in 0..table_count {
                    for s in 0..tournament["rounds"][*round][t]["seating"].len() {
                        let uid = tournament["rounds"][*round][t]["seating"][s]["player_uid"]
                            .as_str()
                            .unwrap_or("")
                            .to_string();
                        let result =
                            tournament["rounds"][*round][t]["seating"][s]["result"].clone();
                        let judge = tournament["rounds"][*round][t]["seating"][s]["judge_uid"]
                            .as_str()
                            .unwrap_or("")
                            .to_string();
                        old_results.insert(uid, (t, result, judge));
                    }
                }

                // Validate new seating has exact same player set
                let new_total: usize = seating.iter().map(|t| t.len()).sum();
                if new_total != old_results.len() {
                    return Err(EngineError::PlayerCountMismatch);
                }

                // R1 check: reject predator-prey repeats
                {
                    let mut check_rounds: Vec<Vec<Vec<String>>> = Vec::new();
                    for r in 0..rounds_len {
                        if r == *round {
                            check_rounds.push(seating.clone());
                        } else {
                            let rd = &tournament["rounds"][r];
                            let mut tables = Vec::new();
                            for t in 0..rd.len() {
                                let mut tbl = Vec::new();
                                for s in 0..rd[t]["seating"].len() {
                                    tbl.push(
                                        rd[t]["seating"][s]["player_uid"]
                                            .as_str()
                                            .unwrap_or("")
                                            .to_string(),
                                    );
                                }
                                tables.push(tbl);
                            }
                            check_rounds.push(tables);
                        }
                    }
                    let issues = seating::compute_player_issues(&check_rounds);
                    if issues.iter().any(|i| i.rule == 0) {
                        return Err(EngineError::SeatingViolatesR1);
                    }
                }

                // Mutation phase (mutable borrow)
                let round_data = &mut tournament["rounds"][*round];

                // Rebuild each table's seating
                for t in 0..seating.len() {
                    if t >= round_data.len() {
                        round_data.push(json::object! {
                            seating: [],
                            state: "In Progress",
                            override: json::Null,
                        })?;
                    }
                    let new_players = &seating[t];
                    let mut new_seating = Vec::new();
                    for uid in new_players {
                        let (old_table, old_result, old_judge) =
                            old_results
                                .get(uid)
                                .ok_or_else(|| EngineError::PlayerNotInRound {
                                    player: uid.to_string(),
                                })?;
                        // Preserve result and judge_uid if player stays in same table, reset otherwise
                        let (result, judge) = if *old_table == t {
                            (old_result.clone(), old_judge.as_str())
                        } else {
                            (json::object! { gw: 0, vp: 0.0, tp: 0 }, "")
                        };
                        new_seating.push(json::object! {
                            player_uid: uid.as_str(),
                            result: result,
                            judge_uid: judge,
                        });
                    }
                    round_data[t]["seating"] = JsonValue::Array(new_seating);

                    // Recompute table state: if all VPs are 0, it's "In Progress"
                    let vps: Vec<f64> = (0..round_data[t]["seating"].len())
                        .map(|s| {
                            round_data[t]["seating"][s]["result"]["vp"]
                                .as_f64()
                                .unwrap_or(0.0)
                        })
                        .collect();
                    if round_data[t]["override"].is_null() {
                        let all_zero = vps.iter().all(|&v| v == 0.0);
                        if all_zero {
                            round_data[t]["state"] = "In Progress".into();
                        }
                        // If not all zero, keep existing state (scores were preserved for same-table)
                    }
                }

                // Drop empty tables (draft workspaces, or tables emptied by moves)
                for t in (0..round_data.len()).rev() {
                    if round_data[t]["seating"].is_empty() {
                        round_data.array_remove(t);
                    }
                }
            }

            Ok(())
        }

        TournamentEvent::SeatPlayer {
            player_uid,
            table,
            seat,
        } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            // Verify player exists and is Registered
            let player_idx = find_player_index(&tournament["players"], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            let player_state = tournament["players"][player_idx]["state"]
                .as_str()
                .unwrap_or("");
            if player_state != "Registered"
                && !(state == TournamentState::Finished && player_state == "Finished")
            {
                return Err(EngineError::PlayerWrongState {
                    current: player_state.to_string(),
                });
            }

            // Verify table exists in current round
            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = rounds.len() - 1;
            if *table >= rounds[last].len() {
                return Err(EngineError::InvalidTable);
            }

            // Verify table is not already full (max 5 players)
            let seating = &mut rounds[last][*table]["seating"];
            let seating_len = seating.len();
            if seating_len >= 5 {
                return Err(EngineError::TableFull);
            }
            let insert_pos = if *seat > seating_len {
                seating_len
            } else {
                *seat
            };

            let seat_entry = json::object! {
                player_uid: player_uid.as_str(),
                result: { gw: 0, vp: 0.0, tp: 0 },
                judge_uid: "",
            };

            // Insert by rebuilding array
            let mut new_seating = Vec::new();
            for i in 0..seating_len {
                if i == insert_pos {
                    new_seating.push(seat_entry.clone());
                }
                new_seating.push(seating[i].clone());
            }
            if insert_pos >= seating_len {
                new_seating.push(seat_entry);
            }
            rounds[last][*table]["seating"] = JsonValue::Array(new_seating);

            // Set player state to Playing
            tournament["players"][player_idx]["state"] = "Playing".into();
            Ok(())
        }

        TournamentEvent::UnseatPlayer { player_uid } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = rounds.len() - 1;

            // Find and remove player from seating
            let mut found = false;
            for t in 0..rounds[last].len() {
                let seating = &rounds[last][t]["seating"];
                let mut seat_idx = None;
                for s in 0..seating.len() {
                    if seating[s]["player_uid"].as_str() == Some(player_uid) {
                        seat_idx = Some(s);
                        break;
                    }
                }
                if let Some(s) = seat_idx {
                    rounds[last][t]["seating"].array_remove(s);
                    found = true;
                    break;
                }
            }

            if !found {
                return Err(EngineError::PlayerNotInRound {
                    player: player_uid.to_string(),
                });
            }

            // Set player state back to Registered
            if let Some(idx) = find_player_index(&tournament["players"], player_uid) {
                tournament["players"][idx]["state"] = "Registered".into();
            }
            Ok(())
        }

        TournamentEvent::AddTable => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = rounds.len() - 1;

            let empty_table = json::object! {
                seating: [],
                state: "In Progress",
                override: json::Null,
            };
            rounds[last].push(empty_table)?;
            Ok(())
        }

        TournamentEvent::RemoveTable { table } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = rounds.len() - 1;
            if *table >= rounds[last].len() {
                return Err(EngineError::InvalidTable);
            }
            if !rounds[last][*table]["seating"].is_empty() {
                return Err(EngineError::TableNotEmpty);
            }
            rounds[last].array_remove(*table);
            Ok(())
        }

        TournamentEvent::SetScore {
            round,
            table,
            scores,
        } => {
            // Players score only mid-round; organizers may correct any round between
            // rounds (Waiting) or after the tournament has finished.
            require_can_edit_results(actor, state)?;

            // If round == rounds.len() and finals exists, target finals table
            let rounds_len = tournament["rounds"].len();
            let is_finals = *round == rounds_len && !tournament["finals"].is_null() && *table == 0;

            // Resolve SA effective rounds from the whole tournament BEFORE taking the
            // mutable borrow of `t` below (scores don't move seats, so resolving here
            // is equivalent and avoids a borrow conflict).
            let effective_sas = sanctions::resolve_sa_effective_rounds(tournament, sanctions);

            let t = if is_finals {
                &mut tournament["finals"]
            } else {
                let rounds = &tournament["rounds"];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                if *table >= rounds[*round].len() {
                    return Err(EngineError::InvalidTable);
                }
                &mut tournament["rounds"][*round][*table]
            };

            // Check permission: organizer or player at this table
            let is_at_table = t["seating"]
                .members()
                .any(|s| s["player_uid"].as_str() == Some(&actor.uid));

            if !actor.is_organizer && !is_at_table {
                return Err(EngineError::ScoreForbidden);
            }

            // If table has override and actor is not organizer, deny
            if !t["override"].is_null() && !actor.is_organizer {
                return Err(EngineError::ScoreLocked);
            }

            // If any seat was scored by an organizer, non-organizers cannot change scores
            if !actor.is_organizer {
                let has_judge_score = t["seating"]
                    .members()
                    .any(|s| !s["judge_uid"].as_str().unwrap_or("").is_empty());
                if has_judge_score {
                    return Err(EngineError::ScoreSetByOrganizer);
                }
            }

            let table_size = t["seating"].len();

            // Basic VP validation per seat
            for score in scores.iter() {
                let vp = score.vp;
                // Must be in [0, table_size] in 0.5 steps
                if (vp < 0.0 || vp > table_size as f64 || (vp * 2.0).fract() != 0.0)
                    && !actor.is_organizer
                {
                    return Err(EngineError::internal(format!("Invalid VP value: {}", vp)));
                }
                // table_size - 0.5 is impossible (non-organizer blocked)
                if !actor.is_organizer && vp == table_size as f64 - 0.5 {
                    return Err(EngineError::internal(format!(
                        "VP value {} is impossible",
                        vp
                    )));
                }
            }

            // Build a map from player_uid -> vp from the scores
            let vp_map: std::collections::HashMap<&str, f64> = scores
                .iter()
                .map(|s| (s.player_uid.as_str(), s.vp))
                .collect();

            // Gather VPs in seating order (predator-prey order)
            let mut vps: Vec<f64> = Vec::with_capacity(table_size);
            for i in 0..table_size {
                let player_uid = t["seating"][i]["player_uid"].as_str().unwrap_or("");
                let vp = vp_map
                    .get(player_uid)
                    .copied()
                    .unwrap_or(t["seating"][i]["result"]["vp"].as_f64().unwrap_or(0.0));
                vps.push(vp);
            }

            // Per-seat SA adjustments (-1.0 VP per SA on this round). Same helper the
            // standings/rating recompute uses, so GW/TP stay consistent everywhere.
            let current_round = if is_finals { rounds_len } else { *round };
            let adjustments = table_sa_adjustments(&t["seating"], current_round, &effective_sas);

            let gws = if is_finals {
                let seating_uids: Vec<&str> = (0..table_size)
                    .map(|i| t["seating"][i]["player_uid"].as_str().unwrap_or(""))
                    .collect();
                let seed_order: Vec<String> = t["seed_order"]
                    .members()
                    .filter_map(|s| s.as_str().map(|v| v.to_string()))
                    .collect();
                compute_gw_finals(&vps, &adjustments, &seating_uids, &seed_order)
            } else {
                compute_gw(&vps, &adjustments)
            };
            let tps = compute_tp(table_size, &vps, &adjustments);

            // Apply scores
            for i in 0..table_size {
                let player_uid = t["seating"][i]["player_uid"]
                    .as_str()
                    .unwrap_or("")
                    .to_string();
                if vp_map.contains_key(player_uid.as_str()) {
                    t["seating"][i]["result"]["vp"] = vps[i].into();
                    t["seating"][i]["result"]["gw"] = gws[i].into();
                    t["seating"][i]["result"]["tp"] = tps[i].into();
                    if actor.is_organizer {
                        t["seating"][i]["judge_uid"] = actor.uid.as_str().into();
                    }
                }
            }

            // Determine table state using oust-order validation
            // Only recompute state if override is not set (override forces Finished)
            if t["override"].is_null() {
                let vp_err = check_table_vps(&vps);
                match vp_err {
                    Some(VpError::InsufficientTotal) => {
                        t["state"] = "In Progress".into();
                    }
                    Some(_) => {
                        // Invalid oust order or other error
                        if !actor.is_organizer {
                            // Non-organizer: reject impossible oust sequences
                            return Err(EngineError::InvalidScore);
                        }
                        t["state"] = "Invalid".into();
                    }
                    None => {
                        t["state"] = "Finished".into();
                    }
                }
            }

            // Keep stored standings in sync with the edited result. Required for
            // out-of-round corrections (Waiting/Finished) and edits to an already-
            // finished round while another is still Playing — FinishRound won't run
            // again to refresh them, and ratings/VEKN-push/exports read them.
            update_standings(tournament, sanctions);

            Ok(())
        }

        TournamentEvent::Override {
            round,
            table,
            comment,
        } => {
            require_organizer(actor)?;
            require_can_edit_results(actor, state)?;

            let is_finals = *round == tournament["rounds"].len()
                && !tournament["finals"].is_null()
                && *table == 0;
            let t = if is_finals {
                &mut tournament["finals"]
            } else {
                let rounds = &tournament["rounds"];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                if *table >= rounds[*round].len() {
                    return Err(EngineError::InvalidTable);
                }
                &mut tournament["rounds"][*round][*table]
            };
            t["override"] = json::object! {
                judge_uid: actor.uid.as_str(),
                comment: comment.as_str(),
            };
            // Override forces table to Finished
            t["state"] = "Finished".into();

            Ok(())
        }

        TournamentEvent::Unoverride { round, table } => {
            require_organizer(actor)?;
            require_can_edit_results(actor, state)?;

            let is_finals = *round == tournament["rounds"].len()
                && !tournament["finals"].is_null()
                && *table == 0;
            let t = if is_finals {
                &mut tournament["finals"]
            } else {
                let rounds = &tournament["rounds"];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                if *table >= rounds[*round].len() {
                    return Err(EngineError::InvalidTable);
                }
                &mut tournament["rounds"][*round][*table]
            };
            t["override"] = json::Null;

            // Recompute table state from current VPs
            let table_size = t["seating"].len();
            let vps: Vec<f64> = (0..table_size)
                .map(|i| t["seating"][i]["result"]["vp"].as_f64().unwrap_or(0.0))
                .collect();
            let vp_err = check_table_vps(&vps);
            match vp_err {
                Some(VpError::InsufficientTotal) => {
                    t["state"] = "In Progress".into();
                }
                Some(_) => {
                    t["state"] = "Invalid".into();
                }
                None => {
                    t["state"] = "Finished".into();
                }
            }

            Ok(())
        }

        TournamentEvent::SetToss { player_uid, toss } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if tournament["rounds"].len() < 2 {
                return Err(EngineError::TossMinRounds);
            }
            let idx = find_player_index(&tournament["players"], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            tournament["players"][idx]["toss"] = (*toss).into();
            Ok(())
        }

        TournamentEvent::RandomToss => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if tournament["rounds"].len() < 2 {
                return Err(EngineError::TossMinRounds);
            }

            let standings = compute_preliminary_standings(tournament, sanctions);

            // Find tied groups in top-5 cutoff zone that need toss
            // Group players by (gw, vp, tp) where toss == 0
            let cutoff = standings.len().min(5);
            // Include players beyond #5 that tie with #5
            let mut zone_end = cutoff;
            if cutoff > 0 && standings.len() > cutoff {
                let fifth = &standings[cutoff - 1];
                while zone_end < standings.len() {
                    let s = &standings[zone_end];
                    if s.gw == fifth.gw && s.vp == fifth.vp && s.tp == fifth.tp {
                        zone_end += 1;
                    } else {
                        break;
                    }
                }
            }

            // Find groups of tied players with toss == 0
            let mut i = 0;
            let mut toss_counter: u32 = 1;
            // Simple deterministic shuffle using tournament uid as seed
            let seed: u64 = tournament["uid"]
                .as_str()
                .unwrap_or("")
                .bytes()
                .fold(0u64, |acc, b| acc.wrapping_mul(31).wrapping_add(b as u64));

            while i < zone_end {
                let mut j = i + 1;
                while j < zone_end
                    && standings[j].gw == standings[i].gw
                    && standings[j].vp == standings[i].vp
                    && standings[j].tp == standings[i].tp
                {
                    j += 1;
                }
                // i..j is a group of players with same scores
                if j - i > 1 {
                    // Collect those with toss == 0
                    let mut needs_toss: Vec<usize> =
                        (i..j).filter(|&k| standings[k].toss == 0).collect();
                    if needs_toss.len() > 1 {
                        // Shuffle using simple Fisher-Yates with deterministic seed
                        let mut rng = seed.wrapping_add(i as u64);
                        for k in (1..needs_toss.len()).rev() {
                            rng = rng
                                .wrapping_mul(6364136223846793005)
                                .wrapping_add(1442695040888963407);
                            let swap_idx = (rng >> 33) as usize % (k + 1);
                            needs_toss.swap(k, swap_idx);
                        }
                        // Assign sequential toss values
                        for &idx in &needs_toss {
                            let uid = &standings[idx].user_uid;
                            if let Some(pi) = find_player_index(&tournament["players"], uid) {
                                tournament["players"][pi]["toss"] = toss_counter.into();
                                toss_counter += 1;
                            }
                        }
                    }
                }
                i = j;
            }

            Ok(())
        }

        TournamentEvent::StartFinals => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if tournament["rounds"].len() < 2 {
                return Err(EngineError::FinalsMinRounds);
            }
            if !tournament["finals"].is_null() {
                return Err(EngineError::FinalsAlreadyStarted);
            }

            let standings = compute_preliminary_standings(tournament, sanctions);

            // Finals consideration excludes the disqualified and the withdrawn/dropped (Finished).
            // Players who reached their per-player cap rest in Completed and stay eligible; a
            // withdrawn finalist is dropped here so the next-ranked qualifier is promoted.
            let eligible: Vec<&standings::Standing> = standings
                .iter()
                .filter(|s| {
                    let player = tournament["players"]
                        .members()
                        .find(|p| p["user_uid"].as_str() == Some(&s.user_uid));
                    let ps = player.and_then(|p| p["state"].as_str()).unwrap_or("");
                    // `disqualified` carries the dual DQ signal (state OR active DQ
                    // sanction) the standings already resolved — use it so finals
                    // eligibility can't diverge from who got zeroed.
                    !s.disqualified && ps != "Finished"
                })
                .collect();

            if eligible.len() < 5 {
                return Err(EngineError::FinalsNotEnoughPlayers);
            }
            if top5_has_ties(&eligible) {
                return Err(EngineError::FinalsUnresolvedTies);
            }

            // Top 5 eligible players form the finals table
            let top5: Vec<&standings::Standing> = eligible.into_iter().take(5).collect();
            let seed_order: Vec<JsonValue> =
                top5.iter().map(|s| s.user_uid.as_str().into()).collect();
            let seating: Vec<JsonValue> = top5
                .iter()
                .map(|s| {
                    json::object! {
                        player_uid: s.user_uid.as_str(),
                        result: { gw: 0, vp: 0.0, tp: 0 },
                        judge_uid: "",
                    }
                })
                .collect();

            tournament["finals"] = json::object! {
                seating: JsonValue::Array(seating),
                state: "In Progress",
                override: json::Null,
                seed_order: JsonValue::Array(seed_order),
            };

            // Mark top 5 players as Playing and finalist
            for s in &top5 {
                if let Some(idx) = find_player_index(&tournament["players"], &s.user_uid) {
                    tournament["players"][idx]["state"] = "Playing".into();
                    tournament["players"][idx]["finalist"] = true.into();
                }
            }

            if state != TournamentState::Finished {
                tournament["state"] = "Playing".into();
            }
            Ok(())
        }

        TournamentEvent::FinishFinals => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;
            if tournament["finals"].is_null() {
                return Err(EngineError::NoFinalsInProgress);
            }

            let finals_state = tournament["finals"]["state"].as_str().unwrap_or("");
            if finals_state != "Finished" {
                return Err(EngineError::FinalsTableUnfinished);
            }

            // Determine winner: highest VP in finals, tiebreak by seed order
            let seed_order: Vec<String> = tournament["finals"]["seed_order"]
                .members()
                .filter_map(|s| s.as_str().map(|v| v.to_string()))
                .collect();
            let seating = &tournament["finals"]["seating"];
            let mut best_uid = String::new();
            let mut best_vp = -1.0f64;
            let mut best_seed = usize::MAX;

            for seat in seating.members() {
                let uid = seat["player_uid"].as_str().unwrap_or("").to_string();
                let vp = seat["result"]["vp"].as_f64().unwrap_or(0.0);
                let seed_pos = seed_order
                    .iter()
                    .position(|s| s == &uid)
                    .unwrap_or(usize::MAX);
                if vp > best_vp || (vp == best_vp && seed_pos < best_seed) {
                    best_vp = vp;
                    best_uid = uid;
                    best_seed = seed_pos;
                }
            }

            tournament["winner"] = best_uid.as_str().into();
            if state != TournamentState::Finished {
                tournament["state"] = "Finished".into();
            }

            // Mark all players as finished (except DQ'd)
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() != Some("Disqualified") {
                    players[i]["state"] = "Finished".into();
                }
            }

            // Recompute standings so finalist flags are up-to-date
            update_standings(tournament, sanctions);

            Ok(())
        }

        TournamentEvent::CancelFinals => {
            // Revert a seated (not-yet-finalized) finals back to Waiting so the organizer can
            // drop a no-show finalist and re-run StartFinals (which then promotes the next
            // qualifier). Only valid while finals are in progress, not after FinishFinals.
            require_organizer(actor)?;
            require_state(state, TournamentState::Playing)?;
            if tournament["finals"].is_null() {
                return Err(EngineError::NoFinalsInProgress);
            }

            // Capped (open-rounds) finalists return to Completed; the rest to Checked-in. Compute
            // the capped set before the mutable borrow.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let capped: std::collections::HashSet<String> = if max_rounds > 0 {
                tournament["players"]
                    .members()
                    .filter(|p| p["finalist"].as_bool().unwrap_or(false))
                    .filter_map(|p| p["user_uid"].as_str().map(String::from))
                    .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                    .collect()
            } else {
                std::collections::HashSet::new()
            };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["finalist"].as_bool().unwrap_or(false) {
                    let uid = players[i]["user_uid"].as_str().unwrap_or("").to_string();
                    players[i]["finalist"] = false.into();
                    players[i]["state"] = if capped.contains(&uid) {
                        "Completed"
                    } else {
                        "Checked-in"
                    }
                    .into();
                }
            }

            tournament["finals"] = json::Null;
            tournament["state"] = "Waiting".into();
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::FinishTournament => {
            require_organizer(actor)?;
            if state != TournamentState::Waiting
                && state != TournamentState::Playing
                && state != TournamentState::Finished
            {
                return Err(EngineError::CannotFinish);
            }

            tournament["state"] = "Finished".into();

            // Mark all players as finished (except DQ'd)
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() != Some("Disqualified") {
                    players[i]["state"] = "Finished".into();
                }
            }

            update_standings(tournament, sanctions);

            // Emit deck_ops to flip public on qualifying decks
            for d in decks.members() {
                let user_uid = d["user_uid"].as_str().unwrap_or("");
                if user_uid.is_empty() {
                    continue;
                }
                let is_public = compute_deck_public(tournament, user_uid);
                if is_public {
                    let op = json::object! {
                        "op" => "set_public",
                        "deck_uid" => d["uid"].as_str().unwrap_or(""),
                        "public" => true,
                    };
                    let _ = deck_ops.push(op);
                }
            }
            Ok(())
        }

        TournamentEvent::UpsertDeck {
            player_uid,
            deck,
            multideck,
        } => {
            // Auth: organizer or self
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err(EngineError::DeckUploadForbidden);
            }
            // Verify player is registered
            let is_registered = tournament["players"]
                .members()
                .any(|p| p["user_uid"].as_str() == Some(player_uid.as_str()));
            if !is_registered {
                return Err(EngineError::NotRegistered);
            }
            // Lifecycle: non-organizers restricted by tournament state
            if !actor.is_organizer {
                let existing_count = decks
                    .members()
                    .filter(|d| d["user_uid"].as_str() == Some(player_uid.as_str()))
                    .count();
                match state {
                    TournamentState::Playing => {
                        if *multideck {
                            // Multideck: new deck goes at index == existing_count
                            // Block if that round has already been played
                            if is_deck_locked(tournament, player_uid, existing_count) {
                                return Err(EngineError::DeckLockedRound);
                            }
                        } else if existing_count > 0 {
                            return Err(EngineError::DeckLockedPlaying);
                        }
                    }
                    TournamentState::Finished if existing_count > 0 => {
                        return Err(EngineError::DeckLockedFinished);
                    }
                    _ => {} // Planned, Registration, Waiting: always allowed
                }
            }
            // Compute public flag
            let is_public = compute_deck_public(tournament, player_uid);
            // Build deck data with public flag
            let mut deck_data = deck.clone();
            deck_data["public"] = is_public.into();
            // Emit deck_ops upsert (tournament unchanged for deck events)
            let op = json::object! {
                "op" => "upsert",
                "player_uid" => player_uid.as_str(),
                "deck" => deck_data,
                "multideck" => *multideck,
            };
            let _ = deck_ops.push(op);
            Ok(())
        }

        TournamentEvent::DeleteDeck {
            player_uid,
            deck_index,
            multideck,
        } => {
            // Auth: organizer or self
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err(EngineError::DeckDeleteForbidden);
            }
            // Lifecycle: non-organizers restricted
            if !actor.is_organizer {
                match state {
                    TournamentState::Playing => {
                        if *multideck {
                            if let Some(idx) = deck_index {
                                if is_deck_locked(tournament, player_uid, *idx) {
                                    return Err(EngineError::DeckLockedRound);
                                }
                            } else {
                                return Err(EngineError::internal(
                                    "deck_index required for multideck delete",
                                ));
                            }
                        } else {
                            return Err(EngineError::DeckLockedPlaying);
                        }
                    }
                    TournamentState::Finished => {
                        return Err(EngineError::DeckLockedFinished);
                    }
                    _ => {} // Planned, Registration, Waiting: always allowed
                }
            }
            // Emit deck_ops delete
            let op = json::object! {
                "op" => "delete",
                "player_uid" => player_uid.as_str(),
                "deck_index" => match deck_index { Some(i) => JsonValue::from(*i), None => JsonValue::Null },
                "multideck" => *multideck,
            };
            let _ = deck_ops.push(op);
            Ok(())
        }

        TournamentEvent::RaffleDraw {
            label,
            pool,
            exclude_drawn,
            count,
            seed,
        } => {
            require_organizer(actor)?;
            if state != TournamentState::Waiting
                && state != TournamentState::Playing
                && state != TournamentState::Finished
            {
                return Err(EngineError::RaffleWrongState);
            }
            if *count == 0 {
                return Err(EngineError::RaffleCountMin);
            }
            let mut eligible = get_raffle_pool(tournament, sanctions, pool, *exclude_drawn)?;
            if eligible.is_empty() {
                return Err(EngineError::RaffleNoPlayers);
            }
            // Fisher-Yates shuffle with caller-provided seed (same LCG as RandomToss)
            let mut rng = *seed;
            for k in (1..eligible.len()).rev() {
                rng = rng
                    .wrapping_mul(6364136223846793005)
                    .wrapping_add(1442695040888963407);
                let swap_idx = (rng >> 33) as usize % (k + 1);
                eligible.swap(k, swap_idx);
            }
            let winners: Vec<JsonValue> = eligible
                .into_iter()
                .take(*count)
                .map(|uid| uid.into())
                .collect();
            let draw = json::object! {
                "label" => label.as_str(),
                "pool" => pool.as_str(),
                "winners" => JsonValue::Array(winners),
            };
            if tournament["raffles"].is_null() {
                tournament["raffles"] = JsonValue::new_array();
            }
            tournament["raffles"].push(draw)?;
            Ok(())
        }

        TournamentEvent::RaffleUndo => {
            require_organizer(actor)?;
            if tournament["raffles"].is_null() || tournament["raffles"].is_empty() {
                return Err(EngineError::RaffleNoDraws);
            }
            let last = tournament["raffles"].len() - 1;
            tournament["raffles"].array_remove(last);
            Ok(())
        }

        TournamentEvent::RaffleClear => {
            require_organizer(actor)?;
            tournament["raffles"] = JsonValue::new_array();
            Ok(())
        }

        TournamentEvent::UpdateConfig { config } => {
            require_organizer(actor)?;

            // Validate shared config fields
            validate_config_fields(config)?;

            if let Some(mr) = config["max_rounds"].as_usize() {
                if mr != 0 {
                    // Per-player cap: can't drop below what any single player has already played.
                    let completed = tournament["players"]
                        .members()
                        .filter_map(|p| p["user_uid"].as_str())
                        .map(|uid| count_player_rounds_played(tournament, uid))
                        .max()
                        .unwrap_or(0);
                    if mr < completed {
                        return Err(EngineError::MaxRoundsBelowCompleted { max: mr, completed });
                    }
                }
            }
            // Validate league_uid: only league organizers (or IC) can link
            if config.has_key("league_uid") && !config["league_uid"].is_null() {
                let league_uid = config["league_uid"].as_str().unwrap_or("");
                if !league_uid.is_empty()
                    && !actor.roles.contains(&"IC".to_string())
                    && !actor
                        .can_organize_league_uids
                        .contains(&league_uid.to_string())
                {
                    return Err(EngineError::LeagueLinkForbidden);
                }
            }

            // Check if decklists_mode is changing on a Finished tournament
            let decklists_mode_changing =
                config.has_key("decklists_mode") && state == TournamentState::Finished;

            // Apply config fields (key present = apply, even if null)
            let config_fields = [
                "name",
                "format",
                "rank",
                "online",
                "start",
                "finish",
                "timezone",
                "country",
                "venue",
                "venue_url",
                "address",
                "map_url",
                "proxies",
                "multideck",
                "decklist_required",
                "description",
                "standings_mode",
                "decklists_mode",
                "max_rounds",
                "table_rooms",
                "league_uid",
                "round_time",
                "finals_time",
            ];
            for field in config_fields {
                if config.has_key(field) {
                    tournament[field] = config[field].clone();
                }
            }

            // Recompute deck public flags if decklists_mode changed on Finished tournament
            if decklists_mode_changing {
                for d in decks.members() {
                    let user_uid = d["user_uid"].as_str().unwrap_or("");
                    let deck_uid = d["uid"].as_str().unwrap_or("");
                    if user_uid.is_empty() || deck_uid.is_empty() {
                        continue;
                    }
                    let is_public = compute_deck_public(tournament, user_uid);
                    let op = json::object! {
                        "op" => "set_public",
                        "deck_uid" => deck_uid,
                        "public" => is_public,
                    };
                    let _ = deck_ops.push(op);
                }
            }

            Ok(())
        }

        TournamentEvent::CreateTournament { .. } => Err(EngineError::internal(
            "CreateTournament is not a tournament event — use create_tournament() instead",
        )),
    }
}
