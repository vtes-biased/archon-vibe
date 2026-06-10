//! VEKN Tournament Seating Algorithm
//!
//! Official seating priorities:
//! https://groups.google.com/g/rec.games.trading-cards.jyhad/c/4YivYLDVYQc/m/CCH-ZBU5UiUJ
//!
//! Layered into submodules:
//! - [`measure`]: the N×N×8 relationship matrix and round/table primitives
//! - [`score`]: lexicographic / detailed scoring, per-player issues, minimums
//! - [`anneal`]: multi-restart simulated annealing
//! - [`precomputed`]: exhaustive-search optimal seatings for ≤25 players
//! - [`stagger`]: awkward player counts (6, 7, 11)

mod anneal;
mod measure;
mod precomputed;
mod score;
mod stagger;

#[cfg(test)]
mod tests;

// Public API — the only seating items external code should depend on
// (plus `compute_seating` / `compute_next_round` / `seed_for_round` defined below).
pub use score::{
    compute_minimum_violations, compute_player_issues, score_rounds, SeatingIssue, SeatingScore,
};
pub use stagger::select_players_for_round;

// Internal plumbing for this module's own entry points (not public API).
use crate::error::EngineError;
use anneal::{get_sa_params, optimize_sa_multi};
use measure::build_round;
use precomputed::{apply_precomputed, get_precomputed_seating};
use score::score_total;
use stagger::get_staggered_rounds;

/// Derive a deterministic PRNG seed for a round's seating from the tournament
/// uid and the (0-based) round index. The same uid+round always yields the same
/// seed, so seating computed in the browser (WASM), the backend (PyO3), offline
/// replay, and the bot all agree without forwarding the result.
pub fn seed_for_round(tournament_uid: &str, round_index: usize) -> u64 {
    // FNV-1a over the uid, then mix in the round index via an LCG step.
    let base = tournament_uid
        .bytes()
        .fold(0xcbf2_9ce4_8422_2325u64, |acc, b| {
            (acc ^ b as u64).wrapping_mul(0x0000_0100_0000_01b3)
        });
    base.wrapping_mul(6364136223846793005)
        .wrapping_add(round_index as u64)
        .wrapping_add(1)
}

/// `compute_seating` result: (rounds → tables → seats) plus the seating's score.
type SeatingResult = Result<(Vec<Vec<Vec<String>>>, SeatingScore), EngineError>;

/// Compute seating for a tournament.
///
/// # Arguments
/// * `players` - List of player names/IDs for this computation
/// * `rounds_count` - Total number of rounds to compute
/// * `previous_rounds` - Optional previous rounds (for successive computation)
///
/// # Returns
/// * All rounds (including previous) with optimized seating
/// * Score indicating quality of the seating
///
/// # Usage patterns
///
/// Fresh tournament (no dropouts):
///     `compute_seating(&players, 3, None, seed)`
///
/// Adding a round after dropouts/additions:
///     `compute_seating(&current_players, 2, Some(&[round1]), seed)`
///
/// Adding round 4+ to existing tournament:
///     `compute_seating(&players, 4, Some(&prev_rounds), seed)`
///
/// `seed` is typically `seed_for_round(tournament_uid, round_index)`.
#[allow(clippy::type_complexity)]
pub fn compute_seating(
    players: &[String],
    rounds_count: usize,
    previous_rounds: Option<&[Vec<Vec<String>>]>,
    seed: u64,
) -> SeatingResult {
    if players.len() < 4 {
        return Err(EngineError::SeatingMinPlayers);
    }

    if rounds_count == 0 {
        return Err(EngineError::SeatingMinRounds);
    }

    let n = players.len();
    let has_previous = previous_rounds.map(|p| !p.is_empty()).unwrap_or(false);

    // Use precomputed optimal seatings when applicable:
    // - No previous rounds (fresh tournament, same players throughout)
    // - Exactly 3 rounds
    // - Player count has precomputed solution (4-25, excluding 6,7,11)
    if !has_previous && rounds_count == 3 {
        if let Some(precomputed) = get_precomputed_seating(n) {
            let rounds = apply_precomputed(players, &precomputed);
            let score = score_total(&rounds);
            return Ok((rounds, score));
        }
    }

    // Build initial rounds
    let mut rounds = match previous_rounds {
        Some(prev) if !prev.is_empty() => {
            // Start with previous rounds, add new ones
            let mut r: Vec<Vec<Vec<String>>> = prev.to_vec();
            let new_rounds_needed = rounds_count.saturating_sub(r.len());
            for _ in 0..new_rounds_needed {
                r.push(build_round(players));
            }
            r
        }
        _ => {
            // Check for staggered rounds
            if [6, 7, 11].contains(&n) {
                get_staggered_rounds(players, rounds_count)
            } else {
                (0..rounds_count).map(|_| build_round(players)).collect()
            }
        }
    };

    if rounds.is_empty() {
        return Err(EngineError::internal("Could not build rounds"));
    }

    // Determine fixed rounds (previous rounds are fixed)
    let fixed = previous_rounds.map(|p| p.len()).unwrap_or(0);

    // Simulated annealing parameters based on tournament size
    let (iterations, restarts) = get_sa_params(n);
    optimize_sa_multi(&mut rounds, iterations, restarts, fixed, seed);

    // Compute final score
    let score = score_total(&rounds);

    Ok((rounds, score))
}

/// Compute the next round for an ongoing tournament.
///
/// This is a convenience function for the common case of adding one round
/// at a time, handling dropouts and late additions.
///
/// # Arguments
/// * `current_players` - Players for the next round (may differ from previous)
/// * `previous_rounds` - All previous rounds played
///
/// # Returns
/// * The new round seating
/// * Score for the complete tournament so far
pub fn compute_next_round(
    current_players: &[String],
    previous_rounds: &[Vec<Vec<String>>],
    seed: u64,
) -> Result<(Vec<Vec<String>>, SeatingScore), EngineError> {
    let total_rounds = previous_rounds.len() + 1;
    let (all_rounds, score) =
        compute_seating(current_players, total_rounds, Some(previous_rounds), seed)?;

    // Return only the new round
    let new_round = all_rounds.into_iter().last().ok_or("No rounds generated")?;
    Ok((new_round, score))
}
