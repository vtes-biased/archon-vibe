//! Staggered seating for the awkward player counts (6, 7, 11) that don't
//! divide into tables of 4-5.

use std::collections::HashMap;

pub(crate) fn is_valid_table_count(n: usize) -> bool {
    n >= 4 && n != 6 && n != 7 && n != 11
}

/// Largest valid T < N such that (N*2 - 2*T) is also valid, so 3 rounds
/// equalize: R1=T, R2=T, R3=(2N-2T) players.
fn find_equalization_target(n: usize) -> usize {
    match n {
        6 => 4,
        7 => 5,
        11 => 9,
        _ => n, // shouldn't be called for valid counts
    }
}

/// For awkward counts (6, 7, 11), returns a subset so everyone plays exactly 2
/// of every 3 rounds; sorted by (rounds_played, uid) ascending for determinism.
pub fn select_players_for_round(
    checked_in: &[String],
    previous_rounds: &[Vec<Vec<String>>],
) -> Vec<String> {
    let n = checked_in.len();
    if is_valid_table_count(n) {
        return checked_in.to_vec();
    }

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

    // Equalizing round, only if the behind-players form a valid table count.
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

    // Normal stagger: seat the target count, prioritizing fewest rounds played.
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
