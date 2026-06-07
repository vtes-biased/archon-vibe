//! Standings computation and management.

use json::JsonValue;

use super::sanctions::get_sa_sanctions;

/// Player standing: (user_uid, gw, vp, tp, toss, finalist)
pub(super) struct Standing {
    pub user_uid: String,
    pub gw: f64,
    pub vp: f64,
    pub tp: f64,
    pub toss: u32,
    pub finalist: bool,
}

/// Compute standings from all rounds. Sorted by GW desc, VP desc, TP desc, toss desc.
/// Applies SA overflow: if a player has an SA sanction for a round where their raw VP < 1.0,
/// the overflow (1.0 - raw_vp) is subtracted from their total VP.
pub(super) fn compute_preliminary_standings(
    tournament: &JsonValue,
    sanctions: &JsonValue,
) -> Vec<Standing> {
    let mut map: std::collections::HashMap<String, (f64, f64, f64)> =
        std::collections::HashMap::new();

    // Sum results across all rounds
    for round in tournament["rounds"].members() {
        for table in round.members() {
            for seat in table["seating"].members() {
                let uid = seat["player_uid"].as_str().unwrap_or("").to_string();
                if uid.is_empty() {
                    continue;
                }
                let entry = map.entry(uid).or_insert((0.0, 0.0, 0.0));
                entry.0 += seat["result"]["gw"].as_f64().unwrap_or(0.0);
                entry.1 += seat["result"]["vp"].as_f64().unwrap_or(0.0);
                entry.2 += seat["result"]["tp"].as_f64().unwrap_or(0.0);
            }
        }
    }

    // Apply SA overflow: for each SA sanction, if the player's raw VP in that round < 1.0,
    // subtract the overflow from total VP
    let sa_sanctions = get_sa_sanctions(sanctions);
    for (sa_uid, sa_round) in &sa_sanctions {
        if *sa_round >= tournament["rounds"].len() {
            continue;
        }
        // Find the player's raw VP in that round
        let mut round_vp = 0.0;
        for table in tournament["rounds"][*sa_round].members() {
            for seat in table["seating"].members() {
                if seat["player_uid"].as_str() == Some(sa_uid.as_str()) {
                    round_vp = seat["result"]["vp"].as_f64().unwrap_or(0.0);
                }
            }
        }
        if round_vp < 1.0 {
            if let Some(entry) = map.get_mut(sa_uid) {
                entry.1 -= 1.0 - round_vp; // subtract overflow
            }
        }
    }

    // Build standings with toss and finalist from player records
    let mut standings: Vec<Standing> = map
        .into_iter()
        .map(|(uid, (gw, vp, tp))| {
            let player = tournament["players"]
                .members()
                .find(|p| p["user_uid"].as_str() == Some(&uid));
            let toss = player.and_then(|p| p["toss"].as_u32()).unwrap_or(0);
            let finalist = player
                .and_then(|p| p["finalist"].as_bool())
                .unwrap_or(false);
            Standing {
                user_uid: uid,
                gw,
                vp,
                tp,
                toss,
                finalist,
            }
        })
        .collect();

    // Sort desc by score, then toss (finals cutoff tiebreak), then user_uid as a
    // deterministic terminal key — without it, players fully tied on (gw, vp, tp,
    // toss) come out in nondeterministic HashMap order, flipping rank-based GP
    // league points. Note: toss decides the finals cutoff only; it does NOT split
    // ranks for GP points (that key is gw/vp/tp — see league.rs).
    standings.sort_by(|a, b| {
        b.gw.partial_cmp(&a.gw)
            .unwrap()
            .then(b.vp.partial_cmp(&a.vp).unwrap())
            .then(b.tp.partial_cmp(&a.tp).unwrap())
            .then(b.toss.cmp(&a.toss))
            .then(a.user_uid.cmp(&b.user_uid))
    });

    standings
}

/// Compute standings and store them on the tournament JSON object.
/// Guard: does NOT overwrite standings if rounds are empty (preserves VEKN-synced data).
pub(super) fn update_standings(tournament: &mut JsonValue, sanctions: &JsonValue) {
    if tournament["rounds"].is_empty() {
        return;
    }
    let standings = compute_preliminary_standings(tournament, sanctions);
    let arr: Vec<JsonValue> = standings
        .into_iter()
        .map(|s| {
            json::object! {
                "user_uid" => s.user_uid,
                "gw" => s.gw,
                "vp" => s.vp,
                "tp" => s.tp,
                "toss" => s.toss,
                "finalist" => s.finalist,
            }
        })
        .collect();
    tournament["standings"] = JsonValue::Array(arr);
}

/// Clone a preliminary standing entry and tag it with a 1-based final `rank`.
fn with_rank(standing: &JsonValue, rank: usize) -> JsonValue {
    let mut obj = standing.clone();
    obj["rank"] = (rank as i32).into();
    obj
}

/// Reorder preliminary `standings` into **final placement** and tag each entry
/// with a 1-based `rank`, per VEKN §3.7.5 / §3.1. Single source of truth for
/// "who placed where" — consumed by league GP/RTP scoring and the post-finals
/// results display.
///
/// - The finals `winner` (when present in `standings`) is **rank 1**.
/// - Every other flagged finalist shares **rank 2**: non-winner finalists tie
///   for 2nd with no tiebreak (§3.7.5). Their array order is cosmetic (the
///   input's deterministic preliminary order) and never changes the rank.
/// - Non-finalists keep preliminary order and use standard competition ranking
///   (shared rank on equal gw/vp/tp, skipping after ties), numbered from
///   `finalist_count + 1`.
///
/// **Whether a final happened is read from the `finalist` flags**, not from any
/// separate finals data — that flag is the one signal every writer sets (engine
/// `StartFinals`, the archon importer, and VEKN sync all flag their finalists;
/// VEKN sync notably stores no finals table at all, so the flag — not finals
/// seating — is the portable signal). With no flagged finalists (a genuine
/// no-finals event) this degrades to plain preliminary competition ranking; a
/// winner, if one is set, is still pulled to rank 1 defensively.
///
/// Invariant: a player gets rank 1 iff they are the `winner` *and* appear in
/// `standings`. `standings` is assumed pre-sorted descending by preliminary
/// score (as produced by [`compute_preliminary_standings`]); order is only preserved within
/// buckets, never recomputed.
pub fn compute_final_standings(standings: &JsonValue, winner: &str) -> Vec<JsonValue> {
    let winner_present = !winner.is_empty()
        && standings
            .members()
            .any(|s| s["user_uid"].as_str() == Some(winner));

    // Partition into placement buckets, each preserving preliminary order.
    let mut winner_entry: Option<&JsonValue> = None;
    let mut finalists: Vec<&JsonValue> = Vec::new(); // flagged, non-winner
    let mut non_finalists: Vec<&JsonValue> = Vec::new();
    for s in standings.members() {
        if winner_present && s["user_uid"].as_str() == Some(winner) {
            winner_entry = Some(s);
        } else if s["finalist"].as_bool().unwrap_or(false) {
            finalists.push(s);
        } else {
            non_finalists.push(s);
        }
    }

    let finalist_count = winner_entry.is_some() as usize + finalists.len();

    let mut out: Vec<JsonValue> = Vec::new();
    if let Some(w) = winner_entry {
        out.push(with_rank(w, 1));
    }
    for s in &finalists {
        out.push(with_rank(s, 2)); // shared rank 2 — finalists tie for 2nd
    }

    // Non-finalists: standard competition ranking from finalist_count + 1.
    let start = if finalist_count > 0 {
        finalist_count + 1
    } else {
        1
    };
    let mut rank = start;
    let mut prev_key: Option<(i64, i64, i64)> = None;
    for (idx, s) in non_finalists.iter().enumerate() {
        let key = (
            (s["gw"].as_f64().unwrap_or(0.0) * 10.0) as i64,
            (s["vp"].as_f64().unwrap_or(0.0) * 10.0) as i64,
            s["tp"].as_i32().unwrap_or(0) as i64,
        );
        if prev_key != Some(key) {
            rank = start + idx; // skip ranks after a tie group
            prev_key = Some(key);
        }
        out.push(with_rank(s, rank));
    }
    out
}

/// Check if top 5 has unbroken ties (players at the cutoff boundary with same scores and no toss differentiation)
pub(super) fn top5_has_ties(standings: &[Standing]) -> bool {
    if standings.len() < 5 {
        return false;
    }
    // Check all pairs in top 5 for ties not broken by toss
    for i in 0..5 {
        for j in (i + 1)..5 {
            let a = &standings[i];
            let b = &standings[j];
            if a.gw == b.gw && a.vp == b.vp && a.tp == b.tp && a.toss == b.toss {
                return true;
            }
        }
    }
    // Also check if #5 ties with #6+
    if standings.len() > 5 {
        let fifth = &standings[4];
        for s in &standings[5..] {
            if s.gw == fifth.gw && s.vp == fifth.vp && s.tp == fifth.tp && s.toss == fifth.toss {
                return true;
            }
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rank_of(ranked: &[JsonValue], uid: &str) -> usize {
        ranked
            .iter()
            .find(|s| s["user_uid"].as_str() == Some(uid))
            .unwrap_or_else(|| panic!("{uid} missing"))["rank"]
            .as_usize()
            .unwrap()
    }

    #[test]
    fn final_standings_winner_first_finalists_tie_for_second() {
        // 8 players, top 5 finalists; p3 wins the finals from preliminary 3rd.
        let standings = json::parse(
            r#"[
            {"user_uid":"p1","gw":3.0,"vp":6.0,"tp":180,"finalist":true},
            {"user_uid":"p2","gw":2.0,"vp":5.0,"tp":150,"finalist":true},
            {"user_uid":"p3","gw":2.0,"vp":4.0,"tp":140,"finalist":true},
            {"user_uid":"p4","gw":1.0,"vp":3.0,"tp":120,"finalist":true},
            {"user_uid":"p5","gw":1.0,"vp":2.0,"tp":100,"finalist":true},
            {"user_uid":"p6","gw":0.0,"vp":1.0,"tp":80,"finalist":false},
            {"user_uid":"p7","gw":0.0,"vp":1.0,"tp":80,"finalist":false},
            {"user_uid":"p8","gw":0.0,"vp":0.0,"tp":40,"finalist":false}
        ]"#,
        )
        .unwrap();
        let r = compute_final_standings(&standings, "p3");
        assert_eq!(
            r[0]["user_uid"].as_str(),
            Some("p3"),
            "winner emitted first"
        );
        assert_eq!(rank_of(&r, "p3"), 1, "finals winner is 1st");
        for u in ["p1", "p2", "p4", "p5"] {
            assert_eq!(rank_of(&r, u), 2, "{u} ties for 2nd (§3.7.5)");
        }
        assert_eq!(rank_of(&r, "p6"), 6, "first non-finalist is 6th");
        assert_eq!(rank_of(&r, "p7"), 6, "tied 6th shares rank");
        assert_eq!(rank_of(&r, "p8"), 8, "rank 7 skipped after the tie");
    }

    #[test]
    fn final_standings_no_finals_is_prelim_ranking() {
        // No finalist flags, no winner -> plain competition ranking; 2nd-4th distinct.
        let standings = json::parse(
            r#"[
            {"user_uid":"a","gw":2.0,"vp":5.0,"tp":120,"finalist":false},
            {"user_uid":"b","gw":1.0,"vp":3.0,"tp":80,"finalist":false},
            {"user_uid":"c","gw":1.0,"vp":3.0,"tp":80,"finalist":false},
            {"user_uid":"d","gw":0.0,"vp":1.0,"tp":40,"finalist":false}
        ]"#,
        )
        .unwrap();
        let r = compute_final_standings(&standings, "");
        assert_eq!(rank_of(&r, "a"), 1);
        assert_eq!(rank_of(&r, "b"), 2);
        assert_eq!(rank_of(&r, "c"), 2, "prelim tie shares rank");
        assert_eq!(rank_of(&r, "d"), 4, "rank 3 skipped");
    }

    #[test]
    fn final_standings_flagless_winner_pulled_to_first() {
        // Import artifact: finals played but no finalist flags. Winner must still
        // be 1st; everyone else ranks from 2 by preliminary standing.
        let standings = json::parse(
            r#"[
            {"user_uid":"w","gw":2.0,"vp":6.5,"tp":120,"finalist":false},
            {"user_uid":"x","gw":0.0,"vp":0.5,"tp":66,"finalist":false},
            {"user_uid":"y","gw":0.0,"vp":0.5,"tp":66,"finalist":false},
            {"user_uid":"z","gw":0.0,"vp":0.0,"tp":42,"finalist":false}
        ]"#,
        )
        .unwrap();
        let r = compute_final_standings(&standings, "w");
        assert_eq!(rank_of(&r, "w"), 1);
        assert_eq!(rank_of(&r, "x"), 2);
        assert_eq!(rank_of(&r, "y"), 2);
        assert_eq!(rank_of(&r, "z"), 4);
    }

    #[test]
    fn final_standings_partial_final_offsets_non_finalists() {
        // Sub-5 final (3 finalists — small event or finals shrunk by DQ/dropout).
        // Guards the `finalist_count + 1` offset: non-finalists must start at 4,
        // not a hardcoded 6. The 5-finalist tests above can't catch a broken
        // offset because there player_count == finalist_count.
        let standings = json::parse(
            r#"[
            {"user_uid":"p1","gw":3.0,"vp":6.0,"tp":180,"finalist":true},
            {"user_uid":"p2","gw":2.0,"vp":5.0,"tp":150,"finalist":true},
            {"user_uid":"p3","gw":2.0,"vp":4.0,"tp":140,"finalist":true},
            {"user_uid":"p4","gw":1.0,"vp":3.0,"tp":120,"finalist":false},
            {"user_uid":"p5","gw":0.0,"vp":1.0,"tp":80,"finalist":false}
        ]"#,
        )
        .unwrap();
        let r = compute_final_standings(&standings, "p2");
        assert_eq!(rank_of(&r, "p2"), 1, "finals winner is 1st");
        assert_eq!(rank_of(&r, "p1"), 2, "other finalist ties for 2nd");
        assert_eq!(rank_of(&r, "p3"), 2);
        assert_eq!(
            rank_of(&r, "p4"),
            4,
            "non-finalists start at finalist_count + 1"
        );
        assert_eq!(rank_of(&r, "p5"), 5);
    }

    #[test]
    fn final_standings_preserves_entry_fields() {
        let standings = json::parse(
            r#"[{"user_uid":"p1","gw":1.0,"vp":3.0,"tp":60,"toss":2,"finalist":true}]"#,
        )
        .unwrap();
        let r = compute_final_standings(&standings, "p1");
        assert_eq!(
            r[0]["toss"].as_i32(),
            Some(2),
            "carries extra fields through"
        );
        assert_eq!(r[0]["rank"].as_usize(), Some(1));
    }
}
