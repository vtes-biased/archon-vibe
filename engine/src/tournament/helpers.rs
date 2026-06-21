//! Helper functions for tournament event processing.

use json::JsonValue;

use super::types::{ActorContext, TournamentState};
use crate::error::EngineError;

/// Number of rounds in which `user_uid` is seated. Per-player (not tournament-wide):
/// under open rounds players play different subsets, so this is the player's own round count.
pub(super) fn count_player_rounds_played(tournament: &JsonValue, user_uid: &str) -> usize {
    tournament["rounds"]
        .members()
        .filter(|round| {
            round.members().any(|table| {
                table["seating"]
                    .members()
                    .any(|seat| seat["player_uid"].as_str() == Some(user_uid))
            })
        })
        .count()
}

/// Returns true if a player's deck slot is locked (its round has already started for them).
/// Indexed per-player: deck slot `i` is the deck for the player's `i`-th round.
pub(super) fn is_deck_locked(tournament: &JsonValue, user_uid: &str, deck_index: usize) -> bool {
    deck_index < count_player_rounds_played(tournament, user_uid)
}

pub(super) fn require_organizer(actor: &ActorContext) -> Result<(), EngineError> {
    if !actor.is_organizer {
        return Err(EngineError::NotOrganizer);
    }
    Ok(())
}

pub(super) fn require_state(
    current: TournamentState,
    expected: TournamentState,
) -> Result<(), EngineError> {
    if current != expected {
        return Err(EngineError::WrongState {
            expected: expected.as_str().to_string(),
            current: current.as_str().to_string(),
        });
    }
    Ok(())
}

pub(super) fn require_state_or_finished(
    current: TournamentState,
    expected: TournamentState,
) -> Result<(), EngineError> {
    if current != expected && current != TournamentState::Finished {
        return Err(EngineError::WrongState {
            expected: expected.as_str().to_string(),
            current: current.as_str().to_string(),
        });
    }
    Ok(())
}

/// Gate for result-correction events (SetScore/Override/Unoverride). A player may
/// only score while a round is live (`Playing`); an organizer may also correct any
/// round between rounds (`Waiting`) or after the tournament has finished
/// (`Finished`) — they must be able to fix a result at any time, not just mid-round.
pub(super) fn require_can_edit_results(
    actor: &ActorContext,
    current: TournamentState,
) -> Result<(), EngineError> {
    let allowed = match current {
        TournamentState::Playing => true,
        TournamentState::Waiting | TournamentState::Finished => actor.is_organizer,
        _ => false,
    };
    if !allowed {
        return Err(EngineError::WrongState {
            expected: TournamentState::Playing.as_str().to_string(),
            current: current.as_str().to_string(),
        });
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

pub(super) fn validate_enum(value: &str, valid: &[&str], field: &str) -> Result<(), EngineError> {
    if !valid.contains(&value) {
        return Err(EngineError::internal(format!(
            "Invalid {}: {}",
            field, value
        )));
    }
    Ok(())
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
