/// League standings computation shared between frontend (WASM) and backend (PyO3).
///
/// Three standings modes:
/// - **RTP**: Sum of per-tournament rating points (reuses `compute_rating_points`)
/// - **Score**: Sum of preliminary GW/VP/TP (finals scores subtracted for finalists)
/// - **GP**: Position-based points per tournament (25/15/10-6/3)
use json::JsonValue;

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
pub fn compute_league_standings(config_json: &str) -> Result<String, String> {
    let config = json::parse(config_json).map_err(|e| e.to_string())?;
    let mode = config["standings_mode"].as_str().unwrap_or("RTP");

    let mut players: std::collections::HashMap<String, PlayerEntry> =
        std::collections::HashMap::new();

    for tournament in config["tournaments"].members() {
        let rank = tournament["rank"].as_str().unwrap_or("");
        let player_count = tournament["player_count"].as_i32().unwrap_or(0);

        // Build finals score map (player_uid -> (gw, vp, tp)) for Score mode subtraction
        let mut finals_scores: std::collections::HashMap<String, (f64, f64, i32)> =
            std::collections::HashMap::new();
        if mode == "Score" {
            for seat in tournament["finals"].members() {
                let uid = seat["player_uid"].as_str().unwrap_or("").to_string();
                if !uid.is_empty() {
                    let gw = seat["gw"].as_f64().unwrap_or(0.0);
                    let vp = seat["vp"].as_f64().unwrap_or(0.0);
                    let tp = seat["tp"].as_i32().unwrap_or(0);
                    finals_scores.insert(uid, (gw, vp, tp));
                }
            }
        }

        // Process each player in the tournament standings
        let standings = &tournament["standings"];
        let standings_count = standings.members().count();

        for (position, standing) in tournament["standings"].members().enumerate() {
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
                    entry.gw += gw;
                    entry.vp += vp;
                    entry.tp += tp;
                    // Subtract finals scores so only prelim results count
                    if let Some((fgw, fvp, ftp)) = finals_scores.get(&uid) {
                        entry.gw -= fgw;
                        entry.vp -= fvp;
                        entry.tp -= ftp;
                    }
                }
                "RTP" => {
                    let finalist_position = if finalist {
                        // Winner = position 0 in sorted standings among finalists
                        // Check if this is the winner (first finalist in standings)
                        let winner_uid = tournament["winner"].as_str().unwrap_or("");
                        if uid == winner_uid {
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
                    // GP points based on final position (1-indexed)
                    let pos = position + 1; // 1-based rank
                    let gp = compute_gp_points(pos, standings_count);
                    entry.points += gp;
                    entry.gw += gw;
                    entry.vp += vp;
                    entry.tp += tp;
                }
                _ => {
                    return Err(format!("Unknown standings mode: {}", mode));
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
        result.push(obj).map_err(|e| e.to_string())?;
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
                "finals": []
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
    }

    #[test]
    fn test_score_mode_subtracts_finals() {
        let config = r#"{
            "standings_mode": "Score",
            "tournaments": [{
                "uid": "t1",
                "rank": "",
                "player_count": 20,
                "winner": "p1",
                "standings": [
                    {"user_uid": "p1", "gw": 4.0, "vp": 8.0, "tp": 240, "finalist": true},
                    {"user_uid": "p2", "gw": 3.0, "vp": 5.0, "tp": 180, "finalist": true},
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
        // p1: prelim only = gw:3, vp:5, tp:180
        // p2: prelim only = gw:3, vp:4, tp:156
        // p3: gw:2, vp:4, tp:120
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
    fn test_empty_tournaments() {
        let config = r#"{"standings_mode": "RTP", "tournaments": []}"#;
        let result = compute_league_standings(config).unwrap();
        assert_eq!(result, "[]");
    }
}
