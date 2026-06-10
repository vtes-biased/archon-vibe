/// League standings computation shared between frontend (WASM) and backend (PyO3).
///
/// Three standings modes:
/// - **RTP**: Sum of per-tournament rating points; GW/VP include finals
/// - **Score**: Sum of preliminary GW/VP/TP only (finals excluded)
/// - **GP**: Position-based points per tournament; GW/VP include finals
use json::JsonValue;

use crate::error::EngineError;
use crate::ratings::compute_rating_points;

/// A player's aggregated league standing entry.
#[derive(Debug, Clone)]
struct PlayerEntry {
    user_uid: String,
    gw: f64,
    vp: f64,
    tp: i32,
    points: i32, // RTP or GP points
    tournaments_count: i32,
}

/// Compute league standings from tournament data.
///
/// Input JSON:
/// ```json
/// {
///   "standings_mode": "RTP" | "Score" | "GP",
///   "tournaments": [
///     {
///       "uid": "...",
///       "rank": "" | "National Championship" | "Continental Championship",
///       "standings": [{ "user_uid": "...", "gw": 1.0, "vp": 3.5, "tp": 48, "finalist": false }],
///       "player_count": 20,
///       "finals": [{ "player_uid": "...", "gw": 0, "vp": 1.5, "tp": 0 }] // seats if finals exist
///     }
///   ]
/// }
/// ```
///
/// Output JSON: array of standing entries sorted by ranking, each with:
/// `{ "user_uid", "gw", "vp", "tp", "points", "rank", "tournaments_count" }`
pub fn compute_league_standings(config_json: &str) -> Result<String, EngineError> {
    let config = json::parse(config_json)?;
    let mode = config["standings_mode"].as_str().unwrap_or("RTP");

    let mut players: std::collections::HashMap<String, PlayerEntry> =
        std::collections::HashMap::new();

    for tournament in config["tournaments"].members() {
        let rank = tournament["rank"].as_str().unwrap_or("");
        let player_count = tournament["player_count"].as_i32().unwrap_or(0);

        // GP and RTP score by *final* placement (winner 1st even if they did not
        // lead the preliminaries; other finalists tie for 2nd). Resolve every
        // player's final-placement rank once per tournament from the shared
        // engine helper, then the loop below just looks it up.
        let final_place: std::collections::HashMap<String, usize> = if mode == "Score" {
            std::collections::HashMap::new()
        } else {
            let winner = tournament["winner"].as_str().unwrap_or("");
            crate::tournament::compute_final_standings(&tournament["standings"], winner)
                .iter()
                .filter_map(|s| Some((s["user_uid"].as_str()?.to_string(), s["rank"].as_usize()?)))
                .collect()
        };

        for standing in tournament["standings"].members() {
            let uid = standing["user_uid"].as_str().unwrap_or("").to_string();
            if uid.is_empty() {
                continue;
            }
            let gw = standing["gw"].as_f64().unwrap_or(0.0);
            let vp = standing["vp"].as_f64().unwrap_or(0.0);
            let tp = standing["tp"].as_i32().unwrap_or(0);
            let finalist = standing["finalist"].as_bool().unwrap_or(false);

            let entry = players.entry(uid.clone()).or_insert_with(|| PlayerEntry {
                user_uid: uid.clone(),
                gw: 0.0,
                vp: 0.0,
                tp: 0,
                points: 0,
                tournaments_count: 0,
            });
            entry.tournaments_count += 1;

            match mode {
                "Score" => {
                    // Standings are prelim-only (compute_preliminary_standings sums rounds only)
                    entry.gw += gw;
                    entry.vp += vp;
                    entry.tp += tp;
                }
                "RTP" => {
                    // Finalist bonus is gated on the finalist flag (every data
                    // source sets it when a final is played); winner (final rank
                    // 1) = 1, other finalists = 2.
                    let finalist_position = if finalist {
                        if final_place.get(&uid) == Some(&1) {
                            1
                        } else {
                            2
                        }
                    } else {
                        0
                    };
                    let rtp =
                        compute_rating_points(vp, gw as i32, finalist_position, player_count, rank);
                    entry.points += rtp;
                    entry.gw += gw;
                    entry.vp += vp;
                    entry.tp += tp;
                }
                "GP" => {
                    let place = final_place.get(&uid).copied().unwrap_or(0);
                    entry.points += compute_gp_points(place, 0);
                    entry.gw += gw;
                    entry.vp += vp;
                    entry.tp += tp;
                }
                _ => {
                    return Err(EngineError::internal(format!(
                        "Unknown standings mode: {}",
                        mode
                    )));
                }
            }
        }

        // For non-Score modes, add finals GW/VP/TP to displayed totals
        if mode != "Score" {
            for finalist in tournament["finals"].members() {
                let uid = finalist["player_uid"].as_str().unwrap_or("").to_string();
                if let Some(entry) = players.get_mut(&uid) {
                    entry.gw += finalist["gw"].as_f64().unwrap_or(0.0);
                    entry.vp += finalist["vp"].as_f64().unwrap_or(0.0);
                    entry.tp += finalist["tp"].as_i32().unwrap_or(0);
                }
            }
        }
    }

    // Sort players
    let mut sorted: Vec<PlayerEntry> = players.into_values().collect();
    match mode {
        "Score" => {
            sorted.sort_by(|a, b| {
                b.gw.partial_cmp(&a.gw)
                    .unwrap()
                    .then(b.vp.partial_cmp(&a.vp).unwrap())
                    .then(b.tp.cmp(&a.tp))
            });
        }
        _ => {
            // RTP and GP: sort by points desc, then GW, VP, TP
            sorted.sort_by(|a, b| {
                b.points
                    .cmp(&a.points)
                    .then(b.gw.partial_cmp(&a.gw).unwrap())
                    .then(b.vp.partial_cmp(&a.vp).unwrap())
                    .then(b.tp.cmp(&a.tp))
            });
        }
    }

    // Assign ranks with ties
    let mut result = JsonValue::Array(Vec::new());
    let mut rank = 1;
    let mut passed = 0;
    let mut prev_key: Option<(i32, i64, i64, i32)> = None;

    for entry in &sorted {
        let key = (
            entry.points,
            (entry.gw * 10.0) as i64,
            (entry.vp * 10.0) as i64,
            entry.tp,
        );
        if prev_key.is_some() && Some(key) != prev_key {
            rank += passed;
            passed = 0;
        }
        prev_key = Some(key);
        passed += 1;

        let mut obj = json::object! {
            "user_uid" => entry.user_uid.as_str(),
            "gw" => entry.gw,
            "vp" => entry.vp,
            "tp" => entry.tp,
            "points" => entry.points,
            "rank" => rank,
            "tournaments_count" => entry.tournaments_count,
        };
        // For Score mode, points field is not meaningful
        if mode == "Score" {
            obj.remove("points");
        }
        result.push(obj)?;
    }

    Ok(result.dump())
}

/// Compute GP (Grand Prix) points based on final position.
/// Winner=25, Finalists(2-5)=15, 6th=10, 7th=9, 8th=8, 9th=7, 10th=6, 11th+=3
fn compute_gp_points(position: usize, _total: usize) -> i32 {
    match position {
        1 => 25,
        2..=5 => 15,
        6 => 10,
        7 => 9,
        8 => 8,
        9 => 7,
        10 => 6,
        _ => 3,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rtp_mode() {
        let config = r#"{
            "standings_mode": "RTP",
            "tournaments": [{
                "uid": "t1",
                "rank": "",
                "player_count": 20,
                "winner": "p1",
                "standings": [
                    {"user_uid": "p1", "gw": 3.0, "vp": 6.0, "tp": 180, "finalist": true},
                    {"user_uid": "p2", "gw": 2.0, "vp": 4.0, "tp": 140, "finalist": true},
                    {"user_uid": "p3", "gw": 1.0, "vp": 2.0, "tp": 100, "finalist": false}
                ],
                "finals": [
                    {"player_uid": "p1", "gw": 1, "vp": 3.0, "tp": 60},
                    {"player_uid": "p2", "gw": 0, "vp": 1.0, "tp": 24}
                ]
            }]
        }"#;
        let result = compute_league_standings(config).unwrap();
        let parsed = json::parse(&result).unwrap();
        assert_eq!(parsed.len(), 3);
        // p1 should be ranked first
        assert_eq!(parsed[0]["user_uid"].as_str().unwrap(), "p1");
        assert_eq!(parsed[0]["rank"].as_i32().unwrap(), 1);
        // p1 gets more RTP as winner
        assert!(parsed[0]["points"].as_i32().unwrap() > parsed[1]["points"].as_i32().unwrap());
        // GW/VP should include finals
        assert_eq!(parsed[0]["gw"].as_f64().unwrap(), 4.0); // 3 prelim + 1 final
        assert_eq!(parsed[0]["vp"].as_f64().unwrap(), 9.0); // 6 prelim + 3 final
                                                            // p3 has no finals data, unchanged
        assert_eq!(parsed[2]["gw"].as_f64().unwrap(), 1.0);
        assert_eq!(parsed[2]["vp"].as_f64().unwrap(), 2.0);
    }

    #[test]
    fn test_score_mode_prelim_only() {
        let config = r#"{
            "standings_mode": "Score",
            "tournaments": [{
                "uid": "t1",
                "rank": "",
                "player_count": 20,
                "winner": "p1",
                "standings": [
                    {"user_uid": "p1", "gw": 3.0, "vp": 5.0, "tp": 180, "finalist": true},
                    {"user_uid": "p2", "gw": 3.0, "vp": 4.0, "tp": 156, "finalist": true},
                    {"user_uid": "p3", "gw": 2.0, "vp": 4.0, "tp": 120, "finalist": false}
                ],
                "finals": [
                    {"player_uid": "p1", "gw": 1, "vp": 3.0, "tp": 60},
                    {"player_uid": "p2", "gw": 0, "vp": 1.0, "tp": 24}
                ]
            }]
        }"#;
        let result = compute_league_standings(config).unwrap();
        let parsed = json::parse(&result).unwrap();
        // Standings are prelim-only; league Score mode uses them directly
        let p1 = &parsed[0];
        assert_eq!(p1["user_uid"].as_str().unwrap(), "p1");
        assert_eq!(p1["gw"].as_f64().unwrap(), 3.0);
        assert_eq!(p1["vp"].as_f64().unwrap(), 5.0);
        assert_eq!(p1["tp"].as_i32().unwrap(), 180);
    }

    #[test]
    fn test_gp_mode() {
        let config = r#"{
            "standings_mode": "GP",
            "tournaments": [{
                "uid": "t1",
                "rank": "",
                "player_count": 20,
                "winner": "p1",
                "standings": [
                    {"user_uid": "p1", "gw": 3.0, "vp": 6.0, "tp": 180, "finalist": true},
                    {"user_uid": "p2", "gw": 2.0, "vp": 4.0, "tp": 140, "finalist": true},
                    {"user_uid": "p3", "gw": 1.0, "vp": 2.0, "tp": 100, "finalist": false}
                ],
                "finals": []
            }]
        }"#;
        let result = compute_league_standings(config).unwrap();
        let parsed = json::parse(&result).unwrap();
        assert_eq!(parsed[0]["points"].as_i32().unwrap(), 25); // winner
        assert_eq!(parsed[1]["points"].as_i32().unwrap(), 15); // finalist
        assert_eq!(parsed[2]["points"].as_i32().unwrap(), 15); // 3rd = still finalist range
    }

    #[test]
    fn test_gp_mode_ties_share_rank_and_skip() {
        // p6 & p7 are tied on (gw, vp, tp): both get 6th-place GP points (10),
        // and rank 7 is skipped so p8 gets 8th-place points (8), not 9.
        let config = r#"{
            "standings_mode": "GP",
            "tournaments": [{
                "uid": "t1", "rank": "", "player_count": 8, "winner": "p1",
                "standings": [
                    {"user_uid": "p1", "gw": 3.0, "vp": 6.0, "tp": 180, "finalist": true},
                    {"user_uid": "p2", "gw": 2.0, "vp": 5.0, "tp": 150, "finalist": true},
                    {"user_uid": "p3", "gw": 2.0, "vp": 4.0, "tp": 140, "finalist": true},
                    {"user_uid": "p4", "gw": 1.0, "vp": 3.0, "tp": 120, "finalist": true},
                    {"user_uid": "p5", "gw": 1.0, "vp": 2.0, "tp": 100, "finalist": true},
                    {"user_uid": "p6", "gw": 0.0, "vp": 1.0, "tp": 80, "finalist": false},
                    {"user_uid": "p7", "gw": 0.0, "vp": 1.0, "tp": 80, "finalist": false},
                    {"user_uid": "p8", "gw": 0.0, "vp": 0.0, "tp": 40, "finalist": false}
                ],
                "finals": []
            }]
        }"#;
        let parsed = json::parse(&compute_league_standings(config).unwrap()).unwrap();
        let pts = |uid: &str| -> i32 {
            parsed
                .members()
                .find(|e| e["user_uid"].as_str() == Some(uid))
                .unwrap_or_else(|| panic!("{uid} missing"))["points"]
                .as_i32()
                .unwrap()
        };
        assert_eq!(pts("p1"), 25);
        assert_eq!(pts("p6"), 10, "tied 6th gets 6th-place points");
        assert_eq!(pts("p7"), 10, "tied 6th gets 6th-place points");
        assert_eq!(pts("p8"), 8, "rank 7 skipped, p8 is 8th");
    }

    #[test]
    fn test_gp_non_prelim_first_winner() {
        // p2 wins the finals despite finishing 2nd in the prelims. The finals
        // winner must score 25 (GP rank 1); the prelim leader who lost the
        // finals drops into the flat 2nd-5th band (15). Non-finalists are
        // unaffected. Guards the core of the bug: GP must follow final
        // placement, not prelim order.
        let config = r#"{
            "standings_mode": "GP",
            "tournaments": [{
                "uid": "t1", "rank": "", "player_count": 10, "winner": "p2",
                "standings": [
                    {"user_uid": "p1", "gw": 3.0, "vp": 6.0, "tp": 180, "finalist": true},
                    {"user_uid": "p2", "gw": 2.0, "vp": 5.0, "tp": 150, "finalist": true},
                    {"user_uid": "p3", "gw": 2.0, "vp": 4.0, "tp": 140, "finalist": true},
                    {"user_uid": "p4", "gw": 1.0, "vp": 3.0, "tp": 120, "finalist": true},
                    {"user_uid": "p5", "gw": 1.0, "vp": 2.0, "tp": 100, "finalist": true},
                    {"user_uid": "p6", "gw": 0.0, "vp": 1.0, "tp": 80, "finalist": false}
                ],
                "finals": [
                    {"player_uid": "p2", "gw": 1, "vp": 3.0, "tp": 60},
                    {"player_uid": "p1", "gw": 0, "vp": 2.0, "tp": 48}
                ]
            }]
        }"#;
        let parsed = json::parse(&compute_league_standings(config).unwrap()).unwrap();
        let pts = |uid: &str| -> i32 {
            parsed
                .members()
                .find(|e| e["user_uid"].as_str() == Some(uid))
                .unwrap_or_else(|| panic!("{uid} missing"))["points"]
                .as_i32()
                .unwrap()
        };
        assert_eq!(
            pts("p2"),
            25,
            "finals winner scores 25 even from prelim 2nd"
        );
        assert_eq!(
            pts("p1"),
            15,
            "prelim leader who lost the finals drops to 15"
        );
        assert_eq!(pts("p3"), 15);
        assert_eq!(pts("p4"), 15);
        assert_eq!(pts("p5"), 15);
        assert_eq!(pts("p6"), 10, "top non-finalist is 6th");
    }

    #[test]
    fn test_gp_rank_resets_between_tournaments() {
        // Guards the per-tournament reset of gp_rank/gp_prev_key. T1 ends on a
        // tie at rank 2 (b,c share key (10,30,60)); T2's first player d shares
        // that exact key. If the rank state leaked across tournaments, d would
        // keep rank 2 (15pts) instead of being T2's rank 1 (25pts).
        let config = r#"{
            "standings_mode": "GP",
            "tournaments": [
                {"uid":"t1","rank":"","player_count":3,"winner":"a","standings":[
                    {"user_uid":"a","gw":2.0,"vp":6.0,"tp":120,"finalist":true},
                    {"user_uid":"b","gw":1.0,"vp":3.0,"tp":60,"finalist":false},
                    {"user_uid":"c","gw":1.0,"vp":3.0,"tp":60,"finalist":false}
                ],"finals":[]},
                {"uid":"t2","rank":"","player_count":2,"winner":"d","standings":[
                    {"user_uid":"d","gw":1.0,"vp":3.0,"tp":60,"finalist":true},
                    {"user_uid":"e","gw":0.0,"vp":0.0,"tp":0,"finalist":false}
                ],"finals":[]}
            ]
        }"#;
        let parsed = json::parse(&compute_league_standings(config).unwrap()).unwrap();
        let pts = |uid: &str| -> i32 {
            parsed
                .members()
                .find(|e| e["user_uid"].as_str() == Some(uid))
                .unwrap_or_else(|| panic!("{uid} missing"))["points"]
                .as_i32()
                .unwrap()
        };
        assert_eq!(
            pts("d"),
            25,
            "T2 leader must be rank 1, not carried-over rank 2"
        );
        assert_eq!(pts("a"), 25);
        assert_eq!(pts("b"), 15);
        assert_eq!(pts("c"), 15);
        assert_eq!(pts("e"), 15);
    }

    #[test]
    fn test_gp_points() {
        assert_eq!(compute_gp_points(1, 20), 25);
        assert_eq!(compute_gp_points(2, 20), 15);
        assert_eq!(compute_gp_points(5, 20), 15);
        assert_eq!(compute_gp_points(6, 20), 10);
        assert_eq!(compute_gp_points(10, 20), 6);
        assert_eq!(compute_gp_points(11, 20), 3);
        assert_eq!(compute_gp_points(50, 100), 3);
    }

    #[test]
    fn test_multiple_tournaments() {
        let config = r#"{
            "standings_mode": "GP",
            "tournaments": [
                {
                    "uid": "t1", "rank": "", "player_count": 10, "winner": "p1",
                    "standings": [
                        {"user_uid": "p1", "gw": 2.0, "vp": 4.0, "tp": 120, "finalist": true},
                        {"user_uid": "p2", "gw": 1.0, "vp": 2.0, "tp": 60, "finalist": false}
                    ],
                    "finals": []
                },
                {
                    "uid": "t2", "rank": "", "player_count": 10, "winner": "p2",
                    "standings": [
                        {"user_uid": "p2", "gw": 2.0, "vp": 4.0, "tp": 120, "finalist": true},
                        {"user_uid": "p1", "gw": 1.0, "vp": 2.0, "tp": 60, "finalist": false}
                    ],
                    "finals": []
                }
            ]
        }"#;
        let result = compute_league_standings(config).unwrap();
        let parsed = json::parse(&result).unwrap();
        // Both have 25+15 = 40 GP points — should be tied at rank 1
        assert_eq!(parsed[0]["points"].as_i32().unwrap(), 40);
        assert_eq!(parsed[1]["points"].as_i32().unwrap(), 40);
        assert_eq!(parsed[0]["rank"].as_i32().unwrap(), 1);
        assert_eq!(parsed[1]["rank"].as_i32().unwrap(), 1);
        // Both played 2 tournaments
        assert_eq!(parsed[0]["tournaments_count"].as_i32().unwrap(), 2);
    }

    #[test]
    fn test_real_data_gp_mode() {
        // 5-player event, all 5 in the final (finalist flags set, as every
        // importer/engine writer does). lionel has 2 prelim GW + the finals GW.
        let config = r#"{
            "standings_mode": "GP",
            "tournaments": [{
                "uid": "t1",
                "rank": "",
                "player_count": 5,
                "winner": "lionel",
                "standings": [
                    {"user_uid": "lionel", "gw": 2.0, "vp": 6.5, "tp": 120, "finalist": true},
                    {"user_uid": "p2", "gw": 0.0, "vp": 0.5, "tp": 66, "finalist": true},
                    {"user_uid": "p3", "gw": 0.0, "vp": 0.5, "tp": 66, "finalist": true},
                    {"user_uid": "p4", "gw": 0.0, "vp": 0.5, "tp": 66, "finalist": true},
                    {"user_uid": "p5", "gw": 0.0, "vp": 0.0, "tp": 42, "finalist": true}
                ],
                "finals": [
                    {"player_uid": "lionel", "gw": 1, "vp": 5.0, "tp": 60},
                    {"player_uid": "p2", "gw": 0, "vp": 0.0, "tp": 30},
                    {"player_uid": "p3", "gw": 0, "vp": 0.0, "tp": 30},
                    {"player_uid": "p4", "gw": 0, "vp": 0.0, "tp": 30},
                    {"player_uid": "p5", "gw": 0, "vp": 0.0, "tp": 30}
                ]
            }]
        }"#;
        let result = compute_league_standings(config).unwrap();
        let parsed = json::parse(&result).unwrap();
        let lionel = parsed
            .members()
            .find(|e| e["user_uid"] == "lionel")
            .unwrap();
        // GP: prelim 2GW + finals 1GW = 3GW displayed
        assert_eq!(lionel["gw"].as_f64().unwrap(), 3.0);
        assert_eq!(lionel["vp"].as_f64().unwrap(), 11.5); // 6.5 + 5.0
        assert_eq!(lionel["points"].as_i32().unwrap(), 25); // winner = rank 1
        let pts = |uid: &str| {
            parsed.members().find(|e| e["user_uid"] == uid).unwrap()["points"]
                .as_i32()
                .unwrap()
        };
        assert_eq!(pts("p2"), 15, "other finalists tie for 2nd");
        assert_eq!(pts("p5"), 15);
    }

    #[test]
    fn test_real_data_score_mode() {
        let config = r#"{
            "standings_mode": "Score",
            "tournaments": [{
                "uid": "t1",
                "rank": "",
                "player_count": 5,
                "winner": "lionel",
                "standings": [
                    {"user_uid": "lionel", "gw": 2.0, "vp": 6.5, "tp": 120, "finalist": false},
                    {"user_uid": "p2", "gw": 0.0, "vp": 0.5, "tp": 66, "finalist": false},
                    {"user_uid": "p3", "gw": 0.0, "vp": 0.5, "tp": 66, "finalist": false},
                    {"user_uid": "p4", "gw": 0.0, "vp": 0.5, "tp": 66, "finalist": false},
                    {"user_uid": "p5", "gw": 0.0, "vp": 0.0, "tp": 42, "finalist": false}
                ],
                "finals": [
                    {"player_uid": "lionel", "gw": 1, "vp": 5.0, "tp": 60},
                    {"player_uid": "p2", "gw": 0, "vp": 0.0, "tp": 30},
                    {"player_uid": "p3", "gw": 0, "vp": 0.0, "tp": 30},
                    {"player_uid": "p4", "gw": 0, "vp": 0.0, "tp": 30},
                    {"player_uid": "p5", "gw": 0, "vp": 0.0, "tp": 30}
                ]
            }]
        }"#;
        let result = compute_league_standings(config).unwrap();
        let parsed = json::parse(&result).unwrap();
        let lionel = parsed
            .members()
            .find(|e| e["user_uid"] == "lionel")
            .unwrap();
        // Score: prelim only = 2GW
        assert_eq!(lionel["gw"].as_f64().unwrap(), 2.0);
        assert_eq!(lionel["vp"].as_f64().unwrap(), 6.5);
    }

    #[test]
    fn test_empty_tournaments() {
        let config = r#"{"standings_mode": "RTP", "tournaments": []}"#;
        let result = compute_league_standings(config).unwrap();
        assert_eq!(result, "[]");
    }
}
