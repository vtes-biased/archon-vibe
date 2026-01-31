//! VEKN Tournament Seating Algorithm
//!
//! Official seating priorities:
//! https://groups.google.com/g/rec.games.trading-cards.jyhad/c/4YivYLDVYQc/m/CCH-ZBU5UiUJ

use std::collections::HashMap;

// Rule order (strict lexicographic priority, R1 is highest priority)
// R1: predator-prey repeat (hard)
// R2: opponent on all rounds (hard)
// R3: VP distribution (stddev)
// R4: opponent twice
// R5: fifth seat twice
// R6: same relative position
// R7: same seat position
// R8: transfers distribution (stddev)
// R9: same position group

/// Lexicographic score - array of 9 rule violation counts
/// Compare using `cmp_lex` for strict priority ordering
#[derive(Clone, Debug, PartialEq)]
pub struct LexScore(pub [f64; 9]);

impl LexScore {
    /// Compare two scores lexicographically
    /// Returns Ordering::Less if self is better (lower violations)
    pub fn cmp(&self, other: &LexScore) -> std::cmp::Ordering {
        for i in 0..9 {
            if self.0[i] < other.0[i] {
                return std::cmp::Ordering::Less;
            }
            if self.0[i] > other.0[i] {
                return std::cmp::Ordering::Greater;
            }
        }
        std::cmp::Ordering::Equal
    }

    /// Check if self is strictly better than other
    pub fn is_better(&self, other: &LexScore) -> bool {
        self.cmp(other) == std::cmp::Ordering::Less
    }

    /// Get the first rule where scores differ (for temperature-based acceptance)
    pub fn first_diff_rule(&self, other: &LexScore) -> Option<(usize, f64)> {
        for i in 0..9 {
            let diff = self.0[i] - other.0[i];
            if diff.abs() > 1e-10 {
                return Some((i, diff));
            }
        }
        None
    }

    /// Check if all rules are zero (perfect score)
    pub fn is_perfect(&self) -> bool {
        self.0.iter().all(|&x| x < 1e-10)
    }
}

// Measurement vectors for opponent relationships at 4-player tables
// Format: [opponent, prey, grand_prey, grand_pred, pred, cross, neighbour, non_neighbour]
const OPPONENTS_4: [[i32; 8]; 3] = [
    [1, 1, 0, 0, 0, 0, 1, 0], // position 1: prey (neighbour)
    [1, 0, 0, 0, 0, 1, 0, 1], // position 2: cross-table (non-neighbour)
    [1, 0, 0, 0, 1, 0, 1, 0], // position 3: predator (neighbour)
];

// Measurement vectors for opponent relationships at 5-player tables
const OPPONENTS_5: [[i32; 8]; 4] = [
    [1, 1, 0, 0, 0, 0, 1, 0], // position 1: prey (neighbour)
    [1, 0, 1, 0, 0, 0, 0, 1], // position 2: grand-prey (non-neighbour)
    [1, 0, 0, 1, 0, 0, 0, 1], // position 3: grand-predator (non-neighbour)
    [1, 0, 0, 0, 1, 0, 1, 0], // position 4: predator (neighbour)
];

// Position vectors: [played, vps, transfers, seat1, seat2, seat3, seat4, seat5]
const POSITIONS_4: [[i32; 8]; 4] = [
    [1, 4, 1, 1, 0, 0, 0, 0],
    [1, 4, 2, 0, 1, 0, 0, 0],
    [1, 4, 3, 0, 0, 1, 0, 0],
    [1, 4, 4, 0, 0, 0, 1, 0],
];

const POSITIONS_5: [[i32; 8]; 5] = [
    [1, 5, 1, 1, 0, 0, 0, 0],
    [1, 5, 2, 0, 1, 0, 0, 0],
    [1, 5, 3, 0, 0, 1, 0, 0],
    [1, 5, 4, 0, 0, 0, 1, 0],
    [1, 5, 4, 0, 0, 0, 0, 1],
];

/// 3D measurement matrix (N × N × 8)
/// Diagonal [i][i] stores position info, off-diagonal stores relationships
#[derive(Clone)]
pub struct Measure {
    n: usize,
    data: Vec<i32>, // Flattened: [i * n * 8 + j * 8 + k]
}

impl Measure {
    pub fn new(n: usize) -> Self {
        Measure {
            n,
            data: vec![0; n * n * 8],
        }
    }

    #[inline]
    fn idx(&self, i: usize, j: usize, k: usize) -> usize {
        i * self.n * 8 + j * 8 + k
    }

    #[inline]
    pub fn get(&self, i: usize, j: usize, k: usize) -> i32 {
        self.data[self.idx(i, j, k)]
    }

    #[inline]
    pub fn set(&self, i: usize, j: usize, k: usize) -> i32 {
        self.data[self.idx(i, j, k)]
    }

    #[inline]
    pub fn add_vec(&mut self, i: usize, j: usize, vec: &[i32; 8]) {
        let base = self.idx(i, j, 0);
        for k in 0..8 {
            self.data[base + k] += vec[k];
        }
    }

    #[inline]
    pub fn sub_vec(&mut self, i: usize, j: usize, vec: &[i32; 8]) {
        let base = self.idx(i, j, 0);
        for k in 0..8 {
            self.data[base + k] -= vec[k];
        }
    }

    #[inline]
    pub fn set_vec(&mut self, i: usize, j: usize, vec: &[i32; 8]) {
        let base = self.idx(i, j, 0);
        for k in 0..8 {
            self.data[base + k] = vec[k];
        }
    }

    #[inline]
    pub fn clear_row(&mut self, i: usize, j: usize) {
        let base = self.idx(i, j, 0);
        for k in 0..8 {
            self.data[base + k] = 0;
        }
    }

    pub fn add(&mut self, other: &Measure) {
        for i in 0..self.data.len() {
            self.data[i] += other.data[i];
        }
    }

    pub fn sub(&mut self, other: &Measure) {
        for i in 0..self.data.len() {
            self.data[i] -= other.data[i];
        }
    }
}

/// Scoring result with detailed rule violations
#[derive(Clone, Debug)]
pub struct SeatingScore {
    pub rules: [f64; 9],
    pub mean_vps: f64,
    pub mean_transfers: f64,
}

impl SeatingScore {
    pub fn to_json(&self) -> json::JsonValue {
        json::object! {
            rules: self.rules.iter().map(|&x| x.into()).collect::<Vec<json::JsonValue>>(),
            mean_vps: self.mean_vps,
            mean_transfers: self.mean_transfers,
        }
    }

    pub fn from_lex(lex: &LexScore, mean_vps: f64, mean_transfers: f64) -> Self {
        SeatingScore {
            rules: lex.0,
            mean_vps,
            mean_transfers,
        }
    }

    /// Check if self is strictly better than other (lexicographically)
    pub fn is_better(&self, other: &SeatingScore) -> bool {
        for i in 0..9 {
            if self.rules[i] < other.rules[i] {
                return true;
            }
            if self.rules[i] > other.rules[i] {
                return false;
            }
        }
        false
    }

    /// Check if all rules are zero (perfect score)
    pub fn is_perfect(&self) -> bool {
        self.rules.iter().all(|&x| x < 1e-10)
    }
}

/// Build player name to index mapping
pub fn build_mapping(rounds: &[Vec<Vec<String>>]) -> HashMap<String, usize> {
    let mut mapping = HashMap::new();
    let mut idx = 0;
    for round in rounds {
        for table in round {
            for player in table {
                if !mapping.contains_key(player) {
                    mapping.insert(player.clone(), idx);
                    idx += 1;
                }
            }
        }
    }
    mapping
}

/// Measure a single round (optionally only specific tables via hints)
pub fn measure_round(mapping: &HashMap<String, usize>, round: &[Vec<String>]) -> Measure {
    measure_round_with_hints(mapping, round, None)
}

/// Measure a round with optional hints for which tables to process
pub fn measure_round_with_hints(
    mapping: &HashMap<String, usize>,
    round: &[Vec<String>],
    hints: Option<&[usize]>,
) -> Measure {
    let n = mapping.len();
    let mut m = Measure::new(n);

    for (table_idx, table) in round.iter().enumerate() {
        // Skip tables not in hints
        if let Some(h) = hints {
            if !h.contains(&table_idx) {
                continue;
            }
        }

        let table_size = table.len();
        if table_size < 4 || table_size > 5 {
            continue;
        }

        let positions = if table_size == 4 {
            &POSITIONS_4[..]
        } else {
            &POSITIONS_5[..]
        };
        let opponents = if table_size == 4 {
            &OPPONENTS_4[..]
        } else {
            &OPPONENTS_5[..]
        };

        for (seat, player) in table.iter().enumerate() {
            let i = mapping[player];
            // Set position on diagonal
            m.set_vec(i, i, &positions[seat]);

            // Set opponent relationships
            for rel in 0..table_size - 1 {
                let opp_seat = (seat + rel + 1) % table_size;
                let opp_idx = mapping[&table[opp_seat]];
                m.add_vec(i, opp_idx, &opponents[rel]);
            }
        }
    }
    m
}


/// Compute lexicographic score for optimization
pub fn fast_lex_score(measure: &Measure, rounds_count: usize) -> LexScore {
    let n = measure.n;
    let mut playing_count = 0;
    let mut vps_sum = 0.0;
    let mut transfers_sum = 0.0;
    let mut vps_list = Vec::with_capacity(n);
    let mut transfers_list = Vec::with_capacity(n);

    // Collect position data from diagonal
    for i in 0..n {
        let played = measure.get(i, i, 0);
        if played > 0 {
            let vps = measure.get(i, i, 1) as f64 / played as f64;
            let transfers = measure.get(i, i, 2) as f64 / played as f64;
            vps_sum += vps;
            transfers_sum += transfers;
            vps_list.push(vps);
            transfers_list.push(transfers);
            playing_count += 1;
        }
    }

    if playing_count == 0 {
        return LexScore([0.0; 9]);
    }

    let mean_vps = vps_sum / playing_count as f64;
    let mean_transfers = transfers_sum / playing_count as f64;

    // R3: VP stddev
    let vps_variance: f64 = vps_list.iter().map(|v| (v - mean_vps).powi(2)).sum::<f64>()
        / playing_count as f64;
    let r3 = vps_variance.sqrt();

    // R8: Transfers stddev
    let transfers_variance: f64 = transfers_list
        .iter()
        .map(|t| (t - mean_transfers).powi(2))
        .sum::<f64>()
        / playing_count as f64;
    let r8 = transfers_variance.sqrt();

    // Count violations from position data
    let mut r5 = 0.0; // Fifth seat twice
    let mut r7 = 0.0; // Same seat twice

    for i in 0..n {
        for seat in 3..8 {
            let count = measure.get(i, i, seat);
            if count > 1 {
                r7 += 1.0;
                if seat == 7 {
                    // Fifth seat
                    r5 += 1.0;
                }
            }
        }
    }

    // Count violations from opponent relationships
    let mut r1 = 0.0; // Predator-prey repeat
    let mut r2 = 0.0; // Opponent all rounds
    let mut r4 = 0.0; // Opponent twice
    let mut r6 = 0.0; // Same position twice
    let mut r9 = 0.0; // Same position group twice

    for i in 0..n {
        for j in 0..i {
            let opponent_count = measure.get(i, j, 0);
            if opponent_count > 1 {
                r4 += 1.0;
                if opponent_count >= rounds_count as i32 {
                    r2 += 1.0;
                }

                // Check specific relationships (prey, grand-prey, grand-pred, pred, cross)
                for k in 1..6 {
                    if measure.get(i, j, k) > 1 {
                        r6 += 1.0;
                        if k == 1 || k == 4 {
                            // Prey or predator
                            r1 += 1.0;
                        }
                    }
                }

                // Check position groups (neighbour, non-neighbour)
                for k in 6..8 {
                    if measure.get(i, j, k) > 1 {
                        r9 += 1.0;
                    }
                }
            }
        }
    }

    LexScore([r1, r2, r3, r4, r5, r6, r7, r8, r9])
}

/// Compute detailed score
pub fn compute_score(measure: &Measure, rounds_count: usize) -> SeatingScore {
    let n = measure.n;
    let mut playing_count = 0;
    let mut vps_sum = 0.0;
    let mut transfers_sum = 0.0;
    let mut vps_list = Vec::with_capacity(n);
    let mut transfers_list = Vec::with_capacity(n);

    for i in 0..n {
        let played = measure.get(i, i, 0);
        if played > 0 {
            let vps = measure.get(i, i, 1) as f64 / played as f64;
            let transfers = measure.get(i, i, 2) as f64 / played as f64;
            vps_sum += vps;
            transfers_sum += transfers;
            vps_list.push(vps);
            transfers_list.push(transfers);
            playing_count += 1;
        }
    }

    let mean_vps = if playing_count > 0 {
        vps_sum / playing_count as f64
    } else {
        0.0
    };
    let mean_transfers = if playing_count > 0 {
        transfers_sum / playing_count as f64
    } else {
        0.0
    };

    let r3 = if playing_count > 0 {
        (vps_list.iter().map(|v| (v - mean_vps).powi(2)).sum::<f64>() / playing_count as f64)
            .sqrt()
    } else {
        0.0
    };

    let r8 = if playing_count > 0 {
        (transfers_list
            .iter()
            .map(|t| (t - mean_transfers).powi(2))
            .sum::<f64>()
            / playing_count as f64)
            .sqrt()
    } else {
        0.0
    };

    let mut r5 = 0.0;
    let mut r7 = 0.0;
    for i in 0..n {
        for seat in 3..8 {
            let count = measure.get(i, i, seat);
            if count > 1 {
                r7 += 1.0;
                if seat == 7 {
                    r5 += 1.0;
                }
            }
        }
    }

    let mut r1 = 0.0;
    let mut r2 = 0.0;
    let mut r4 = 0.0;
    let mut r6 = 0.0;
    let mut r9 = 0.0;

    for i in 0..n {
        for j in 0..i {
            let opponent_count = measure.get(i, j, 0);
            if opponent_count > 1 {
                r4 += 1.0;
                if opponent_count >= rounds_count as i32 {
                    r2 += 1.0;
                }
                for k in 1..6 {
                    if measure.get(i, j, k) > 1 {
                        r6 += 1.0;
                        if k == 1 || k == 4 {
                            r1 += 1.0;
                        }
                    }
                }
                for k in 6..8 {
                    if measure.get(i, j, k) > 1 {
                        r9 += 1.0;
                    }
                }
            }
        }
    }

    SeatingScore {
        rules: [r1, r2, r3, r4, r5, r6, r7, r8, r9],
        mean_vps,
        mean_transfers,
    }
}

/// Build default round structure from players
pub fn build_round(players: &[String]) -> Vec<Vec<String>> {
    let count = players.len();
    if count < 4 {
        return vec![];
    }

    // Calculate table sizes: prefer 5-player tables, use 4-player to fill
    // Python: fours = 5 - (length % 5 or 5)
    let remainder = count % 5;
    let divisor = if remainder == 0 { 5 } else { remainder };
    let fours = 5 - divisor;
    let fives_count = (count - 4 * fours) / 5;

    let mut tables = Vec::new();
    let mut idx = 0;

    // 5-player tables first
    for _ in 0..fives_count {
        tables.push(players[idx..idx + 5].to_vec());
        idx += 5;
    }

    // 4-player tables
    for _ in 0..fours {
        if idx + 4 <= count {
            tables.push(players[idx..idx + 4].to_vec());
            idx += 4;
        }
    }

    tables
}

/// Multi-restart simulated annealing optimization
pub fn optimize_sa_multi(
    rounds: &mut [Vec<Vec<String>>],
    iterations_per_run: u32,
    restarts: u32,
    fixed_rounds: usize,
) -> SeatingScore {
    use rand::prelude::*;

    // Keep original state for restarts
    let original_rounds = rounds.to_vec();

    let mut best_rounds = rounds.to_vec();
    let mut best_score = optimize_sa(&mut best_rounds, iterations_per_run, fixed_rounds);

    if best_score.is_perfect() {
        for (i, r) in best_rounds.into_iter().enumerate() {
            rounds[i] = r;
        }
        return best_score;
    }

    let mut rng = rand::thread_rng();

    for _ in 1..restarts {
        // Re-shuffle non-fixed rounds from original state
        let mut trial = original_rounds.clone();
        for r in trial.iter_mut().skip(fixed_rounds) {
            let mut players: Vec<String> = r.iter().flatten().cloned().collect();
            players.shuffle(&mut rng);
            *r = build_round(&players);
        }

        let score = optimize_sa(&mut trial, iterations_per_run, fixed_rounds);

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
pub fn optimize_sa(
    rounds: &mut [Vec<Vec<String>>],
    iterations: u32,
    fixed_rounds: usize,
) -> SeatingScore {
    use rand::prelude::*;

    let rounds_count = rounds.len();
    if rounds_count == 0 || fixed_rounds >= rounds_count {
        let mapping = build_mapping(rounds);
        let total_measure = rounds.iter().fold(Measure::new(mapping.len()), |mut acc, r| {
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

    let mut rng = rand::thread_rng();

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

/// Build round from player indices
fn build_round_idx(players: &[usize], _n: usize) -> Vec<Vec<usize>> {
    let count = players.len();
    if count < 4 {
        return vec![];
    }
    let remainder = count % 5;
    let divisor = if remainder == 0 { 5 } else { remainder };
    let fours = 5 - divisor;
    let fives_count = (count - 4 * fours) / 5;

    let mut tables = Vec::with_capacity(fives_count + fours);
    let mut idx = 0;

    for _ in 0..fives_count {
        tables.push(players[idx..idx + 5].to_vec());
        idx += 5;
    }
    for _ in 0..fours {
        if idx + 4 <= count {
            tables.push(players[idx..idx + 4].to_vec());
            idx += 4;
        }
    }
    tables
}

/// Measure a round using indices
fn measure_round_idx(round: &[Vec<usize>], n: usize) -> Measure {
    let mut m = Measure::new(n);
    for table in round {
        add_table_to_measure_idx(&mut m, table, n);
    }
    m
}

/// Add a single table's contribution to measure
#[inline]
fn add_table_to_measure_idx(measure: &mut Measure, table: &[usize], _n: usize) {
    let table_size = table.len();
    match table_size {
        4 => {
            for (seat, &player) in table.iter().enumerate() {
                measure.add_vec(player, player, &POSITIONS_4[seat]);
                for rel in 0..3 {
                    let opp = table[(seat + rel + 1) % 4];
                    measure.add_vec(player, opp, &OPPONENTS_4[rel]);
                }
            }
        }
        5 => {
            for (seat, &player) in table.iter().enumerate() {
                measure.add_vec(player, player, &POSITIONS_5[seat]);
                for rel in 0..4 {
                    let opp = table[(seat + rel + 1) % 5];
                    measure.add_vec(player, opp, &OPPONENTS_5[rel]);
                }
            }
        }
        _ => {}
    }
}

/// Remove a single table's contribution from measure
#[inline]
fn clear_table_from_measure_idx(measure: &mut Measure, table: &[usize], _n: usize) {
    let table_size = table.len();
    match table_size {
        4 => {
            for (seat, &player) in table.iter().enumerate() {
                measure.sub_vec(player, player, &POSITIONS_4[seat]);
                for rel in 0..3 {
                    let opp = table[(seat + rel + 1) % 4];
                    measure.sub_vec(player, opp, &OPPONENTS_4[rel]);
                }
            }
        }
        5 => {
            for (seat, &player) in table.iter().enumerate() {
                measure.sub_vec(player, player, &POSITIONS_5[seat]);
                for rel in 0..4 {
                    let opp = table[(seat + rel + 1) % 5];
                    measure.sub_vec(player, opp, &OPPONENTS_5[rel]);
                }
            }
        }
        _ => {}
    }
}

/// Get initial rounds for staggered player counts (6, 7, 11)
pub fn get_staggered_rounds(players: &[String], rounds_count: usize) -> Vec<Vec<Vec<String>>> {
    let players_count = players.len();

    if players_count < 4 {
        return vec![];
    }

    if ![6, 7, 11].contains(&players_count) {
        return (0..rounds_count)
            .map(|_| build_round(players))
            .collect();
    }

    if rounds_count < 2 {
        return vec![];
    }

    // For 6, 7, 11 players, some must sit out each round
    let possible_outs: Vec<usize> = [4, 5, 8, 9, 10]
        .iter()
        .filter(|&&i| players_count > i)
        .map(|&i| players_count - i)
        .rev()
        .collect();

    if possible_outs.is_empty() {
        return (0..rounds_count)
            .map(|_| build_round(players))
            .collect();
    }

    // Calculate additional rounds needed
    let mut additional_rounds = 1;
    while possible_outs[0] * (rounds_count + additional_rounds) > players_count * additional_rounds
    {
        additional_rounds += 1;
    }

    let total_rounds = rounds_count + additional_rounds;
    let mut excludes = players_count * additional_rounds;

    // Compute exclusions per round
    let mut out: Vec<usize> = Vec::new();
    while excludes > 0 {
        let mut i = 0;
        while (total_rounds - out.len()) * possible_outs[i] < excludes {
            i += 1;
        }
        while i > 0 && excludes > possible_outs[i] && excludes - possible_outs[i] < possible_outs[0] {
            i -= 1;
        }
        out.push(possible_outs[i]);
        excludes -= possible_outs[i];
    }

    // Build exclusion list
    let exclusions: Vec<usize> = (0..total_rounds)
        .flat_map(|r| vec![r; out.get(r).copied().unwrap_or(0)])
        .collect();

    // Build rounds with exclusions
    (0..total_rounds)
        .map(|r| {
            let playing: Vec<String> = (0..players_count)
                .filter(|&p| {
                    !(0..additional_rounds).any(|c| {
                        let exc_idx = p + players_count * c;
                        exc_idx < exclusions.len() && exclusions[exc_idx] == r
                    })
                })
                .map(|p| players[p].clone())
                .collect();
            build_round(&playing)
        })
        .collect()
}

// ========================================================================
// PRECOMPUTED OPTIMAL SEATINGS
// ========================================================================
// For ≤25 players with no dropouts/additions, we use precomputed optimal
// seatings from exhaustive search. Player indices are 0-based.

fn get_precomputed_seating(n: usize) -> Option<Vec<Vec<Vec<usize>>>> {
    match n {
        4 => Some(vec![
            vec![vec![0, 1, 2, 3]],
            vec![vec![2, 0, 3, 1]],
            vec![vec![1, 3, 0, 2]],
        ]),
        5 => Some(vec![
            vec![vec![0, 1, 2, 3, 4]],
            vec![vec![3, 0, 2, 4, 1]],
            vec![vec![1, 4, 2, 0, 3]],
        ]),
        8 => Some(vec![
            vec![vec![0, 1, 2, 3], vec![4, 5, 6, 7]],
            vec![vec![1, 3, 4, 6], vec![2, 7, 5, 0]],
            vec![vec![6, 0, 7, 1], vec![5, 4, 3, 2]],
        ]),
        9 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8]],
            vec![vec![8, 0, 4, 1, 6], vec![3, 2, 5, 7]],
            vec![vec![6, 3, 1, 5, 0], vec![7, 4, 8, 2]],
        ]),
        10 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8, 9]],
            vec![vec![2, 0, 9, 6, 5], vec![4, 7, 3, 1, 8]],
            vec![vec![9, 3, 0, 5, 7], vec![6, 8, 1, 4, 2]],
        ]),
        12 => Some(vec![
            vec![vec![0, 1, 2, 3], vec![4, 5, 6, 7], vec![8, 9, 10, 11]],
            vec![vec![5, 11, 3, 8], vec![10, 0, 4, 6], vec![7, 2, 9, 1]],
            vec![vec![9, 3, 1, 4], vec![2, 6, 8, 10], vec![11, 7, 5, 0]],
        ]),
        13 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8], vec![9, 10, 11, 12]],
            vec![vec![11, 9, 0, 5, 7], vec![10, 3, 1, 6], vec![12, 4, 8, 2]],
            vec![vec![8, 12, 6, 0, 10], vec![4, 5, 9, 1], vec![2, 7, 3, 11]],
        ]),
        14 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8, 9], vec![10, 11, 12, 13]],
            vec![vec![7, 13, 6, 2, 10], vec![11, 4, 9, 12, 3], vec![8, 5, 1, 0]],
            vec![vec![12, 10, 8, 1, 7], vec![3, 0, 13, 11, 5], vec![9, 2, 4, 6]],
        ]),
        15 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8, 9], vec![10, 11, 12, 13, 14]],
            vec![vec![8, 14, 1, 10, 5], vec![12, 4, 11, 9, 0], vec![13, 3, 6, 2, 7]],
            vec![vec![4, 2, 14, 12, 8], vec![7, 5, 0, 11, 13], vec![9, 10, 3, 1, 6]],
        ]),
        16 => Some(vec![
            vec![vec![0, 1, 2, 3], vec![4, 5, 6, 7], vec![8, 9, 10, 11], vec![12, 13, 14, 15]],
            vec![vec![3, 7, 9, 14], vec![11, 6, 12, 0], vec![1, 4, 13, 8], vec![2, 15, 5, 10]],
            vec![vec![13, 11, 7, 2], vec![5, 8, 3, 12], vec![9, 0, 15, 4], vec![10, 14, 1, 6]],
        ]),
        17 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8], vec![9, 10, 11, 12], vec![13, 14, 15, 16]],
            vec![vec![6, 5, 12, 10, 15], vec![16, 2, 8, 1], vec![7, 9, 14, 0], vec![4, 13, 3, 11]],
            vec![vec![11, 8, 16, 14, 7], vec![2, 0, 10, 13], vec![3, 15, 5, 9], vec![12, 4, 1, 6]],
        ]),
        18 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8, 9], vec![10, 11, 12, 13], vec![14, 15, 16, 17]],
            vec![vec![15, 13, 11, 5, 2], vec![4, 9, 17, 12, 14], vec![1, 16, 8, 6], vec![3, 0, 10, 7]],
            vec![vec![6, 17, 3, 11, 16], vec![13, 7, 14, 10, 1], vec![9, 12, 5, 0], vec![8, 2, 4, 15]],
        ]),
        19 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8, 9], vec![10, 11, 12, 13, 14], vec![15, 16, 17, 18]],
            vec![vec![4, 18, 6, 17, 12], vec![7, 10, 16, 2, 0], vec![8, 13, 9, 15, 1], vec![3, 5, 14, 11]],
            vec![vec![17, 3, 1, 10, 5], vec![14, 9, 18, 0, 15], vec![11, 8, 4, 16, 7], vec![12, 2, 13, 6]],
        ]),
        20 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8, 9], vec![10, 11, 12, 13, 14], vec![15, 16, 17, 18, 19]],
            vec![vec![9, 0, 18, 1, 12], vec![16, 14, 15, 7, 3], vec![13, 17, 6, 2, 11], vec![19, 4, 8, 5, 10]],
            vec![vec![7, 18, 4, 10, 13], vec![1, 5, 14, 6, 16], vec![2, 12, 19, 9, 15], vec![3, 8, 11, 17, 0]],
        ]),
        21 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8], vec![9, 10, 11, 12], vec![13, 14, 15, 16], vec![17, 18, 19, 20]],
            vec![vec![7, 15, 9, 14, 19], vec![4, 17, 8, 11], vec![12, 20, 16, 0], vec![18, 3, 5, 2], vec![10, 13, 6, 1]],
            vec![vec![20, 8, 10, 5, 13], vec![19, 16, 3, 9], vec![11, 2, 0, 7], vec![14, 4, 18, 6], vec![15, 12, 1, 17]],
        ]),
        22 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8, 9], vec![10, 11, 12, 13], vec![14, 15, 16, 17], vec![18, 19, 20, 21]],
            vec![vec![7, 16, 19, 15, 10], vec![17, 0, 18, 6, 12], vec![1, 3, 5, 14], vec![4, 20, 8, 11], vec![13, 21, 9, 2]],
            vec![vec![21, 17, 13, 20, 5], vec![11, 9, 14, 18, 1], vec![12, 7, 4, 16], vec![3, 8, 15, 0], vec![6, 2, 10, 19]],
        ]),
        23 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8, 9], vec![10, 11, 12, 13, 14], vec![15, 16, 17, 18], vec![19, 20, 21, 22]],
            vec![vec![21, 17, 3, 12, 19], vec![2, 8, 20, 11, 18], vec![22, 9, 16, 10, 15], vec![4, 14, 0, 6], vec![7, 5, 13, 1]],
            vec![vec![6, 13, 19, 16, 20], vec![14, 22, 1, 17, 7], vec![18, 4, 15, 21, 5], vec![12, 10, 8, 0], vec![9, 3, 11, 2]],
        ]),
        24 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8, 9], vec![10, 11, 12, 13, 14], vec![15, 16, 17, 18, 19], vec![20, 21, 22, 23]],
            vec![vec![13, 2, 23, 6, 18], vec![11, 22, 15, 4, 8], vec![3, 5, 16, 10, 20], vec![21, 12, 9, 17, 0], vec![19, 7, 14, 1]],
            vec![vec![8, 19, 20, 12, 2], vec![6, 14, 3, 15, 21], vec![17, 23, 1, 11, 5], vec![18, 10, 0, 7, 22], vec![4, 9, 13, 16]],
        ]),
        25 => Some(vec![
            vec![vec![0, 1, 2, 3, 4], vec![5, 6, 7, 8, 9], vec![10, 11, 12, 13, 14], vec![15, 16, 17, 18, 19], vec![20, 21, 22, 23, 24]],
            vec![vec![14, 7, 19, 20, 0], vec![24, 12, 18, 6, 2], vec![21, 5, 1, 10, 15], vec![4, 22, 9, 17, 11], vec![13, 8, 23, 16, 3]],
            vec![vec![8, 18, 11, 1, 20], vec![2, 17, 13, 7, 21], vec![16, 24, 14, 4, 5], vec![3, 19, 6, 22, 10], vec![9, 23, 0, 15, 12]],
        ]),
        _ => None,
    }
}

/// Convert precomputed index-based seating to named players
fn apply_precomputed(players: &[String], precomputed: &[Vec<Vec<usize>>]) -> Vec<Vec<Vec<String>>> {
    precomputed
        .iter()
        .map(|round| {
            round
                .iter()
                .map(|table| table.iter().map(|&idx| players[idx].clone()).collect())
                .collect()
        })
        .collect()
}

/// Compute lower-bound minimum violations for a given round structure.
///
/// These represent violations that are mathematically unavoidable given the
/// number of players, rounds, and table sizes. Violations at or below these
/// minimums are expected; violations above indicate suboptimal seating.
pub fn compute_minimum_violations(rounds: &[Vec<Vec<String>>]) -> [f64; 9] {
    let r = rounds.len();
    if r == 0 {
        return [0.0; 9];
    }

    let mapping = build_mapping(rounds);
    let n = mapping.len();
    if n == 0 {
        return [0.0; 9];
    }

    // --- R4 minimum (opponent twice): pigeonhole on pair-slots ---
    // Total opponent-pair-slots across all rounds
    let total_pair_slots: usize = rounds
        .iter()
        .map(|round| {
            round
                .iter()
                .map(|table| table.len() * (table.len() - 1) / 2)
                .sum::<usize>()
        })
        .sum();
    // Available unique pairs (all players that ever participated)
    let available_pairs = n * (n - 1) / 2;
    let r4_min = if total_pair_slots > available_pairs && r > 1 {
        let excess = total_pair_slots - available_pairs;
        (excess as f64 / (r as f64 - 1.0)).ceil()
    } else {
        0.0
    };

    // --- R2 minimum (opponent all rounds) ---
    // If every round has exactly 1 table (≤5 players per round), all pairs that
    // co-participate in all rounds must meet in every round.
    // For multi-table rounds, pairs CAN theoretically be separated → min 0.
    let all_single_table = rounds.iter().all(|round| round.len() == 1);
    let r2_min = if all_single_table && r >= 2 {
        // Find players who participate in ALL rounds
        let mut play_counts = vec![0usize; n];
        for round in rounds {
            for table in round {
                for player in table {
                    play_counts[mapping[player]] += 1;
                }
            }
        }
        let all_round_players = play_counts.iter().filter(|&&c| c >= r).count();
        // C(all_round_players, 2)
        (all_round_players * all_round_players.saturating_sub(1) / 2) as f64
    } else {
        0.0
    };

    // --- R7 minimum (same seat position twice) ---
    // A player at 4-player tables has 4 possible seats; at 5-player, 5 seats.
    // If they play more rounds than available seats, seat repeats are forced.
    // With mixed table sizes, available distinct seats = up to 4+5=9.
    // Conservatively: if a player plays r rounds at only 4-player tables, repeats
    // after 4 rounds. We compute per-player.
    let mut r7_min = 0.0;
    let mut player_table_sizes: Vec<Vec<usize>> = vec![vec![]; n];
    for round in rounds {
        for table in round {
            for player in table {
                player_table_sizes[mapping[player]].push(table.len());
            }
        }
    }
    for sizes in &player_table_sizes {
        if sizes.is_empty() {
            continue;
        }
        let has_4 = sizes.iter().any(|&s| s == 4);
        let has_5 = sizes.iter().any(|&s| s == 5);
        let distinct_seats = match (has_4, has_5) {
            (true, true) => 9,  // seats 1-4 at 4-table + seats 1-5 at 5-table
            (true, false) => 4,
            (false, true) => 5,
            _ => sizes.len(), // shouldn't happen
        };
        if sizes.len() > distinct_seats {
            r7_min += 1.0; // at least 1 seat repeat for this player
        }
    }

    // --- R5 minimum (fifth seat twice) ---
    // Only relevant if a player plays at 5-player tables more than 5 times
    let mut r5_min = 0.0;
    for sizes in &player_table_sizes {
        let five_table_rounds = sizes.iter().filter(|&&s| s == 5).count();
        if five_table_rounds > 5 {
            r5_min += 1.0;
        }
    }

    // --- R3 minimum (VP stddev) ---
    // If all tables across all rounds are the same size, min = 0.
    // If mixed (4 and 5), some minimum variance is unavoidable.
    // R3 minimum: with mixed table sizes (4 and 5), some VP variance is unavoidable
    // due to integer assignment constraints. Exact computation requires solving an
    // assignment problem; use 0 as conservative lower bound for now.
    let r3_min = 0.0;

    // R1 (predator-prey repeat): always 0 minimum (hard constraint, must never happen)
    // R6 (same relative position): 0 (complex, conservative)
    // R8 (transfer stddev): same logic as R3, use 0 for now
    // R9 (same position group): 0 (complex, conservative)
    [0.0, r2_min, r3_min, r4_min, r5_min, 0.0, r7_min, 0.0, 0.0]
}

/// Score an existing seating arrangement without optimization.
pub fn score_rounds(rounds: &[Vec<Vec<String>>]) -> Result<SeatingScore, String> {
    if rounds.is_empty() {
        return Err("No rounds to score".to_string());
    }
    let mapping = build_mapping(rounds);
    let n = mapping.len();
    let total = rounds.iter().fold(Measure::new(n), |mut acc, r| {
        acc.add(&measure_round(&mapping, r));
        acc
    });
    Ok(compute_score(&total, rounds.len()))
}

// ========================================================================
// PUBLIC API
// ========================================================================

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
/// ## Fresh tournament (no dropouts)
/// ```ignore
/// let (rounds, score) = compute_seating(&players, 3, None)?;
/// ```
///
/// ## Adding a round after dropouts/additions
/// ```ignore
/// // Round 2 with different players than round 1
/// let (rounds, score) = compute_seating(&current_players, 2, Some(&[round1]))?;
/// ```
///
/// ## Adding round 4+ to existing tournament
/// ```ignore
/// let (rounds, score) = compute_seating(&players, 4, Some(&prev_rounds))?;
/// ```
pub fn compute_seating(
    players: &[String],
    rounds_count: usize,
    previous_rounds: Option<&[Vec<Vec<String>>]>,
) -> Result<(Vec<Vec<Vec<String>>>, SeatingScore), String> {
    if players.len() < 4 {
        return Err("At least 4 players required".to_string());
    }

    if rounds_count == 0 {
        return Err("At least 1 round required".to_string());
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
            let mapping = build_mapping(&rounds);
            let total_measure = rounds.iter().fold(Measure::new(n), |mut acc, r| {
                acc.add(&measure_round(&mapping, r));
                acc
            });
            let score = compute_score(&total_measure, rounds.len());
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
        return Err("Could not build rounds".to_string());
    }

    // Determine fixed rounds (previous rounds are fixed)
    let fixed = previous_rounds.map(|p| p.len()).unwrap_or(0);

    // Simulated annealing parameters based on tournament size
    let (iterations, restarts) = get_sa_params(n);
    optimize_sa_multi(&mut rounds, iterations, restarts, fixed);

    // Compute final score
    let mapping = build_mapping(&rounds);
    let total_measure = rounds.iter().fold(Measure::new(mapping.len()), |mut acc, r| {
        acc.add(&measure_round(&mapping, r));
        acc
    });
    let score = compute_score(&total_measure, rounds.len());

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
) -> Result<(Vec<Vec<String>>, SeatingScore), String> {
    let total_rounds = previous_rounds.len() + 1;
    let (all_rounds, score) = compute_seating(current_players, total_rounds, Some(previous_rounds))?;

    // Return only the new round
    let new_round = all_rounds.into_iter().last().ok_or("No rounds generated")?;
    Ok((new_round, score))
}

/// Get SA parameters based on player count
fn get_sa_params(n: usize) -> (u32, u32) {
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

#[cfg(test)]
mod tests {
    use super::*;

    fn make_players(count: usize) -> Vec<String> {
        (1..=count).map(|i| format!("P{}", i)).collect()
    }

    #[test]
    fn test_build_round_8_players() {
        let players = make_players(8);
        let round = build_round(&players);
        // 8 players = 2 tables of 4
        assert_eq!(round.len(), 2);
        assert_eq!(round[0].len(), 4);
        assert_eq!(round[1].len(), 4);
    }

    #[test]
    fn test_build_round_9_players() {
        let players = make_players(9);
        let round = build_round(&players);
        // 9 players = 1 table of 5 + 1 table of 4
        assert_eq!(round.len(), 2);
        assert_eq!(round[0].len(), 5);
        assert_eq!(round[1].len(), 4);
    }

    #[test]
    fn test_build_round_10_players() {
        let players = make_players(10);
        let round = build_round(&players);
        // 10 players = 2 tables of 5
        assert_eq!(round.len(), 2);
        assert_eq!(round[0].len(), 5);
        assert_eq!(round[1].len(), 5);
    }

    #[test]
    fn test_build_round_20_players() {
        let players = make_players(20);
        let round = build_round(&players);
        // 20 players = 4 tables of 5
        assert_eq!(round.len(), 4);
        for table in &round {
            assert_eq!(table.len(), 5);
        }
    }

    #[test]
    fn test_measure_4_player_table() {
        let round = vec![vec![
            "A".to_string(),
            "B".to_string(),
            "C".to_string(),
            "D".to_string(),
        ]];
        let mapping = build_mapping(&[round.clone()]);
        let m = measure_round(&mapping, &round);

        // Check diagonal (position info)
        let a = mapping["A"];
        assert_eq!(m.get(a, a, 0), 1); // played
        assert_eq!(m.get(a, a, 1), 4); // vps available
        assert_eq!(m.get(a, a, 2), 1); // transfers (seat 1)
        assert_eq!(m.get(a, a, 3), 1); // seat 1

        // Check opponent relationships
        let b = mapping["B"];
        assert_eq!(m.get(a, b, 0), 1); // opponent
        assert_eq!(m.get(a, b, 1), 1); // B is A's prey
    }

    #[test]
    fn test_compute_seating_small() {
        let players = make_players(8);
        let result = compute_seating(&players, 3, None);
        assert!(result.is_ok());

        let (rounds, score) = result.unwrap();
        assert_eq!(rounds.len(), 3);

        // All players should play in each round
        for round in &rounds {
            let total: usize = round.iter().map(|t| t.len()).sum();
            assert_eq!(total, 8);
        }

        // No hard constraint violations expected for 8 players, 3 rounds
        assert_eq!(score.rules[0], 0.0, "R1 should be 0");
    }

    #[test]
    fn test_compute_seating_medium() {
        let players = make_players(20);
        let result = compute_seating(&players, 3, None);
        assert!(result.is_ok());

        let (rounds, score) = result.unwrap();
        assert_eq!(rounds.len(), 3);

        for round in &rounds {
            let total: usize = round.iter().map(|t| t.len()).sum();
            assert_eq!(total, 20);
        }

        // Hard constraints should be satisfied
        assert_eq!(score.rules[0], 0.0, "R1 should be 0");
        assert_eq!(score.rules[1], 0.0, "R2 should be 0");
    }

    #[test]
    fn test_compute_seating_with_previous_rounds() {
        let players = make_players(8);

        // Generate first 2 rounds
        let (initial_rounds, _) = compute_seating(&players, 2, None).unwrap();

        // Generate 3rd round with first 2 fixed
        let result = compute_seating(&players, 3, Some(&initial_rounds));
        assert!(result.is_ok());

        let (rounds, _) = result.unwrap();
        assert_eq!(rounds.len(), 3);

        // First 2 rounds should be identical
        assert_eq!(rounds[0], initial_rounds[0]);
        assert_eq!(rounds[1], initial_rounds[1]);
    }

    #[test]
    fn test_error_on_few_players() {
        let players = make_players(3);
        let result = compute_seating(&players, 3, None);
        assert!(result.is_err());
    }

    #[test]
    fn test_error_on_zero_rounds() {
        let players = make_players(8);
        let result = compute_seating(&players, 0, None);
        assert!(result.is_err());
    }

    #[test]
    fn test_seating_50_players() {
        let players = make_players(50);
        let result = compute_seating(&players, 3, None);
        assert!(result.is_ok());

        let (rounds, score) = result.unwrap();
        assert_eq!(rounds.len(), 3);

        for round in &rounds {
            let total: usize = round.iter().map(|t| t.len()).sum();
            assert_eq!(total, 50);
        }

        // Hard constraints should be satisfied
        assert_eq!(score.rules[0], 0.0, "R1 should be 0");
    }

    #[test]
    fn test_compute_next_round_with_dropout() {
        // Start with 12 players
        let players = make_players(12);
        let (rounds, _) = compute_seating(&players, 2, None).unwrap();

        // Simulate 2 players dropping out for round 3
        let remaining: Vec<String> = (1..=10).map(|i| format!("P{}", i)).collect();

        // Compute round 3 with dropouts
        let (round3, score) = compute_next_round(&remaining, &rounds).unwrap();

        // Should have correct table structure for 10 players
        let total: usize = round3.iter().map(|t| t.len()).sum();
        assert_eq!(total, 10);

        // Tables should be 5+5
        assert_eq!(round3.len(), 2);
        assert_eq!(round3[0].len(), 5);
        assert_eq!(round3[1].len(), 5);

        // No hard constraint violations
        assert_eq!(score.rules[0], 0.0, "R1 should be 0");
    }

    #[test]
    fn test_compute_next_round_with_addition() {
        // Start with 8 players
        let players = make_players(8);
        let (rounds, _) = compute_seating(&players, 2, None).unwrap();

        // Add 2 new players for round 3
        let expanded: Vec<String> = (1..=10).map(|i| format!("P{}", i)).collect();

        // Compute round 3 with new players
        let (round3, score) = compute_next_round(&expanded, &rounds).unwrap();

        // Should have correct table structure for 10 players
        let total: usize = round3.iter().map(|t| t.len()).sum();
        assert_eq!(total, 10);

        // No hard constraint violations
        assert_eq!(score.rules[0], 0.0, "R1 should be 0");
    }

    #[test]
    #[ignore] // Run with: cargo test --release benchmark -- --ignored
    fn benchmark_seating() {
        use std::time::Instant;

        // Benchmark different sizes
        for &count in &[8, 20, 50, 100] {
            let players = make_players(count);
            let start = Instant::now();
            let result = compute_seating(&players, 3, None);
            let elapsed = start.elapsed();

            assert!(result.is_ok());
            let (_, score) = result.unwrap();

            println!(
                "{} players, 3 rounds: {:?} (rules={:?})",
                count, elapsed, score.rules
            );

            // Performance targets
            match count {
                8 | 20 => assert!(elapsed.as_secs() < 1, "Small/medium should be < 1s"),
                50 => assert!(elapsed.as_secs() < 3, "50 players should be < 3s"),
                100 => assert!(elapsed.as_secs() < 5, "100 players should be < 5s"),
                _ => {}
            }
        }
    }

    #[test]
    fn test_minimum_violations_single_table() {
        // 4 players, 2 rounds, single table of 4 each round
        let players: Vec<String> = vec!["A", "B", "C", "D"]
            .into_iter()
            .map(|s| s.to_string())
            .collect();
        let rounds = vec![
            vec![players.clone()],
            vec![players.clone()],
        ];
        let mins = compute_minimum_violations(&rounds);

        // R2 (opponent all rounds): all C(4,2)=6 pairs forced to meet both rounds
        assert_eq!(mins[1], 6.0, "R2 min should be 6 for 4 players single table");
        // R4 (opponent twice): all 6 pairs forced to repeat
        assert_eq!(mins[3], 6.0, "R4 min should be 6 for 4 players single table");
        // R1 (predator-prey repeat): always 0 minimum
        assert_eq!(mins[0], 0.0, "R1 min always 0");
    }

    #[test]
    fn test_minimum_violations_multi_table() {
        // 8 players, 2 rounds, 2 tables of 4
        let players = make_players(8);
        let (rounds, _) = compute_seating(&players, 2, None).unwrap();
        let mins = compute_minimum_violations(&rounds);

        // With 2 tables and 8 players, pairs CAN be separated → min R2 = 0
        assert_eq!(mins[1], 0.0, "R2 min should be 0 for multi-table rounds");
        // total pair-slots = 2 rounds * 2 tables * C(4,2) = 24; C(8,2) = 28 → no forced repeats
        assert_eq!(mins[3], 0.0, "R4 min should be 0 for 8 players, 2 rounds");
    }

    #[test]
    fn test_minimum_violations_forced_r4() {
        // 8 players, 3 rounds, 2 tables of 4 each
        let players = make_players(8);
        let (rounds, _) = compute_seating(&players, 3, None).unwrap();
        let mins = compute_minimum_violations(&rounds);

        // total pair-slots = 3 * 12 = 36; C(8,2) = 28; excess = 8; min_R4 = ceil(8/2) = 4
        assert_eq!(mins[3], 4.0, "R4 min should be 4 for 8 players, 3 rounds");
    }
}
