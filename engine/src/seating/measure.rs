//! The N×N×8 relationship matrix and the round/table construction primitives
//! the scorer and annealer build on.

use std::collections::HashMap;

// Opponent relationship vectors, 4-player tables:
// [opponent, prey, grand_prey, grand_pred, pred, cross, neighbour, non_neighbour]
const OPPONENTS_4: [[i32; 8]; 3] = [
    [1, 1, 0, 0, 0, 0, 1, 0], // position 1: prey (neighbour)
    [1, 0, 0, 0, 0, 1, 0, 1], // position 2: cross-table (non-neighbour)
    [1, 0, 0, 0, 1, 0, 1, 0], // position 3: predator (neighbour)
];

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
pub(crate) struct Measure {
    n: usize,
    data: Vec<i32>, // Flattened: [i * n * 8 + j * 8 + k]
}

#[allow(clippy::needless_range_loop)]
impl Measure {
    pub fn new(n: usize) -> Self {
        Measure {
            n,
            data: vec![0; n * n * 8],
        }
    }

    #[inline]
    pub(crate) fn n(&self) -> usize {
        self.n
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
        self.data[base..base + 8].copy_from_slice(vec);
    }

    pub fn add(&mut self, other: &Measure) {
        for i in 0..self.data.len() {
            self.data[i] += other.data[i];
        }
    }
}

pub(crate) fn build_mapping(rounds: &[Vec<Vec<String>>]) -> HashMap<String, usize> {
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

/// Full-round only — the annealer's hot loop uses the incremental index-based
/// `measure_round_idx` path instead.
#[allow(clippy::needless_range_loop)]
pub(crate) fn measure_round(mapping: &HashMap<String, usize>, round: &[Vec<String>]) -> Measure {
    let n = mapping.len();
    let mut m = Measure::new(n);

    for table in round.iter() {
        let table_size = table.len();
        if !(4..=5).contains(&table_size) {
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
            m.set_vec(i, i, &positions[seat]);

            for rel in 0..table_size - 1 {
                let opp_seat = (seat + rel + 1) % table_size;
                let opp_idx = mapping[&table[opp_seat]];
                m.add_vec(i, opp_idx, &opponents[rel]);
            }
        }
    }
    m
}

pub(crate) fn build_round(players: &[String]) -> Vec<Vec<String>> {
    let count = players.len();
    if count < 4 {
        return vec![];
    }

    // Table sizes prefer 5-player tables; 4s fill the remainder.
    let remainder = count % 5;
    let divisor = if remainder == 0 { 5 } else { remainder };
    let fours = 5 - divisor;
    let fives_count = (count - 4 * fours) / 5;

    let mut tables = Vec::new();
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

pub(crate) fn build_round_idx(players: &[usize], _n: usize) -> Vec<Vec<usize>> {
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

pub(crate) fn measure_round_idx(round: &[Vec<usize>], n: usize) -> Measure {
    let mut m = Measure::new(n);
    for table in round {
        add_table_to_measure_idx(&mut m, table, n);
    }
    m
}

#[inline]
pub(crate) fn add_table_to_measure_idx(measure: &mut Measure, table: &[usize], _n: usize) {
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

#[inline]
pub(crate) fn clear_table_from_measure_idx(measure: &mut Measure, table: &[usize], _n: usize) {
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
