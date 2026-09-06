use crate::model::{arg, deck_object, finals_table, player, seat, table, tournament};
use json::JsonValue;

use super::types::{ActorContext, TournamentState};
use crate::error::EngineError;

/// Number of rounds in which `user_uid` is seated. Per-player (not tournament-wide):
/// under open rounds players play different subsets, so this is the player's own round count.
pub(super) fn count_player_rounds_played(tournament: &JsonValue, user_uid: &str) -> usize {
    tournament[tournament::ROUNDS]
        .members()
        .filter(|round| {
            round.members().any(|table| {
                // A soft-cancelled round doesn't count toward the per-player cap.
                table[table::STATE].as_str() != Some("Cancelled")
                    && table[table::SEATING]
                        .members()
                        .any(|seat| seat[seat::PLAYER_UID].as_str() == Some(user_uid))
            })
        })
        .count()
}

/// Every player seated in `round_idx`, the finals being `rounds.len()`.
fn seated_in_round(tournament: &JsonValue, round_idx: usize) -> std::collections::HashSet<String> {
    let rounds = &tournament[tournament::ROUNDS];
    if round_idx >= rounds.len() {
        return tournament[tournament::FINALS][finals_table::SEATING]
            .members()
            .filter_map(|seat| seat[seat::PLAYER_UID].as_str().map(String::from))
            .collect();
    }
    rounds[round_idx]
        .members()
        .filter(|table| table[table::STATE].as_str() != Some("Cancelled"))
        .flat_map(|table| table[table::SEATING].members())
        .filter_map(|seat| seat[seat::PLAYER_UID].as_str().map(String::from))
        .collect()
}

/// Bind each seated player's pending deck to `round_idx`, one deck per player per round.
pub(super) fn stamp_round_decks(
    tournament: &JsonValue,
    decks: &JsonValue,
    deck_ops: &mut JsonValue,
    round_idx: usize,
) {
    if !tournament[tournament::MULTIDECK].as_bool().unwrap_or(false) {
        return;
    }
    let seated = seated_in_round(tournament, round_idx);
    let mut taken: std::collections::HashSet<&str> = decks
        .members()
        .filter(|d| d[deck_object::ROUND].as_usize() == Some(round_idx))
        .filter_map(|d| d[deck_object::USER_UID].as_str())
        .collect();
    for deck in decks.members() {
        if !deck[deck_object::ROUND].is_null() {
            continue;
        }
        let uid = deck[deck_object::USER_UID].as_str().unwrap_or("");
        if !seated.contains(uid) || !taken.insert(uid) {
            continue;
        }
        let _ = deck_ops.push(json::object! {
            arg::OP => "set_round",
            arg::DECK_UID => deck[deck_object::UID].as_str().unwrap_or(""),
            arg::ROUND => round_idx,
        });
    }
}

/// Return the decks stamped at `rounds_removed` to pending.
pub(super) fn release_stamped_decks(
    decks: &JsonValue,
    deck_ops: &mut JsonValue,
    rounds_removed: &[usize],
    player_uid: Option<&str>,
) {
    for deck in decks.members() {
        let Some(round) = deck[deck_object::ROUND].as_usize() else {
            continue;
        };
        if !rounds_removed.contains(&round) {
            continue;
        }
        if let Some(uid) = player_uid {
            if deck[deck_object::USER_UID].as_str() != Some(uid) {
                continue;
            }
        }
        let _ = deck_ops.push(json::object! {
            arg::OP => "set_round",
            arg::DECK_UID => deck[deck_object::UID].as_str().unwrap_or(""),
            arg::ROUND => JsonValue::Null,
        });
    }
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

/// Organizers can correct results anytime rounds exist, not just mid-round.
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
        .any(|p| p[player::USER_UID].as_str() == Some(user_uid))
}

pub(super) fn past_registration_cap(tournament: &JsonValue) -> bool {
    let cap = tournament[tournament::MAX_PLAYERS].as_usize().unwrap_or(0);
    cap > 0
        && tournament[tournament::PLAYERS]
            .members()
            .filter(|p| !p[player::WAITLISTED].as_bool().unwrap_or(false))
            .count()
            >= cap
}

pub(super) fn find_player_index(players: &JsonValue, user_uid: &str) -> Option<usize> {
    players
        .members()
        .position(|p| p[player::USER_UID].as_str() == Some(user_uid))
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
    let rounds = &tournament[tournament::ROUNDS];
    !rounds.is_empty()
        && rounds.members().all(|round| {
            // Cancelled tables are terminal too — a soft-cancelled round is not "in progress".
            round.members().all(|table| {
                matches!(
                    table[table::STATE].as_str(),
                    Some("Finished") | Some("Cancelled")
                )
            })
        })
}

/// Skips `Cancelled` tables — a soft-cancelled round did not really happen, so it
/// must not constrain future seatings (predator/prey).
pub(super) fn collect_previous_rounds(tournament: &JsonValue) -> Vec<Vec<Vec<String>>> {
    tournament[tournament::ROUNDS]
        .members()
        .map(|round| {
            round
                .members()
                .filter(|table| table[table::STATE].as_str() != Some("Cancelled"))
                .map(|table| {
                    table[table::SEATING]
                        .members()
                        .filter_map(|seat| seat[seat::PLAYER_UID].as_str().map(|s| s.to_string()))
                        .collect()
                })
                .collect()
        })
        .collect()
}

/// A round counts only while it has a non-`Cancelled` table. Mirrors the filter in
/// `collect_previous_rounds`, so `rounds.len()` can't be gamed by a voided round.
pub(super) fn count_played_rounds(tournament: &JsonValue) -> usize {
    tournament[tournament::ROUNDS]
        .members()
        .filter(|round| {
            round
                .members()
                .any(|table| table[table::STATE].as_str() != Some("Cancelled"))
        })
        .count()
}

pub(super) fn demote_unseated_players(
    tournament: &mut JsonValue,
    unseated: &std::collections::HashSet<String>,
    round_idx: usize,
) {
    let still_playing = players_in_other_active_rounds(tournament, round_idx);
    let players = &mut tournament[tournament::PLAYERS];
    for i in 0..players.len() {
        let uid = players[i][player::USER_UID].as_str().map(String::from);
        if players[i][player::STATE].as_str() != Some("Playing") {
            continue;
        }
        if let Some(uid) = uid {
            if unseated.contains(&uid) && !still_playing.contains(&uid) {
                players[i][player::STATE] = "Registered".into();
            }
        }
    }
}

pub(super) fn players_in_other_active_rounds(
    tournament: &JsonValue,
    exclude_round: usize,
) -> std::collections::HashSet<String> {
    tournament[tournament::ROUNDS]
        .members()
        .enumerate()
        .filter(|(i, _)| *i != exclude_round)
        .flat_map(|(_, round)| round.members())
        .filter(|table| {
            !matches!(
                table[table::STATE].as_str(),
                Some("Finished") | Some("Cancelled")
            )
        })
        .flat_map(|table| table[table::SEATING].members())
        .filter_map(|seat| seat[seat::PLAYER_UID].as_str().map(|s| s.to_string()))
        .collect()
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

/// The post-finish pass: every deck's `public` follows the tournament, both ways.
pub(super) fn recompute_deck_publication(
    tournament: &JsonValue,
    decks: &JsonValue,
    deck_ops: &mut JsonValue,
) {
    // A deck this event's own ops upserted or deleted already carries its answer;
    // a set_public behind a delete would resurrect the row on the client.
    let touched = |deck: &JsonValue| -> bool {
        deck_ops.members().any(|op| {
            op[arg::PLAYER_UID].as_str() == deck[deck_object::USER_UID].as_str()
                && match op[arg::OP].as_str() {
                    Some("upsert") => {
                        op[arg::DECK][deck_object::ROUND].as_usize()
                            == deck[deck_object::ROUND].as_usize()
                    }
                    Some("delete") => {
                        !op[arg::MULTIDECK].as_bool().unwrap_or(false)
                            || op[arg::DECK_INDEX].as_usize() == deck[deck_object::ROUND].as_usize()
                    }
                    _ => false,
                }
        })
    };
    let changes: Vec<(String, bool)> = decks
        .members()
        .filter(|d| !touched(d))
        .filter_map(|d| {
            let user_uid = d[deck_object::USER_UID].as_str().unwrap_or("");
            let deck_uid = d[deck_object::UID].as_str().unwrap_or("");
            if user_uid.is_empty() || deck_uid.is_empty() {
                return None;
            }
            let is_public = compute_deck_public(tournament, user_uid);
            (d[deck_object::PUBLIC].as_bool().unwrap_or(false) != is_public)
                .then(|| (deck_uid.to_string(), is_public))
        })
        .collect();
    for (deck_uid, public) in changes {
        let _ = deck_ops.push(json::object! {
            arg::OP => "set_public",
            arg::DECK_UID => deck_uid,
            arg::PUBLIC => public,
        });
    }
}

/// A departure takes the player's decks along. Both callers run before any round
/// exists, so every deck of theirs is still pending.
pub(super) fn delete_player_decks(
    tournament: &JsonValue,
    decks: &JsonValue,
    deck_ops: &mut JsonValue,
    user_uid: &str,
) {
    if !decks
        .members()
        .any(|d| d[deck_object::USER_UID].as_str() == Some(user_uid))
    {
        return;
    }
    let _ = deck_ops.push(json::object! {
        arg::OP => "delete",
        arg::PLAYER_UID => user_uid,
        arg::DECK_INDEX => JsonValue::Null,
        arg::MULTIDECK => tournament[tournament::MULTIDECK].as_bool().unwrap_or(false),
    });
}
