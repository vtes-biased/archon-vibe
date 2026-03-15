//! Helper functions for tournament event processing.

use json::JsonValue;

use super::types::{ActorContext, TournamentState};

/// Returns true if a deck at the given index is locked (its round has already started).
pub(super) fn is_deck_locked(tournament: &JsonValue, deck_index: usize) -> bool {
    let rounds_played = tournament["rounds"].len();
    deck_index < rounds_played
}

pub(super) fn require_organizer(actor: &ActorContext) -> Result<(), String> {
    if !actor.is_organizer {
        return Err("Only organizers can perform this action".to_string());
    }
    Ok(())
}

pub(super) fn require_state(
    current: TournamentState,
    expected: TournamentState,
) -> Result<(), String> {
    if current != expected {
        return Err(format!(
            "Tournament must be in {} state (currently {})",
            expected.as_str(),
            current.as_str()
        ));
    }
    Ok(())
}

pub(super) fn require_state_or_finished(
    current: TournamentState,
    expected: TournamentState,
) -> Result<(), String> {
    if current != expected && current != TournamentState::Finished {
        return Err(format!(
            "Tournament must be in {} state (currently {})",
            expected.as_str(),
            current.as_str()
        ));
    }
    Ok(())
}

pub(super) fn player_exists(players: &JsonValue, user_uid: &str) -> bool {
    players
        .members()
        .any(|p| p["user_uid"].as_str() == Some(user_uid))
}

pub(super) fn find_player_index(players: &JsonValue, user_uid: &str) -> Option<usize> {
    players
        .members()
        .position(|p| p["user_uid"].as_str() == Some(user_uid))
}

pub(super) fn validate_enum(value: &str, valid: &[&str], field: &str) -> Result<(), String> {
    if !valid.contains(&value) {
        return Err(format!("Invalid {}: {}", field, value));
    }
    Ok(())
}

pub(super) fn count_completed_rounds(tournament: &JsonValue) -> usize {
    tournament["rounds"]
        .members()
        .filter(|round| {
            round
                .members()
                .all(|t| t["state"].as_str() == Some("Finished"))
        })
        .count()
}

pub(super) fn all_rounds_finished(tournament: &JsonValue) -> bool {
    let rounds = &tournament["rounds"];
    !rounds.is_empty()
        && rounds.members().all(|round| {
            round
                .members()
                .all(|table| table["state"].as_str() == Some("Finished"))
        })
}

/// Collect user UIDs of players still playing in rounds other than `exclude_round`.
pub(super) fn players_in_other_active_rounds(
    tournament: &JsonValue,
    exclude_round: usize,
) -> std::collections::HashSet<String> {
    tournament["rounds"]
        .members()
        .enumerate()
        .filter(|(i, _)| *i != exclude_round)
        .flat_map(|(_, round)| round.members())
        .filter(|table| table["state"].as_str() != Some("Finished"))
        .flat_map(|table| table["seating"].members())
        .filter_map(|seat| seat["player_uid"].as_str().map(|s| s.to_string()))
        .collect()
}
