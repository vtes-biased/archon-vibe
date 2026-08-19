use super::types::VpError;

/// VPs must be in seating (predator-prey) order around the table.
pub fn check_table_vps(vps: &[f64]) -> Option<VpError> {
    let n = vps.len();
    if !(4..=5).contains(&n) {
        return Some(VpError::InvalidTableSize);
    }
    // Do NOT loosen to a raw total: the oust-order pass below assumes no seat is
    // missing, so a raw total would wrongly accept e.g. [0,0,0,0,4] as a sweep.
    let accounted: i64 = vps.iter().map(|&v| v.ceil() as i64).sum();
    if accounted > n as i64 {
        return Some(VpError::ExcessiveTotal);
    }
    if accounted < n as i64 {
        // A half-step-consistent total exactly one entry short means a Life Boon
        // merged two halves into one integer (RedirectedVp), not unfilled seats.
        let size = n as f64;
        let total: f64 = vps.iter().sum();
        let halves = total * 2.0;
        let complete = total >= size / 2.0
            && total <= size
            && (halves - halves.round()).abs() < 1e-9
            && accounted == n as i64 - 1;
        return Some(if complete {
            VpError::RedirectedVp
        } else {
            VpError::IncompleteTotal
        });
    }
    // A half VP is only ever earned by surviving a time-out, so one anywhere on the
    // table means the game ran out: nobody was last standing, and the game-win VP that
    // otherwise sits with the survivor was never awarded.
    let timed_out = vps.iter().any(|v| (v.fract() - 0.5).abs() < 1e-9);
    let mut seats: Vec<(usize, f64)> = vps.iter().enumerate().map(|(i, &v)| (i, v)).collect();
    loop {
        if seats.is_empty() {
            break;
        }
        let mut found_oust = false;
        for j in 0..seats.len() {
            let (idx, vp_count) = seats[j];
            if vp_count <= 0.0 {
                if vp_count.fract().abs() > 1e-9 && (vp_count.fract().abs() - 1.0).abs() > 1e-9 {
                    return Some(VpError::MissingVp(idx));
                }
                let pred = if j == 0 { seats.len() - 1 } else { j - 1 };
                seats[pred].1 += vp_count - 1.0;
                seats.remove(j);
                found_oust = true;
                break;
            }
        }
        if !found_oust {
            if timed_out {
                let wrong: Vec<usize> = seats
                    .iter()
                    .filter(|(_, vp)| (*vp - 0.5).abs() > 1e-9)
                    .map(|(i, _)| *i)
                    .collect();
                if !wrong.is_empty() {
                    return Some(VpError::HalfVpMismatch(wrong));
                }
                // One survivor is a win, not a time-out: nobody was left to play on.
                if seats.len() < 2 {
                    return Some(VpError::HalfVpMismatch(
                        seats.iter().map(|(i, _)| *i).collect(),
                    ));
                }
                break;
            }
            if seats.len() != 1 || (seats[0].1 - 1.0).abs() > 1e-9 {
                return Some(VpError::MissingVp(seats[0].0));
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

/// Finals GW always awards the winner (highest adjusted VP, tiebroken by seed
/// order) — no 2VP threshold, unlike prelim GW.
pub fn compute_gw_finals(
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

/// TP ranks on `vp + adjustment`, so an SA can re-rank and re-average the table
/// (JG v2 §1.1.3, Example 2); ties average TP. Per-seat `result.vp` stays raw.
pub fn compute_tp(table_size: usize, vps: &[f64], adjustments: &[f64]) -> Vec<f64> {
    let base: &[f64] = match table_size {
        5 => &[60.0, 48.0, 36.0, 24.0, 12.0],
        4 => &[60.0, 48.0, 24.0, 12.0],
        // Seating + check_table_vps enforce 4-5 seats; the zero fallback is
        // defense against malformed imports, not a real table size.
        _ => return vec![0.0; vps.len()],
    };

    let adjusted: Vec<f64> = vps
        .iter()
        .zip(adjustments.iter())
        .map(|(v, a)| v + a)
        .collect();

    let mut indices: Vec<usize> = (0..vps.len()).collect();
    indices.sort_by(|&a, &b| {
        adjusted[b]
            .partial_cmp(&adjusted[a])
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut result = vec![0.0; vps.len()];
    let mut i = 0;
    while i < indices.len() {
        let mut j = i + 1;
        while j < indices.len() && adjusted[indices[j]] == adjusted[indices[i]] {
            j += 1;
        }
        let tp_sum: f64 = (i..j).map(|pos| base[pos]).sum();
        let tp_avg = tp_sum / (j - i) as f64;
        for k in i..j {
            result[indices[k]] = tp_avg;
        }
        i = j;
    }
    result
}
