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
    let total = tournament["rounds"].len();
    if total == 0 {
        return 0;
    }
    // Check if the last round is still in progress (has "In Progress" tables)
    let last_round = &tournament["rounds"][total - 1];
    let has_in_progress = last_round
        .members()
        .any(|table| table["state"].as_str() == Some("In Progress"));
    if has_in_progress {
        total - 1
    } else {
        total
    }
}
