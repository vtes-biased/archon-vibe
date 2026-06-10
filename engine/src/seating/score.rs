//! Scoring layer: the lexicographic rule score, the detailed/issue views, and
//! the unavoidable-minimum lower bounds.
//!
//! Rule order (strict lexicographic priority, R1 is highest priority):
//! - R1: predator-prey repeat (hard)
//! - R2: opponent on all rounds (hard)
//! - R3: VP distribution (stddev)
//! - R4: opponent twice
//! - R5: fifth seat twice
//! - R6: same relative position
//! - R7: same seat position
//! - R8: transfers distribution (stddev)
//! - R9: same position group

use super::measure::{build_mapping, measure_round, Measure};
use crate::error::EngineError;

/// Lexicographic score - array of 9 rule violation counts
/// Compare using `cmp_lex` for strict priority ordering
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct LexScore(pub [f64; 9]);

impl LexScore {
    /// Compare two scores lexicographically
    /// Returns Ordering::Less if self is better (lower violations)
    #[allow(clippy::should_implement_trait)]
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

/// Core scorer shared by [`fast_lex_score`] and [`compute_score`].
///
/// Returns the 9 rule-violation counts plus the mean VPs / transfers. When no
/// player has played, every count and mean is 0 (the diagonal and off-diagonal
/// reads are all zero), so callers needn't special-case the empty matrix.
fn score_measure(measure: &Measure, rounds_count: usize) -> ([f64; 9], f64, f64) {
    let n = measure.n();
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

    // R3: VP stddev, R8: transfers stddev (and the means they hang off)
    let (mean_vps, mean_transfers, r3, r8) = if playing_count > 0 {
        let pc = playing_count as f64;
        let mean_vps = vps_sum / pc;
        let mean_transfers = transfers_sum / pc;
        let r3 = (vps_list.iter().map(|v| (v - mean_vps).powi(2)).sum::<f64>() / pc).sqrt();
        let r8 = (transfers_list
            .iter()
            .map(|t| (t - mean_transfers).powi(2))
            .sum::<f64>()
            / pc)
            .sqrt();
        (mean_vps, mean_transfers, r3, r8)
    } else {
        (0.0, 0.0, 0.0, 0.0)
    };

    // Count violations from position data
    let mut r5 = 0.0; // Fifth seat twice
    let mut r7 = 0.0; // Same seat twice
    for i in 0..n {
        for seat in 3..8 {
            if measure.get(i, i, seat) > 1 {
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

    (
        [r1, r2, r3, r4, r5, r6, r7, r8, r9],
        mean_vps,
        mean_transfers,
    )
}

/// Compute lexicographic score for optimization (hot path)
pub(crate) fn fast_lex_score(measure: &Measure, rounds_count: usize) -> LexScore {
    LexScore(score_measure(measure, rounds_count).0)
}

/// Compute detailed score (rule counts + means)
pub(crate) fn compute_score(measure: &Measure, rounds_count: usize) -> SeatingScore {
    let (rules, mean_vps, mean_transfers) = score_measure(measure, rounds_count);
    SeatingScore {
        rules,
        mean_vps,
        mean_transfers,
    }
}

/// Total-measure a full set of rounds and score it.
pub(crate) fn score_total(rounds: &[Vec<Vec<String>>]) -> SeatingScore {
    let mapping = build_mapping(rounds);
    let total = rounds
        .iter()
        .fold(Measure::new(mapping.len()), |mut acc, r| {
            acc.add(&measure_round(&mapping, r));
            acc
        });
    compute_score(&total, rounds.len())
}

/// Per-player seating issue
#[derive(Debug, Clone)]
pub struct SeatingIssue {
    pub rule: usize,          // 0-8 (R1-R9)
    pub players: Vec<String>, // involved player UIDs
}

impl SeatingIssue {
    pub fn to_json(&self) -> json::JsonValue {
        json::object! {
            rule: self.rule,
            players: self.players.iter().map(|p| p.as_str().into()).collect::<Vec<json::JsonValue>>(),
        }
    }
}

#[allow(clippy::needless_range_loop)] // `i`/`j` index both matrix and `reverse` vec
/// Compute per-player seating issues (which players violate which rules).
/// Returns a list of SeatingIssue, each identifying a rule and the involved player UIDs.
/// Ported from legacy Evaluator.issues().
pub fn compute_player_issues(rounds: &[Vec<Vec<String>>]) -> Vec<SeatingIssue> {
    if rounds.is_empty() {
        return vec![];
    }
    let mapping = build_mapping(rounds);
    let n = mapping.len();
    if n == 0 {
        return vec![];
    }
    // Build reverse mapping
    let mut reverse: Vec<String> = vec![String::new(); n];
    for (name, &idx) in &mapping {
        reverse[idx] = name.clone();
    }
    // Compute total measure
    let total = rounds.iter().fold(Measure::new(n), |mut acc, r| {
        acc.add(&measure_round(&mapping, r));
        acc
    });
    let rounds_count = rounds.len();

    let mut issues = Vec::new();

    // Compute global values
    let mut mean_vps = 0.0_f64;
    let mut mean_trs = 0.0_f64;
    let mut playing = 0_usize;

    for i in 0..n {
        let rounds_played = total.get(i, i, 0);
        if rounds_played > 0 {
            mean_vps += total.get(i, i, 1) as f64 / rounds_played as f64;
            mean_trs += total.get(i, i, 2) as f64 / rounds_played as f64;
            playing += 1;
        }
    }
    if playing == 0 {
        return vec![];
    }
    mean_vps /= playing as f64;
    mean_trs /= playing as f64;

    // Diagonal checks (per-player)
    for i in 0..n {
        let rounds_played = total.get(i, i, 0);
        if rounds_played == 0 {
            continue;
        }
        let rp = rounds_played as f64;

        // R3: VP distribution
        if (mean_vps - total.get(i, i, 1) as f64 / rp).abs() > 1.0 / rp {
            issues.push(SeatingIssue {
                rule: 2,
                players: vec![reverse[i].clone()],
            });
        }
        // R8: Transfer distribution
        if (mean_trs - total.get(i, i, 2) as f64 / rp).abs() > 2.0 / rp {
            issues.push(SeatingIssue {
                rule: 7,
                players: vec![reverse[i].clone()],
            });
        }
        // R5: Fifth seat twice, R7: Same seat twice
        for seat in 3..8 {
            let count = total.get(i, i, seat);
            if count > 1 {
                issues.push(SeatingIssue {
                    rule: 6,
                    players: vec![reverse[i].clone()],
                }); // R7
                if seat == 7 {
                    issues.push(SeatingIssue {
                        rule: 4,
                        players: vec![reverse[i].clone()],
                    }); // R5
                }
            }
        }
    }

    // Off-diagonal checks (pair-wise)
    for i in 0..n {
        for j in 0..i {
            let opponent_count = total.get(i, j, 0);
            if opponent_count > 1 {
                // R4: Opponent twice (only meaningful for larger tournaments)
                if playing > 20 {
                    issues.push(SeatingIssue {
                        rule: 3,
                        players: vec![reverse[i].clone(), reverse[j].clone()],
                    });
                }
                // R2: Opponent all rounds (only when rounds > 2)
                if opponent_count >= rounds_count as i32 && rounds_count > 2 {
                    issues.push(SeatingIssue {
                        rule: 1,
                        players: vec![reverse[i].clone(), reverse[j].clone()],
                    });
                }
                // Check specific relationships
                for k in 1..6 {
                    if total.get(i, j, k) > 1 {
                        // R6: Same position
                        issues.push(SeatingIssue {
                            rule: 5,
                            players: vec![reverse[i].clone(), reverse[j].clone()],
                        });
                        // R1: Predator-prey repeat (prey=1, pred=4)
                        if k == 1 || k == 4 {
                            issues.push(SeatingIssue {
                                rule: 0,
                                players: vec![reverse[i].clone(), reverse[j].clone()],
                            });
                        }
                    }
                }
                // R9: Same position group (neighbour/non-neighbour, only meaningful for larger tournaments)
                if playing > 20 {
                    for k in 6..8 {
                        if total.get(i, j, k) > 1 {
                            issues.push(SeatingIssue {
                                rule: 8,
                                players: vec![reverse[i].clone(), reverse[j].clone()],
                            });
                        }
                    }
                }
            }
        }
    }

    issues
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
        let has_4 = sizes.contains(&4);
        let has_5 = sizes.contains(&5);
        let distinct_seats = match (has_4, has_5) {
            (true, true) => 9, // seats 1-4 at 4-table + seats 1-5 at 5-table
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
pub fn score_rounds(rounds: &[Vec<Vec<String>>]) -> Result<SeatingScore, EngineError> {
    if rounds.is_empty() {
        return Err(EngineError::internal("No rounds to score"));
    }
    Ok(score_total(rounds))
}
