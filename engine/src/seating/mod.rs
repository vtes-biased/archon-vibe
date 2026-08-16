mod anneal;
mod measure;
mod score;
mod stagger;

#[cfg(test)]
mod tests;

pub use score::{
    compute_minimum_violations, compute_player_issues, score_rounds, SeatingIssue, SeatingScore,
};
pub use stagger::select_players_for_round;

use crate::error::EngineError;
use anneal::{get_sa_params, optimize_sa_multi};
use measure::build_round;
use score::score_total;

/// Same uid+round always yields the same seed, so WASM, PyO3, offline replay
/// and the bot compute byte-identical seating without forwarding the result.
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

/// Optimizes up to `rounds_count` total rounds; any `previous_rounds` are kept
/// fixed and only the rounds beyond them are annealed. `seed` is typically
/// `seed_for_round(tournament_uid, round_index)`.
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

    // Awkward counts never reach here in production (StartRound filters via
    // select_players_for_round first); guarded anyway since build_round would panic on them.
    if !stagger::is_valid_table_count(n) {
        return Err(EngineError::internal(format!(
            "{n} players cannot be split into tables of 4-5; \
             filter via select_players_for_round first"
        )));
    }

    let mut rounds = match previous_rounds {
        Some(prev) if !prev.is_empty() => {
            let mut r: Vec<Vec<Vec<String>>> = prev.to_vec();
            let new_rounds_needed = rounds_count.saturating_sub(r.len());
            for _ in 0..new_rounds_needed {
                r.push(build_round(players));
            }
            r
        }
        _ => (0..rounds_count).map(|_| build_round(players)).collect(),
    };

    if rounds.is_empty() {
        return Err(EngineError::internal("Could not build rounds"));
    }

    let fixed = previous_rounds.map(|p| p.len()).unwrap_or(0);

    let (iterations, restarts) = get_sa_params(n);
    optimize_sa_multi(&mut rounds, iterations, restarts, fixed, seed);

    let score = score_total(&rounds);

    Ok((rounds, score))
}

/// Convenience wrapper for adding one round at a time, handling dropouts and
/// late additions; `current_players` may differ from previous rounds' players.
pub fn compute_next_round(
    current_players: &[String],
    previous_rounds: &[Vec<Vec<String>>],
    seed: u64,
) -> Result<(Vec<Vec<String>>, SeatingScore), EngineError> {
    let total_rounds = previous_rounds.len() + 1;
    let (all_rounds, score) =
        compute_seating(current_players, total_rounds, Some(previous_rounds), seed)?;

    let new_round = all_rounds.into_iter().last().ok_or("No rounds generated")?;
    Ok((new_round, score))
}
