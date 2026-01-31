/// Rating points computation shared between frontend (WASM) and backend (PyO3).
///
/// Formula per tournament: 5 + 4*VP + 8*GW + round(finalist_bonus * coef)
/// - Finalist bonus: Winner=90, Runner-up=30
/// - coef = log15(player_count²) - 1, with +0.25 for NC, +1.0 for CC
/// - player_count = players with ≥1 round played

/// Compute per-tournament rating points.
/// - `vp`: victory points (float, e.g. 3.5)
/// - `gw`: game wins
/// - `finalist_position`: 0=none, 1=winner, 2=runner-up
/// - `player_count`: players with ≥1 round played
/// - `rank`: "" (basic), "National Championship", "Continental Championship"
pub fn compute_rating_points(
    vp: f64,
    gw: i32,
    finalist_position: i32,
    player_count: i32,
    rank: &str,
) -> i32 {
    let base = 5.0 + 4.0 * vp + 8.0 * (gw as f64);

    let finalist_bonus: f64 = match finalist_position {
        1 => 90.0,
        2 => 30.0,
        _ => 0.0,
    };

    let coef = if player_count > 0 && finalist_bonus > 0.0 {
        let pc = player_count as f64;
        let log15_pc2 = (pc * pc).ln() / (15.0_f64).ln();
        let rank_bonus = match rank {
            "National Championship" => 0.25,
            "Continental Championship" => 1.0,
            _ => 0.0,
        };
        log15_pc2 - 1.0 + rank_bonus
    } else {
        0.0
    };

    base as i32 + (finalist_bonus * coef).round() as i32
}

/// Map tournament format + online flag to a rating category string.
/// Returns one of: "constructed_online", "constructed_offline", "limited_online", "limited_offline"
pub fn rating_category(format: &str, online: bool) -> &'static str {
    let constructed = match format {
        "Limited" => false,
        _ => true, // Standard, V5 → Constructed
    };
    match (constructed, online) {
        (true, true) => "constructed_online",
        (true, false) => "constructed_offline",
        (false, true) => "limited_online",
        (false, false) => "limited_offline",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_points_no_finalist() {
        // 5 + 4*2.0 + 8*1 = 5 + 8 + 8 = 21
        assert_eq!(compute_rating_points(2.0, 1, 0, 20, ""), 21);
    }

    #[test]
    fn test_winner_basic_tournament() {
        // base = 5 + 4*6.0 + 8*3 = 5 + 24 + 24 = 53
        // coef = log15(20²) - 1 = ln(400)/ln(15) - 1 ≈ 2.212 - 1 = 1.212
        // finalist = round(90 * 1.212) = round(109.1) = 109
        // total = 53 + 109 = 162
        let pts = compute_rating_points(6.0, 3, 1, 20, "");
        assert_eq!(pts, 162);
    }

    #[test]
    fn test_runner_up_nc() {
        // base = 5 + 4*4.0 + 8*2 = 5 + 16 + 16 = 37
        // coef = log15(30²) - 1 + 0.25 = ln(900)/ln(15) - 1 + 0.25
        //      ≈ 6.802/2.708 - 1 + 0.25 ≈ 2.512 - 1 + 0.25 = 1.762
        // finalist = round(30 * 1.762) = round(52.86) = 53
        // total = 37 + 53 = 90
        let pts = compute_rating_points(4.0, 2, 2, 30, "National Championship");
        assert_eq!(pts, 90);
    }

    #[test]
    fn test_category_mapping() {
        assert_eq!(rating_category("Standard", true), "constructed_online");
        assert_eq!(rating_category("Standard", false), "constructed_offline");
        assert_eq!(rating_category("V5", true), "constructed_online");
        assert_eq!(rating_category("V5", false), "constructed_offline");
        assert_eq!(rating_category("Limited", true), "limited_online");
        assert_eq!(rating_category("Limited", false), "limited_offline");
    }
}
