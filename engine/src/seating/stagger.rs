//! Staggered seating for awkward player counts (6, 7, 11) where some players
//! must sit out each round so everyone plays the same number of rounds.

use std::collections::HashMap;

/// Check if n players can be divided into valid tables of 4-5
pub(crate) fn is_valid_table_count(n: usize) -> bool {
    n >= 4 && n != 6 && n != 7 && n != 11
}

/// For awkward counts, find the largest valid T < N such that (N*2 - 2*T) is also valid.
/// This ensures 3-round equalization: R1=T, R2=T, R3=(2N-2T) players.
fn find_equalization_target(n: usize) -> usize {
    // Hard-coded for the three awkward counts
    match n {
        6 => 4,  // R1=4, R2=4, R3=4
        7 => 5,  // R1=5, R2=5, R3=4
        11 => 9, // R1=9, R2=9, R3=4
        _ => n,  // shouldn't be called for valid counts
    }
}

/// Select which players should play this round. For normal counts, returns all.
/// For awkward counts (6, 7, 11), returns a subset so that after 3 rounds everyone
/// plays exactly 2. Players are sorted by (rounds_played ASC, UID ASC) for determinism.
pub fn select_players_for_round(
    checked_in: &[String],
    previous_rounds: &[Vec<Vec<String>>],
) -> Vec<String> {
    let n = checked_in.len();
    if is_valid_table_count(n) {
        return checked_in.to_vec();
    }

    // Count rounds played per player
    let mut play_count: HashMap<String, usize> = HashMap::new();
    for uid in checked_in {
        play_count.insert(uid.clone(), 0);
    }
    for round in previous_rounds {
        for table in round {
            for uid in table {
                if let Some(count) = play_count.get_mut(uid) {
                    *count += 1;
                }
            }
        }
    }

    let min_played = play_count.values().copied().min().unwrap_or(0);
    let max_played = play_count.values().copied().max().unwrap_or(0);

    // Equalizing round: if some players have fewer rounds, and they form a valid count
    if min_played < max_played {
        let mut behind: Vec<String> = checked_in
            .iter()
            .filter(|uid| play_count[uid.as_str()] < max_played)
            .cloned()
            .collect();
        behind.sort();
        if is_valid_table_count(behind.len()) {
            return behind;
        }
    }

    // Normal stagger: seat find_equalization_target(n) players, prioritizing those with fewest rounds
    let target = find_equalization_target(n);
    let mut sorted: Vec<String> = checked_in.to_vec();
    sorted.sort_by(|a, b| {
        play_count[a.as_str()]
            .cmp(&play_count[b.as_str()])
            .then_with(|| a.cmp(b))
    });
    sorted.truncate(target);
    sorted
}
