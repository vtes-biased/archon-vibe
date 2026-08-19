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
    // Reachability decides. The ring walk below cannot model a withdrawal *leaving*
    // the table — it reads the seat as a survivor still sitting there — so on its own
    // it refuses legal sheets; it is kept to name the seat at fault.
    if let Some(key) = half_steps(vps) {
        if reachable_results(n).contains(&key) {
            return None;
        }
    }
    oust_order_fault(vps).or(Some(VpError::HalfVpMismatch((0..n).collect())))
}

/// VPs in half-VP steps, or `None` for a score no table can award.
fn half_steps(vps: &[f64]) -> Option<Vec<u8>> {
    vps.iter()
        .map(|&v| {
            let halves = v * 2.0;
            ((halves - halves.round()).abs() < 1e-9 && (0.0..=5.0).contains(&v))
                .then_some(halves.round() as u8)
        })
        .collect()
}

/// Every result a table of `n` can produce (tournament rules §3.7.2): one VP per prey
/// ousted, half for withdrawing, half for surviving the time limit, and a full point
/// for whoever is last standing.
fn reachable_results(n: usize) -> &'static std::collections::HashSet<Vec<u8>> {
    static FOUR: std::sync::OnceLock<std::collections::HashSet<Vec<u8>>> =
        std::sync::OnceLock::new();
    static FIVE: std::sync::OnceLock<std::collections::HashSet<Vec<u8>>> =
        std::sync::OnceLock::new();

    fn play(alive: &[usize], vp: &mut [u8], out: &mut std::collections::HashSet<Vec<u8>>) {
        if alive.len() == 1 {
            vp[alive[0]] += 2;
            out.insert(vp.to_vec());
            vp[alive[0]] -= 2;
            return;
        }
        let mut timed = vp.to_vec();
        for &i in alive {
            timed[i] += 1;
        }
        out.insert(timed);
        for (pos, &killer) in alive.iter().enumerate() {
            let prey = alive[(pos + 1) % alive.len()];
            let rest: Vec<usize> = alive.iter().copied().filter(|&x| x != prey).collect();
            vp[killer] += 2;
            play(&rest, vp, out);
            vp[killer] -= 2;
        }
        for &quitter in alive {
            let rest: Vec<usize> = alive.iter().copied().filter(|&x| x != quitter).collect();
            vp[quitter] += 1;
            play(&rest, vp, out);
            vp[quitter] -= 1;
        }
    }

    let cell = if n == 4 { &FOUR } else { &FIVE };
    cell.get_or_init(|| {
        let mut out = std::collections::HashSet::new();
        play(&(0..n).collect::<Vec<_>>(), &mut vec![0u8; n], &mut out);
        out
    })
}

/// Which seat makes the oust order impossible, for the message. Never the verdict:
/// this pass has no way to close the ring behind a withdrawal.
fn oust_order_fault(vps: &[f64]) -> Option<VpError> {
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
            if seats.iter().all(|(_, vp)| (*vp - 0.5).abs() < 1e-9) {
                if seats.len() == 1 {
                    return Some(VpError::HalfVpMismatch(vec![seats[0].0]));
                }
                break;
            }
            // Exactly one odd seat is the last player standing on a full point, or a
            // withdrawal (§3.7.2) that left the table before the game was won.
            let remaining: Vec<(usize, f64)> = seats
                .iter()
                .filter(|(_, vp)| (*vp - 0.5).abs() > 1e-9)
                .cloned()
                .collect();
            if remaining.len() > 1 {
                return Some(VpError::HalfVpMismatch(
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
