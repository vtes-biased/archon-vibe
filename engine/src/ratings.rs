/// Rating points computation shared between frontend (WASM) and backend (PyO3).
///
/// Formula per tournament: 5 + 4*VP + 8*GW + round(finalist_bonus * coef)
/// - Finalist bonus: Winner=90, Runner-up=30
/// - coef = log15(player_count²) - 1, with +0.25 for NC, +1.0 for CC
/// - player_count = players with ≥1 round played
///
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

/// Ranking-eligibility gate (VEKN rules 3.1/3.1.6): an event counts toward the
/// international ranking only with >= 8 players who played AND a played final;
/// open-rounds / self-organized events are the non-VEKN house format, never
/// rated. Single source for backend ratings.py (inclusion filter) and the
/// frontend ranked/unranked badge (display) — don't re-derive it there.
///
/// Returns "eligible" or the blocking reason, first match wins:
/// "open_rounds" | "few_players" | "no_final".
pub fn ranking_eligibility(t: &json::JsonValue) -> &'static str {
    if t["open_rounds"].as_bool().unwrap_or(false)
        || t["self_organized_rounds"].as_bool().unwrap_or(false)
    {
        return "open_rounds";
    }
    if players_with_rounds(t) < 8 {
        return "few_players";
    }
    // A reconstructed VEKN import carries a winner but no finals object.
    let has_final = !t["finals"].is_null() || !t["winner"].as_str().unwrap_or("").is_empty();
    if !has_final {
        return "no_final";
    }
    "eligible"
}

/// Players with >= 1 round played: distinct seats across rounds + finals when
/// per-round detail exists; else (rounds-less VEKN import) standings rows
/// carrying any score. Inclusive of DQ'd players (tournament-rules A.2).
fn players_with_rounds(t: &json::JsonValue) -> usize {
    let mut played = std::collections::HashSet::new();
    if !t["rounds"].is_empty() {
        for round in t["rounds"].members() {
            for table in round.members() {
                for seat in table["seating"].members() {
                    match seat["player_uid"].as_str() {
                        Some(uid) if !uid.is_empty() => played.insert(uid),
                        _ => false,
                    };
                }
            }
        }
        for seat in t["finals"]["seating"].members() {
            match seat["player_uid"].as_str() {
                Some(uid) if !uid.is_empty() => played.insert(uid),
                _ => false,
            };
        }
        return played.len();
    }
    t["standings"]
        .members()
        .filter(|s| {
            s["gw"].as_f64().unwrap_or(0.0) != 0.0
                || s["vp"].as_f64().unwrap_or(0.0) != 0.0
                || s["tp"].as_f64().unwrap_or(0.0) != 0.0
        })
        .count()
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
    fn test_ranking_eligibility() {
        // 2 rounds × 2 tables × 4 seats = 8 distinct players, finals present.
        fn seating(uids: &[&str]) -> json::JsonValue {
            let seats: Vec<json::JsonValue> = uids
                .iter()
                .map(|u| json::object! { "player_uid" => *u })
                .collect();
            json::object! { "seating" => seats }
        }
        let eligible = json::object! {
            "rounds" => json::array![
                json::array![seating(&["a","b","c","d"]), seating(&["e","f","g","h"])],
            ],
            "finals" => seating(&["a","b","c","d","e"]),
            "winner" => "a",
        };
        assert_eq!(ranking_eligibility(&eligible), "eligible");

        // House format is never rated, regardless of size/finals.
        let mut open = eligible.clone();
        open["open_rounds"] = true.into();
        assert_eq!(ranking_eligibility(&open), "open_rounds");

        // 7 players who played < 8.
        let small = json::object! {
            "rounds" => json::array![
                json::array![seating(&["a","b","c","d"]), seating(&["e","f","g"])],
            ],
            "finals" => seating(&["a","b","c","d","e"]),
            "winner" => "a",
        };
        assert_eq!(ranking_eligibility(&small), "few_players");

        // Native no-final finish: no finals object, empty winner — the 8
        // prelim players still count, the missing final is what blocks.
        let mut no_final = eligible.clone();
        no_final["finals"] = json::JsonValue::Null;
        no_final["winner"] = "".into();
        assert_eq!(ranking_eligibility(&no_final), "no_final");

        // VEKN import: no rounds, standings carry the field, winner set, no finals.
        let import = json::object! {
            "rounds" => json::array![],
            "finals" => json::JsonValue::Null,
            "winner" => "a",
            "standings" => (0..9).map(|i| json::object! {
                "user_uid" => format!("p{i}"), "gw" => 0, "vp" => 1.5, "tp" => 24,
            }).collect::<Vec<_>>(),
        };
        assert_eq!(ranking_eligibility(&import), "eligible");
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
