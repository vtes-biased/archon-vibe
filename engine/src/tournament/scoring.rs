//! Scoring functions: VP validation, GW/TP computation.

use super::types::VpError;

/// Check VP validity on a table, replicating archon's oust-order validation.
/// VPs are in seating (predator-prey) order around the table.
/// Returns None if valid, Some(error) if invalid.
pub fn check_table_vps(vps: &[f64]) -> Option<VpError> {
    let n = vps.len();
    if !(4..=5).contains(&n) {
        return Some(VpError::InvalidTableSize);
    }
    // Check total: ceil each VP, sum must equal table size
    let total: i64 = vps.iter().map(|&v| v.ceil() as i64).sum();
    if total < n as i64 {
        return Some(VpError::InsufficientTotal);
    }
    if total > n as i64 {
        return Some(VpError::ExcessiveTotal);
    }
    // Oust-order simulation: work with (original_index, accounted_vp) pairs
    let mut seats: Vec<(usize, f64)> = vps.iter().enumerate().map(|(i, &v)| (i, v)).collect();
    // Repeatedly find ousted players (vp <= 0) and transfer to predator
    loop {
        if seats.is_empty() {
            break;
        }
        let mut found_oust = false;
        for j in 0..seats.len() {
            let (idx, vp_count) = seats[j];
            if vp_count <= 0.0 {
                // A negative count with fractional part means impossible sequence
                if vp_count.fract().abs() > 1e-9 && (vp_count.fract().abs() - 1.0).abs() > 1e-9 {
                    return Some(VpError::MissingVp(idx));
                }
                // Transfer: predator (previous seat) gets vp_count - 1
                let pred = if j == 0 { seats.len() - 1 } else { j - 1 };
                seats[pred].1 += vp_count - 1.0;
                seats.remove(j);
                found_oust = true;
                break;
            }
        }
        if !found_oust {
            // All remaining scores are positive
            // If everyone is at 0.5, it's a timeout (valid if more than 1)
            if seats.iter().all(|(_, vp)| (*vp - 0.5).abs() < 1e-9) {
                if seats.len() == 1 {
                    return Some(VpError::MissingHalfVp(vec![seats[0].0]));
                }
                break; // valid timeout
            }
            // Remove 0.5s (withdrawals)
            let remaining: Vec<(usize, f64)> = seats
                .iter()
                .filter(|(_, vp)| (*vp - 0.5).abs() > 1e-9)
                .cloned()
                .collect();
            // At most 1 can remain (the last survivor with 1.0 VP)
            if remaining.len() > 1 {
                return Some(VpError::MissingHalfVp(
                    remaining.iter().map(|(i, _)| *i).collect(),
                ));
            }
            break;
        }
    }
    None
}

/// Compute GW for each player: 1 if adjusted_vp >= 2.0 AND strictly highest adjusted VP, else 0.
/// `adjustments` is same length as `vps` with negative values for SA penalties.
pub fn compute_gw(vps: &[f64], adjustments: &[f64]) -> Vec<f64> {
    if vps.is_empty() {
        return vec![];
    }
    let adjusted: Vec<f64> = vps
        .iter()
        .zip(adjustments.iter())
        .map(|(v, a)| v + a)
        .collect();
    let max_adj = adjusted.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let max_count = adjusted.iter().filter(|&&v| v == max_adj).count();
    adjusted
        .iter()
        .map(|&v| {
            if v >= 2.0 && v == max_adj && max_count == 1 {
                1.0
            } else {
                0.0
            }
        })
        .collect()
}

/// Compute GW for finals: always awards 1 GW to the winner (highest adjusted VP,
/// tiebroken by seed order). No 2VP threshold -- finals always produce a winner.
pub(crate) fn compute_gw_finals(
    vps: &[f64],
    adjustments: &[f64],
    seating_uids: &[&str],
    seed_order: &[String],
) -> Vec<f64> {
    if vps.is_empty() {
        return vec![];
    }
    let adjusted: Vec<f64> = vps
        .iter()
        .zip(adjustments.iter())
        .map(|(v, a)| v + a)
        .collect();
    let mut best_idx = 0;
    let mut best_adj = adjusted[0];
    let mut best_seed = seed_order
        .iter()
        .position(|s| s == seating_uids[0])
        .unwrap_or(usize::MAX);
    for i in 1..adjusted.len() {
        let adj = adjusted[i];
        let seed_pos = seed_order
            .iter()
            .position(|s| s == seating_uids[i])
            .unwrap_or(usize::MAX);
        if adj > best_adj || (adj == best_adj && seed_pos < best_seed) {
            best_adj = adj;
            best_idx = i;
            best_seed = seed_pos;
        }
    }
    let mut gws = vec![0.0; vps.len()];
    gws[best_idx] = 1.0;
    gws
}

/// Compute TP based on VP rank within table. Ties average their positions.
pub fn compute_tp(table_size: usize, vps: &[f64]) -> Vec<f64> {
    let base: &[f64] = match table_size {
        5 => &[60.0, 48.0, 36.0, 24.0, 12.0],
        4 => &[60.0, 48.0, 24.0, 12.0],
        3 => &[60.0, 36.0, 12.0],
        _ => return vec![0.0; vps.len()],
    };

    // Create indices sorted by VP descending
    let mut indices: Vec<usize> = (0..vps.len()).collect();
    indices.sort_by(|&a, &b| {
        vps[b]
            .partial_cmp(&vps[a])
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut result = vec![0.0; vps.len()];
    let mut i = 0;
    while i < indices.len() {
        // Find group of tied players
        let mut j = i + 1;
        while j < indices.len() && vps[indices[j]] == vps[indices[i]] {
            j += 1;
        }
        // Average TP for positions i..j
        let tp_sum: f64 = (i..j).map(|pos| base[pos]).sum();
        let tp_avg = tp_sum / (j - i) as f64;
        for k in i..j {
            result[indices[k]] = tp_avg;
        }
        i = j;
    }
    result
}
