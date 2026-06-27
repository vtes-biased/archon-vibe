//! Standings computation and management.

use json::JsonValue;

use super::sanctions::{
    has_dq_sanction, resolve_sa_effective_rounds, sa_vp_penalty, table_sa_adjustments,
};
use super::scoring::{compute_gw, compute_tp};

/// Player standing: (user_uid, gw, vp, tp, toss, finalist, disqualified)
pub(super) struct Standing {
    pub user_uid: String,
    pub gw: f64,
    pub vp: f64,
    pub tp: f64,
    pub toss: u32,
    pub finalist: bool,
    /// DQ'd players forfeit their own score (gw/vp/tp zeroed) and sort last, but
    /// stay in standings flagged — opponents keep the VPs they earned vs them.
    pub disqualified: bool,
    /// Proxy: a non-competing official stood in for this player. Excluded from
    /// rank/rating/finals and sorted last like DQ, but — unlike DQ — the score is
    /// NOT zeroed (the seat's VPs are real for opponents and table-sum checks).
    pub non_competing: bool,
}

/// Compute standings from all rounds. Sorted by GW desc, VP desc, TP desc, toss desc.
///
/// GW and TP are **recomputed** per table from raw VPs + current sanctions (not
/// summed from the stored seat values), so a standings_adjustment issued *after*
/// a round was scored still re-decides who has the GW and re-ranks TP — the seat
/// `result.gw`/`result.tp` are frozen at score time and would otherwise go stale.
/// VP sums the raw per-seat VP, then the full SA penalty (`-1.0` per played-round
/// SA, JG v2 1.1.3) is subtracted, which may take a player's total negative.
/// Per-seat `result.vp` stays raw for display.
pub(super) fn compute_preliminary_standings(
    tournament: &JsonValue,
    sanctions: &JsonValue,
) -> Vec<Standing> {
    let mut map: std::collections::HashMap<String, (f64, f64, f64)> =
        std::collections::HashMap::new();
    let effective_sas = resolve_sa_effective_rounds(tournament, sanctions);

    // Recompute GW/TP per table from raw VPs + current sanctions; sum raw VP.
    for (round_index, round) in tournament["rounds"].members().enumerate() {
        for table in round.members() {
            if table["state"].as_str() == Some("Cancelled") {
                continue; // soft-cancelled round contributes no score
            }
            let seating = &table["seating"];
            let vps: Vec<f64> = seating
                .members()
                .map(|s| s["result"]["vp"].as_f64().unwrap_or(0.0))
                .collect();
            let adjustments = table_sa_adjustments(seating, round_index, &effective_sas);
            let gws = compute_gw(&vps, &adjustments);
            let tps = compute_tp(vps.len(), &vps, &adjustments);
            for (i, seat) in seating.members().enumerate() {
                let uid = seat["player_uid"].as_str().unwrap_or("").to_string();
                if uid.is_empty() {
                    continue;
                }
                let entry = map.entry(uid).or_insert((0.0, 0.0, 0.0));
                entry.0 += gws[i];
                entry.1 += vps[i]; // raw VP; SA penalty applied to the total below
                entry.2 += tps[i];
            }
        }
    }

    // Apply the full SA penalty (-1.0 per resolved SA; may go negative) to each
    // penalized player, per JG v2 1.1.3. The per-round result.vp stays raw; the
    // penalty lives only in the standings total. Same resolved-SA list the GW/TP
    // cascade above used, so VP and GW/TP agree on every effective round.
    for uid in map.keys().cloned().collect::<Vec<_>>() {
        let penalty = sa_vp_penalty(&effective_sas, &uid);
        if penalty != 0.0 {
            if let Some(entry) = map.get_mut(&uid) {
                entry.1 -= penalty;
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
            // DQ (state set by the backend on a DQ sanction, or an active DQ
            // sanction — same dual signal the check-in skip uses): forfeit the
            // player's own score. Their seat is left intact above, so the per-table
            // GW/TP the opponents earned already stand.
            let disqualified = player.and_then(|p| p["state"].as_str()) == Some("Disqualified")
                || has_dq_sanction(sanctions, &uid);
            // Proxy: excluded from rank like DQ, but the score is kept (not zeroed) —
            // the seat's VPs are real for opponents / table-sum validation.
            let non_competing = player
                .and_then(|p| p["non_competing"].as_bool())
                .unwrap_or(false);
            let (gw, vp, tp) = if disqualified {
                (0.0, 0.0, 0.0)
            } else {
                (gw, vp, tp)
            };
            Standing {
                user_uid: uid,
                gw,
                vp,
                tp,
                toss,
                finalist,
                disqualified,
                non_competing,
            }
        })
        .collect();

    // Sort desc by score, then toss (finals cutoff tiebreak), then user_uid as a
    // deterministic terminal key — without it, players fully tied on (gw, vp, tp,
    // toss) come out in nondeterministic HashMap order, flipping rank-based GP
    // league points. Note: toss decides the finals cutoff only; it does NOT split
    // ranks for GP points (that key is gw/vp/tp — see league.rs).
    standings.sort_by(|a, b| {
        // Non-ranked players (DQ'd or proxy) sort last (false < true), then by
        // score within each group.
        (a.disqualified || a.non_competing)
            .cmp(&(b.disqualified || b.non_competing))
            .then(b.gw.partial_cmp(&a.gw).unwrap())
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
                "disqualified" => s.disqualified,
                "non_competing" => s.non_competing,
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
/// - Disqualified players (the `disqualified` flag) are held out of the ranked
///   buckets entirely and appended last with no competitive place (JG v2 §1.1.4).
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
    let mut excluded: Vec<&JsonValue> = Vec::new();
    for s in standings.members() {
        if s["disqualified"].as_bool().unwrap_or(false)
            || s["non_competing"].as_bool().unwrap_or(false)
        {
            // DQ'd or proxy: never a placed competitor — held out of the ranked
            // buckets so they don't tie with (or displace) a real competitor, then
            // appended last (below). The UI renders these rows as "—" off the flag,
            // not the rank.
            excluded.push(s);
        } else if winner_present && s["user_uid"].as_str() == Some(winner) {
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

    // Excluded players (DQ'd or proxy) have no competitive place: append them last
    // with ranks that continue past every ranked player, so any rank-keyed sort keeps
    // them at the bottom. The number is never shown — the UI renders them "—" + badge.
    let excluded_start = finalist_count + non_finalists.len() + 1;
    for (i, s) in excluded.iter().enumerate() {
        out.push(with_rank(s, excluded_start + i));
    }
    out
}

/// Compute a player's SA-adjusted rating VP and GW for a finished tournament.
/// Prelim VP/GW come from the rounds when per-round detail exists (GW
/// **recomputed** per table from raw VPs + current sanctions, so a late SA that
/// flips a GW is reflected, matching [`compute_preliminary_standings`]; VP minus
/// the full SA penalty via [`sa_vp_penalty`], may go negative); otherwise from the
/// player's (prelim-only) standings row as-is (VEKN-synced/rounds-less imports —
/// SA is already baked into synced numbers, so it is not re-applied there). Finals
/// VP/GW are then added from the finals seat (native, or a reconstructed import
/// final). When **no** finals table recorded the win, the tournament winner is
/// credited a +1 GW (a NO-final VEKN import; a native no-final once #341 sets
/// `winner` — native today leaves `winner==""`, so this stays inert).
///
/// Single source so the backend rating and VEKN-push paths consume the SA rule
/// from Rust instead of re-implementing it. Unlike preliminary standings VP, this
/// **includes finals** VP/GW (the rating counts the final table). Returns `(vp, gw)`.
pub fn compute_rating_vp_gw(
    tournament: &JsonValue,
    sanctions: &JsonValue,
    user_uid: &str,
) -> (f64, f64) {
    // DQ'd players earn no rating: forfeit their rating VP/GW too (the participation
    // base + finalist bonus are suppressed upstream in the rating-entry builder).
    let disqualified = tournament["players"].members().any(|p| {
        p["user_uid"].as_str() == Some(user_uid) && p["state"].as_str() == Some("Disqualified")
    }) || has_dq_sanction(sanctions, user_uid);
    // Proxies earn no rating either (non-competing official stood in for the player).
    let non_competing = tournament["players"].members().any(|p| {
        p["user_uid"].as_str() == Some(user_uid) && p["non_competing"].as_bool() == Some(true)
    });
    if disqualified || non_competing {
        return (0.0, 0.0);
    }

    let mut vp = 0.0;
    let mut gw = 0.0;
    // Prelim VP/GW: sum the rounds when we have per-round detail; otherwise read the
    // (prelim-only) standings row. Imports keep finals in the finals object below.
    if tournament["rounds"].is_empty() {
        for s in tournament["standings"].members() {
            if s["user_uid"].as_str() == Some(user_uid) {
                vp += s["vp"].as_f64().unwrap_or(0.0);
                gw += s["gw"].as_f64().unwrap_or(0.0);
                break;
            }
        }
    } else {
        let effective_sas = resolve_sa_effective_rounds(tournament, sanctions);
        for (round_index, round) in tournament["rounds"].members().enumerate() {
            for table in round.members() {
                if table["state"].as_str() == Some("Cancelled") {
                    continue; // soft-cancelled round earns no rating VP/GW
                }
                let seating = &table["seating"];
                let Some(i) = seating
                    .members()
                    .position(|s| s["player_uid"].as_str() == Some(user_uid))
                else {
                    continue;
                };
                let vps: Vec<f64> = seating
                    .members()
                    .map(|s| s["result"]["vp"].as_f64().unwrap_or(0.0))
                    .collect();
                let adjustments = table_sa_adjustments(seating, round_index, &effective_sas);
                vp += vps[i];
                gw += compute_gw(&vps, &adjustments)[i];
            }
        }
        vp -= sa_vp_penalty(&effective_sas, user_uid);
    }
    // Finals VP/GW from the finals table (native, or a reconstructed import final).
    for seat in tournament["finals"]["seating"].members() {
        if seat["player_uid"].as_str() == Some(user_uid) {
            vp += seat["result"]["vp"].as_f64().unwrap_or(0.0);
            gw += seat["result"]["gw"].as_f64().unwrap_or(0.0);
        }
    }
    // No finals table recorded the win → credit the tournament-win GW to the winner.
    if tournament["finals"].is_null() && tournament["winner"].as_str() == Some(user_uid) {
        gw += 1.0;
    }
    (vp, gw)
}

/// Check if top 5 has unbroken ties (players at the cutoff boundary with same scores and no toss differentiation)
/// Takes the *eligible* standings (DQ'd/withdrawn already filtered) so the cutoff tie check
/// matches the players who actually form the finals — not the raw standings.
pub(super) fn top5_has_ties(standings: &[&Standing]) -> bool {
    if standings.len() < 5 {
        return false;
    }
    // Check all pairs in top 5 for ties not broken by toss
    for i in 0..5 {
        for j in (i + 1)..5 {
            let a = standings[i];
            let b = standings[j];
            if a.gw == b.gw && a.vp == b.vp && a.tp == b.tp && a.toss == b.toss {
                return true;
            }
        }
    }
    // Also check if #5 ties with #6+
    if standings.len() > 5 {
        let fifth = standings[4];
        for &s in &standings[5..] {
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
    fn final_standings_dq_appended_last_without_displacing_ranks() {
        // p2 is disqualified (zeroed by compute_preliminary_standings). The non-DQ
        // players must rank 1..N contiguously as if p2 weren't there, and p2 lands
        // last with a rank past every non-DQ rank (UI renders it as "—"/DQ).
        let standings = json::parse(
            r#"[
            {"user_uid":"p1","gw":2.0,"vp":5.0,"tp":120,"finalist":false,"disqualified":false},
            {"user_uid":"p3","gw":1.0,"vp":3.0,"tp":80,"finalist":false,"disqualified":false},
            {"user_uid":"p2","gw":0.0,"vp":0.0,"tp":0,"finalist":false,"disqualified":true}
        ]"#,
        )
        .unwrap();
        let r = compute_final_standings(&standings, "");
        assert_eq!(rank_of(&r, "p1"), 1);
        assert_eq!(rank_of(&r, "p3"), 2, "non-DQ players rank contiguously");
        assert!(
            rank_of(&r, "p2") > rank_of(&r, "p3"),
            "DQ'd player sorts strictly below every non-DQ player"
        );
        assert_eq!(
            r.last().unwrap()["user_uid"].as_str(),
            Some("p2"),
            "DQ'd player is emitted last"
        );
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
