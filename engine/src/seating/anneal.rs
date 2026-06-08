//! Simulated-annealing optimization: a multi-restart driver around a single
//! index-based annealing engine.

use super::measure::{
    add_table_to_measure_idx, build_mapping, build_round_idx, clear_table_from_measure_idx,
    measure_round, measure_round_idx, Measure,
};
use super::score::{compute_score, fast_lex_score, SeatingScore};

/// Multi-restart simulated annealing optimization
pub(crate) fn optimize_sa_multi(
    rounds: &mut [Vec<Vec<String>>],
    iterations_per_run: u32,
    restarts: u32,
    fixed_rounds: usize,
    seed: u64,
) -> SeatingScore {
    use rand::prelude::*;
    use rand_chacha::ChaCha8Rng;

    // Master RNG seeded deterministically; each SA run draws its own sub-seed so
    // WASM/PyO3/offline/bot all reproduce the same seating for the same input.
    let mut rng = ChaCha8Rng::seed_from_u64(seed);

    // Keep original state for restarts
    let original_rounds = rounds.to_vec();

    let mut best_rounds = rounds.to_vec();
    let mut best_score = optimize_sa(
        &mut best_rounds,
        iterations_per_run,
        fixed_rounds,
        rng.next_u64(),
    );

    if best_score.is_perfect() {
        for (i, r) in best_rounds.into_iter().enumerate() {
            rounds[i] = r;
        }
        return best_score;
    }

    for _ in 1..restarts {
        // Each restart starts from the pristine input; `optimize_sa` reshuffles
        // the non-fixed rounds itself from its (distinct) sub-seed.
        let mut trial = original_rounds.clone();
        let score = optimize_sa(&mut trial, iterations_per_run, fixed_rounds, rng.next_u64());

        if score.is_better(&best_score) {
            best_score = score.clone();
            best_rounds = trial;
        }

        if score.is_perfect() {
            break;
        }
    }

    // Copy best back
    for (i, r) in best_rounds.into_iter().enumerate() {
        rounds[i] = r;
    }

    best_score
}

/// Simulated annealing optimization (index-based for performance)
pub(crate) fn optimize_sa(
    rounds: &mut [Vec<Vec<String>>],
    iterations: u32,
    fixed_rounds: usize,
    seed: u64,
) -> SeatingScore {
    use rand::prelude::*;
    use rand_chacha::ChaCha8Rng;

    let rounds_count = rounds.len();
    if rounds_count == 0 || fixed_rounds >= rounds_count {
        let mapping = build_mapping(rounds);
        let total_measure = rounds
            .iter()
            .fold(Measure::new(mapping.len()), |mut acc, r| {
                acc.add(&measure_round(&mapping, r));
                acc
            });
        return compute_score(&total_measure, rounds_count);
    }

    // Build mapping and reverse mapping
    let mapping = build_mapping(rounds);
    let n = mapping.len();
    let mut reverse_mapping: Vec<String> = vec![String::new(); n];
    for (name, &idx) in &mapping {
        reverse_mapping[idx] = name.clone();
    }

    let mut rng = ChaCha8Rng::seed_from_u64(seed);

    // Convert rounds to index-based representation for fast swapping
    let mut idx_rounds: Vec<Vec<Vec<usize>>> = rounds
        .iter()
        .map(|r| {
            r.iter()
                .map(|t| t.iter().map(|p| mapping[p]).collect())
                .collect()
        })
        .collect();

    // Shuffle non-fixed rounds
    for round in idx_rounds.iter_mut().skip(fixed_rounds) {
        let mut players: Vec<usize> = round.iter().flatten().copied().collect();
        players.shuffle(&mut rng);
        *round = build_round_idx(&players, n);
    }

    // Compute total measure
    let mut total_measure = Measure::new(n);
    for r in idx_rounds.iter() {
        total_measure.add(&measure_round_idx(r, n));
    }

    let mut best_score = fast_lex_score(&total_measure, rounds_count);
    let mut current_score = best_score.clone();
    let mut best_state: Vec<Vec<Vec<usize>>> = idx_rounds.clone();

    // Annealing parameters
    let temp_max = 1e6_f64;
    let temp_min = 0.001;
    let temp_factor = -(temp_max / temp_min).ln();

    // Build position lookup: round -> [(table_idx, seat_idx), ...]
    let round_positions: Vec<Vec<(usize, usize)>> = idx_rounds
        .iter()
        .map(|r| {
            r.iter()
                .enumerate()
                .flat_map(|(t, table)| (0..table.len()).map(move |s| (t, s)))
                .collect()
        })
        .collect();

    let checkpoint = (iterations / 100).max(1);

    for step in 0..iterations {
        let progress = step as f64 / iterations as f64;
        let base_temperature = temp_max * (temp_factor * progress).exp();

        // Pick random non-fixed round
        let round_idx = rng.gen_range(fixed_rounds..rounds_count);
        let positions = &round_positions[round_idx];
        let player_count = positions.len();

        if player_count < 2 {
            continue;
        }

        // Pick two random positions for swap
        let pos1 = rng.gen_range(0..player_count);
        let pos2 = rng.gen_range(0..player_count);
        if pos1 == pos2 {
            continue;
        }

        let (t1, s1) = positions[pos1];
        let (t2, s2) = positions[pos2];

        // Clear old contribution (1 or 2 tables)
        let round = &idx_rounds[round_idx];
        clear_table_from_measure_idx(&mut total_measure, &round[t1], n);
        if t1 != t2 {
            clear_table_from_measure_idx(&mut total_measure, &round[t2], n);
        }

        // Swap players
        let round = &mut idx_rounds[round_idx];
        let tmp = round[t1][s1];
        round[t1][s1] = round[t2][s2];
        round[t2][s2] = tmp;

        // Add new contribution
        add_table_to_measure_idx(&mut total_measure, &round[t1], n);
        if t1 != t2 {
            add_table_to_measure_idx(&mut total_measure, &round[t2], n);
        }

        let new_score = fast_lex_score(&total_measure, rounds_count);

        // Accept or reject
        let accept = match new_score.cmp(&current_score) {
            std::cmp::Ordering::Less => true,
            std::cmp::Ordering::Equal => true,
            std::cmp::Ordering::Greater => {
                if let Some((rule_idx, diff)) = new_score.first_diff_rule(&current_score) {
                    let rule_temp = base_temperature / (10.0_f64.powi(rule_idx as i32));
                    let accept_prob = (-diff.abs() / rule_temp).exp();
                    rng.gen::<f64>() < accept_prob
                } else {
                    true
                }
            }
        };

        if accept {
            if new_score.is_better(&best_score) {
                best_score = new_score.clone();
                best_state = idx_rounds.clone();
            }
            current_score = new_score;
        } else {
            // Revert: remove NEW, re-swap, add OLD back
            let round = &idx_rounds[round_idx];
            clear_table_from_measure_idx(&mut total_measure, &round[t1], n);
            if t1 != t2 {
                clear_table_from_measure_idx(&mut total_measure, &round[t2], n);
            }

            let round = &mut idx_rounds[round_idx];
            let tmp = round[t1][s1];
            round[t1][s1] = round[t2][s2];
            round[t2][s2] = tmp;

            add_table_to_measure_idx(&mut total_measure, &round[t1], n);
            if t1 != t2 {
                add_table_to_measure_idx(&mut total_measure, &round[t2], n);
            }
        }

        // Checkpoint
        if step > 0 && step % checkpoint == 0 {
            idx_rounds = best_state.clone();
            total_measure = Measure::new(n);
            for r in idx_rounds.iter() {
                total_measure.add(&measure_round_idx(r, n));
            }
            current_score = best_score.clone();

            if best_score.is_perfect() {
                break;
            }
        }
    }

    // Convert best state back to strings
    for (r_idx, r) in best_state.iter().enumerate() {
        for (t_idx, t) in r.iter().enumerate() {
            for (s_idx, &p_idx) in t.iter().enumerate() {
                rounds[r_idx][t_idx][s_idx] = reverse_mapping[p_idx].clone();
            }
        }
    }

    compute_score(&total_measure, rounds_count)
}

/// Get SA parameters (iterations, restarts) based on player count
pub(crate) fn get_sa_params(n: usize) -> (u32, u32) {
    if n <= 15 {
        (80_000, 5)
    } else if n <= 25 {
        (60_000, 3)
    } else if n <= 40 {
        (50_000, 2)
    } else {
        (40_000, 2)
    }
}
