use json::JsonValue;

use super::helpers::count_played_rounds;
use super::sanctions::{
    has_dq_sanction, resolve_sa_effective_rounds, sa_vp_penalty, table_sa_adjustments,
};
use super::scoring::{compute_gw, compute_gw_finals, compute_tp};

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
    /// Proxy: excluded from rank/rating/finals, sorted last like DQ, but unlike DQ
    /// the score is NOT zeroed (VPs stay real for opponents/table-sum checks).
    pub non_competing: bool,
}

/// Sorted GW desc, VP desc, TP desc, toss desc. GW/TP recompute per table from raw
/// VPs + current sanctions each call, so a late SA re-ranks (`result.vp` stays raw).
pub(super) fn compute_preliminary_standings(
    tournament: &JsonValue,
    sanctions: &JsonValue,
) -> Vec<Standing> {
    let mut map: std::collections::HashMap<String, (f64, f64, f64)> =
        std::collections::HashMap::new();
    let effective_sas = resolve_sa_effective_rounds(tournament, sanctions);

    for (round_index, round) in tournament["rounds"].members().enumerate() {
        for table in round.members() {
            if table["state"].as_str() != Some("Finished") {
                continue;
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

    // -1.0 per resolved SA (JG v2 §1.1.3), applied only here. Finals-round SAs
    // (index nrounds) are excluded: they penalize the finals result instead.
    let nrounds = tournament["rounds"].len();
    let prelim_sas: Vec<(String, usize)> = effective_sas
        .iter()
        .filter(|(_, r)| *r < nrounds)
        .cloned()
        .collect();
    for uid in map.keys().cloned().collect::<Vec<_>>() {
        let penalty = sa_vp_penalty(&prelim_sas, &uid);
        if penalty != 0.0 {
            if let Some(entry) = map.get_mut(&uid) {
                entry.1 -= penalty;
            }
        }
    }

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
            // DQ signal is state=="Disqualified" OR an active DQ sanction — the same
            // combined signal used elsewhere; forfeits the player's own score only.
            let disqualified = player.and_then(|p| p["state"].as_str()) == Some("Disqualified")
                || has_dq_sanction(sanctions, &uid);
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

    sort_by_rank(&mut standings);
    standings
}

/// GW > VP > TP > toss, DQ'd and proxies parked last. user_uid is a deterministic
/// terminal tiebreak: without it, players tied on all five come out in
/// nondeterministic HashMap order. Toss only ever orders finals candidates.
fn sort_by_rank(standings: &mut [Standing]) {
    standings.sort_by(|a, b| {
        (a.disqualified || a.non_competing)
            .cmp(&(b.disqualified || b.non_competing))
            .then(b.gw.partial_cmp(&a.gw).unwrap())
            .then(b.vp.partial_cmp(&a.vp).unwrap())
            .then(b.tp.partial_cmp(&a.tp).unwrap())
            .then(b.toss.cmp(&a.toss))
            .then(a.user_uid.cmp(&b.user_uid))
    });
}

/// Refresh per-seat GW/TP from raw VPs plus current sanctions, so a late SA cascades.
/// State is set where a table changes and never re-judged here; `Cancelled` keeps its
/// scores untouched, since `RestoreRound` re-derives the round from them.
fn refresh_round_scoring(tournament: &mut JsonValue, sanctions: &JsonValue) {
    let effective_sas = resolve_sa_effective_rounds(tournament, sanctions);
    for r in 0..tournament["rounds"].len() {
        for t in 0..tournament["rounds"][r].len() {
            let table = &tournament["rounds"][r][t];
            if table["state"].as_str() == Some("Cancelled") {
                continue;
            }
            let scored = table["state"].as_str() == Some("Finished");
            let seating = &table["seating"];
            let vps: Vec<f64> = seating
                .members()
                .map(|s| s["result"]["vp"].as_f64().unwrap_or(0.0))
                .collect();
            let adjustments = table_sa_adjustments(seating, r, &effective_sas);
            let gws = compute_gw(&vps, &adjustments);
            let tps = compute_tp(vps.len(), &vps, &adjustments);
            let table = &mut tournament["rounds"][r][t];
            for i in 0..vps.len() {
                table["seating"][i]["result"]["gw"] = if scored { gws[i] } else { 0.0 }.into();
                table["seating"][i]["result"]["tp"] = if scored { tps[i] } else { 0.0 }.into();
            }
        }
    }
}

/// Guard: skips when rounds are empty, preserving VEKN-synced standings.
pub(super) fn update_standings(tournament: &mut JsonValue, sanctions: &JsonValue) {
    refresh_round_scoring(tournament, sanctions);
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
    refresh_finals_scoring(tournament, sanctions);
}

/// Re-score a Finished finals table from raw VPs + current sanctions and re-derive
/// `winner` when already set, using the same [`compute_gw_finals`] call SetScore/FinishFinals use.
fn refresh_finals_scoring(tournament: &mut JsonValue, sanctions: &JsonValue) {
    if tournament["finals"]["state"].as_str() != Some("Finished") {
        return;
    }
    let finals_round = tournament["rounds"].len();
    let effective_sas = resolve_sa_effective_rounds(tournament, sanctions);
    let seating = &tournament["finals"]["seating"];
    let vps: Vec<f64> = seating
        .members()
        .map(|s| s["result"]["vp"].as_f64().unwrap_or(0.0))
        .collect();
    let seating_uids: Vec<String> = seating
        .members()
        .map(|s| s["player_uid"].as_str().unwrap_or("").to_string())
        .collect();
    let uid_refs: Vec<&str> = seating_uids.iter().map(String::as_str).collect();
    let adjustments = table_sa_adjustments(seating, finals_round, &effective_sas);
    let seed_order: Vec<String> = tournament["finals"]["seed_order"]
        .members()
        .filter_map(|s| s.as_str().map(String::from))
        .collect();
    let gws = compute_gw_finals(&vps, &adjustments, &uid_refs, &seed_order);
    let tps = compute_tp(vps.len(), &vps, &adjustments);
    for i in 0..vps.len() {
        tournament["finals"]["seating"][i]["result"]["gw"] = gws[i].into();
        tournament["finals"]["seating"][i]["result"]["tp"] = tps[i].into();
    }
    // Re-derive the winner only once FinishFinals set one (never crown early),
    // and never blank it (an empty derivation means an empty table).
    if !tournament["winner"].as_str().unwrap_or("").is_empty() {
        if let Some(w) = gws.iter().position(|&g| g == 1.0) {
            tournament["winner"] = uid_refs[w].into();
        }
    }
}

fn with_rank(standing: &JsonValue, rank: usize) -> JsonValue {
    let mut obj = standing.clone();
    obj["rank"] = (rank as i32).into();
    obj
}

/// The DQ signal must decide first: DQ'd rows are stored zeroed, so every one of
/// them would otherwise classify as a no-show.
pub fn is_no_show(standing: &JsonValue, winner: &str) -> bool {
    !standing["disqualified"].as_bool().unwrap_or(false)
        && !standing["finalist"].as_bool().unwrap_or(false)
        && standing["user_uid"].as_str() != Some(winner)
        && standing["gw"].as_f64().unwrap_or(0.0) == 0.0
        && standing["vp"].as_f64().unwrap_or(0.0) == 0.0
        && standing["tp"].as_f64().unwrap_or(0.0) == 0.0
}

/// Reorders preliminary `standings` (must arrive sorted desc by score) into final
/// placement per §3.7.5/§3.1: `winner` is rank 1, finalists share rank 2, DQ'd/proxy/no-show excluded and appended last.
pub fn compute_final_standings(standings: &JsonValue, winner: &str) -> Vec<JsonValue> {
    let winner_present = !winner.is_empty()
        && standings
            .members()
            .any(|s| s["user_uid"].as_str() == Some(winner));

    let stamped: Vec<JsonValue> = standings
        .members()
        .map(|s| {
            let mut row = s.clone();
            row["no_show"] = is_no_show(s, winner).into();
            row
        })
        .collect();

    let mut winner_entry: Option<&JsonValue> = None;
    let mut finalists: Vec<&JsonValue> = Vec::new();
    let mut non_finalists: Vec<&JsonValue> = Vec::new();
    let mut excluded: Vec<&JsonValue> = Vec::new();
    for s in &stamped {
        if s["disqualified"].as_bool().unwrap_or(false)
            || s["non_competing"].as_bool().unwrap_or(false)
            || s["no_show"].as_bool().unwrap_or(false)
        {
            // Never place — excluded here so they can't tie with or displace a real
            // competitor. UI renders their row via the flag, not the rank value.
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
        out.push(with_rank(s, 2));
    }

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
            rank = start + idx;
            prev_key = Some(key);
        }
        out.push(with_rank(s, rank));
    }

    // Ranks here just need to sort last; the value itself is never shown (UI
    // renders these rows via the flag, not the rank).
    let excluded_start = finalist_count + non_finalists.len() + 1;
    for (i, s) in excluded.iter().enumerate() {
        out.push(with_rank(s, excluded_start + i));
    }
    out
}

pub fn display_standings(tournament: &JsonValue, sanctions: &JsonValue) -> Vec<JsonValue> {
    let players = &tournament["players"];
    let sheet = &tournament["standings"];
    let rounds_less = tournament["rounds"].is_empty();
    let finals = &tournament["finals"];
    let use_finals =
        !rounds_less && tournament["state"].as_str() == Some("Finished") && !finals.is_null();

    let player_of = |uid: &str| {
        players
            .members()
            .find(|p| p["user_uid"].as_str() == Some(uid))
    };
    let sheet_of = |uid: &str| {
        sheet
            .members()
            .find(|s| s["user_uid"].as_str() == Some(uid))
    };
    let finals_seat = |uid: &str| {
        use_finals
            .then(|| {
                finals["seating"]
                    .members()
                    .find(|s| s["player_uid"].as_str() == Some(uid))
            })
            .flatten()
    };

    let mut winner = if rounds_less || use_finals {
        tournament["winner"].as_str().unwrap_or("").to_string()
    } else {
        String::new()
    };
    if use_finals && winner.is_empty() {
        let mut best: Option<(&str, f64, f64)> = None;
        for seat in finals["seating"].members() {
            let gw = seat["result"]["gw"].as_f64().unwrap_or(0.0);
            let vp = seat["result"]["vp"].as_f64().unwrap_or(0.0);
            if best.is_none_or(|(_, bg, bv)| gw > bg || (gw == bg && vp > bv)) {
                best = Some((seat["player_uid"].as_str().unwrap_or(""), gw, vp));
            }
        }
        winner = best.map(|(uid, _, _)| uid).unwrap_or("").to_string();
    }

    let raw: Vec<(String, f64, f64, f64, u32, bool)> = if !sheet.is_empty() {
        sheet
            .members()
            .map(|s| {
                let uid = s["user_uid"].as_str().unwrap_or("").to_string();
                let (toss, finalist) = if rounds_less {
                    (
                        s["toss"].as_u32().unwrap_or(0),
                        s["finalist"].as_bool().unwrap_or_else(|| {
                            player_of(&uid)
                                .and_then(|p| p["finalist"].as_bool())
                                .unwrap_or(false)
                        }),
                    )
                } else {
                    (
                        player_of(&uid)
                            .and_then(|p| p["toss"].as_u32())
                            .unwrap_or(0),
                        finals_seat(&uid).is_some(),
                    )
                };
                (
                    uid,
                    s["gw"].as_f64().unwrap_or(0.0),
                    s["vp"].as_f64().unwrap_or(0.0),
                    s["tp"].as_f64().unwrap_or(0.0),
                    toss,
                    finalist,
                )
            })
            .collect()
    } else if rounds_less {
        // Pre-standings imports carry the result on the roster row instead.
        players
            .members()
            .filter_map(|p| {
                let uid = p["user_uid"].as_str().unwrap_or("");
                let gw = p["result"]["gw"].as_f64().unwrap_or(0.0);
                let vp = p["result"]["vp"].as_f64().unwrap_or(0.0);
                let tp = p["result"]["tp"].as_f64().unwrap_or(0.0);
                if uid.is_empty() || (gw == 0.0 && vp == 0.0 && tp == 0.0) {
                    return None;
                }
                Some((
                    uid.to_string(),
                    gw,
                    vp,
                    tp,
                    p["toss"].as_u32().unwrap_or(0),
                    p["finalist"].as_bool().unwrap_or(false),
                ))
            })
            .collect()
    } else {
        Vec::new()
    };

    let mut rows: Vec<Standing> = raw
        .into_iter()
        .map(|(uid, gw, vp, tp, toss, finalist)| {
            let player = player_of(&uid);
            let row = sheet_of(&uid);
            let disqualified = player.and_then(|p| p["state"].as_str()) == Some("Disqualified")
                || row.is_some_and(|r| r["disqualified"].as_bool().unwrap_or(false))
                || has_dq_sanction(sanctions, &uid);
            let non_competing = player
                .and_then(|p| p["non_competing"].as_bool())
                .unwrap_or(false)
                || row.is_some_and(|r| r["non_competing"].as_bool().unwrap_or(false));
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

    sort_by_rank(&mut rows);

    let arr: Vec<JsonValue> = rows
        .iter()
        .map(|s| {
            let mut obj = json::object! {
                "user_uid" => s.user_uid.as_str(),
                "gw" => s.gw,
                "vp" => s.vp,
                "tp" => s.tp,
                "toss" => s.toss,
                "finalist" => s.finalist,
                "disqualified" => s.disqualified,
                "non_competing" => s.non_competing,
            };
            if let Some(seat) = finals_seat(&s.user_uid) {
                obj["finals"] = json::object! {
                    "gw" => seat["result"]["gw"].as_f64().unwrap_or(0.0),
                    "vp" => seat["result"]["vp"].as_f64().unwrap_or(0.0),
                    "tp" => seat["result"]["tp"].as_f64().unwrap_or(0.0),
                };
            }
            obj
        })
        .collect();

    compute_final_standings(&JsonValue::Array(arr), &winner)
}

/// SA-adjusted rating VP/GW for a finished tournament, including finals VP/GW unlike
/// preliminary standings. A win with no finals table credits +1 GW (inert when `winner == ""`).
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
                if table["state"].as_str() != Some("Finished") {
                    continue;
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
    for seat in tournament["finals"]["seating"].members() {
        if seat["player_uid"].as_str() == Some(user_uid) {
            vp += seat["result"]["vp"].as_f64().unwrap_or(0.0);
            gw += seat["result"]["gw"].as_f64().unwrap_or(0.0);
        }
    }
    if tournament["finals"].is_null() && tournament["winner"].as_str() == Some(user_uid) {
        gw += 1.0;
    }
    (vp, gw)
}

pub(super) fn scores_tied(a: &Standing, b: &Standing) -> bool {
    a.gw == b.gw && a.vp == b.vp && a.tp == b.tp
}

/// The finals candidate pool, in rank order.
pub(super) fn finals_candidates<'a>(
    players: &JsonValue,
    standings: &'a [Standing],
) -> Vec<&'a Standing> {
    standings
        .iter()
        .filter(|s| {
            // `disqualified` carries the dual DQ signal (state OR active
            // sanction); reuse it so eligibility can't diverge. Completed
            // (capped) stays eligible, Finished (withdrawn) is dropped.
            let ps = players
                .members()
                .find(|p| p["user_uid"].as_str() == Some(&s.user_uid))
                .and_then(|p| p["state"].as_str())
                .unwrap_or("");
            !s.disqualified && !s.non_competing && ps != "Finished"
        })
        .collect()
}

/// The score-tied groups `RandomToss` must order, as ranges into the candidate pool:
/// the top five, extended over everyone tied with fifth since any of them may take
/// the last seat.
pub(super) fn toss_groups(candidates: &[&Standing]) -> Vec<std::ops::Range<usize>> {
    let cutoff = candidates.len().min(5);
    let mut end = cutoff;
    if cutoff > 0 {
        let fifth = candidates[cutoff - 1];
        while end < candidates.len() && scores_tied(candidates[end], fifth) {
            end += 1;
        }
    }
    let mut groups = Vec::new();
    let mut i = 0;
    while i < end {
        let mut j = i + 1;
        while j < end && scores_tied(candidates[j], candidates[i]) {
            j += 1;
        }
        if j - i > 1 {
            groups.push(i..j);
        }
        i = j;
    }
    groups
}

/// Whether a score-tied group is already ordered — every member holding a distinct
/// non-zero toss.
pub(super) fn tosses_are_total(group: &[&Standing]) -> bool {
    let mut seen: Vec<u32> = Vec::with_capacity(group.len());
    for s in group {
        if s.toss == 0 || seen.contains(&s.toss) {
            return false;
        }
        seen.push(s.toss);
    }
    true
}

/// `has_ties` and `tied_uids` stay empty unless `possible` holds, so a caller cannot
/// read a toss verdict for a finals that could not be held anyway.
pub fn finals_qualification(tournament: &JsonValue, standings: &JsonValue) -> JsonValue {
    let mut rows: Vec<Standing> = standings
        .members()
        .map(|s| Standing {
            user_uid: s["user_uid"].as_str().unwrap_or("").to_string(),
            gw: s["gw"].as_f64().unwrap_or(0.0),
            vp: s["vp"].as_f64().unwrap_or(0.0),
            tp: s["tp"].as_f64().unwrap_or(0.0),
            toss: s["toss"].as_u32().unwrap_or(0),
            finalist: s["finalist"].as_bool().unwrap_or(false),
            disqualified: s["disqualified"].as_bool().unwrap_or(false),
            non_competing: s["non_competing"].as_bool().unwrap_or(false),
        })
        .collect();
    sort_by_rank(&mut rows);
    let candidates = finals_candidates(&tournament["players"], &rows);

    let enough_rounds = count_played_rounds(tournament) >= 2;
    let possible = enough_rounds && candidates.len() >= 5;
    let tied: Vec<JsonValue> = if possible {
        toss_groups(&candidates)
            .into_iter()
            .flat_map(|g| candidates[g].iter().map(|s| s.user_uid.as_str().into()))
            .collect()
    } else {
        Vec::new()
    };
    json::object! {
        enough_rounds: enough_rounds,
        possible: possible,
        has_ties: possible && top5_has_ties(&candidates),
        tied_uids: JsonValue::Array(tied),
    }
}

/// Takes the finals candidate pool. Only the five qualifying ranks must be total:
/// two candidates tied *below* fifth share no seat.
pub(super) fn top5_has_ties(candidates: &[&Standing]) -> bool {
    if candidates.len() < 5 {
        return false;
    }
    let tied = |a: &Standing, b: &Standing| scores_tied(a, b) && a.toss == b.toss;
    for i in 0..5 {
        for j in (i + 1)..5 {
            if tied(candidates[i], candidates[j]) {
                return true;
            }
        }
    }
    candidates[5..].iter().any(|s| tied(s, candidates[4]))
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
        // Sub-5 final guards the `finalist_count + 1` offset (must start at 4, not a
        // hardcoded 6) — the 5-finalist tests above can't catch this.
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
        // p2 is disqualified: non-DQ players must rank 1..N contiguously as if p2
        // weren't there, and p2 lands last past every non-DQ rank.
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
    fn final_standings_scoreless_rows_hold_no_placement() {
        let standings = json::parse(
            r#"[
            {"user_uid":"w","gw":1.0,"vp":4.0,"tp":120,"finalist":true},
            {"user_uid":"f","gw":0.0,"vp":0.0,"tp":0,"finalist":true},
            {"user_uid":"a","gw":0.0,"vp":2.0,"tp":90,"finalist":false},
            {"user_uid":"n1","gw":0.0,"vp":0.0,"tp":0,"finalist":false},
            {"user_uid":"n2","gw":0.0,"vp":0.0,"tp":0,"finalist":false}
        ]"#,
        )
        .unwrap();
        let r = compute_final_standings(&standings, "w");
        assert_eq!(rank_of(&r, "w"), 1);
        assert_eq!(rank_of(&r, "f"), 2, "a scoreless finalist still places");
        assert_eq!(
            rank_of(&r, "a"),
            3,
            "the last real competitor keeps its rank"
        );
        for u in ["n1", "n2"] {
            let row = r
                .iter()
                .find(|s| s["user_uid"].as_str() == Some(u))
                .unwrap_or_else(|| panic!("{u} keeps its row"));
            assert!(row["no_show"].as_bool().unwrap(), "{u} is flagged no-show");
            assert!(
                rank_of(&r, u) > rank_of(&r, "a"),
                "{u} sorts past the field"
            );
        }
    }

    #[test]
    fn display_standings_ranks_a_round_less_import_from_its_sheet() {
        // The whole pre-2014 corpus: a result sheet and no rounds to recompute from.
        // The sheet arrives unsorted, so the display path must sort and place it.
        let t = json::parse(
            r#"{
            "state":"Finished","rounds":[],"finals":null,"winner":"w",
            "players":[
                {"user_uid":"w"},{"user_uid":"f"},{"user_uid":"a"},
                {"user_uid":"b"},{"user_uid":"p","non_competing":true}
            ],
            "standings":[
                {"user_uid":"a","gw":0.0,"vp":2.0,"tp":90,"finalist":false},
                {"user_uid":"w","gw":1.0,"vp":5.0,"tp":150,"finalist":true},
                {"user_uid":"p","gw":0.0,"vp":4.0,"tp":140,"finalist":false},
                {"user_uid":"b","gw":0.0,"vp":3.0,"tp":100,"finalist":false},
                {"user_uid":"f","gw":1.0,"vp":4.0,"tp":120,"finalist":true}
            ]
        }"#,
        )
        .unwrap();
        let r = display_standings(&t, &JsonValue::new_array());
        assert_eq!(rank_of(&r, "w"), 1, "the sheet's winner places first");
        assert_eq!(rank_of(&r, "f"), 2, "the other finalist ties for 2nd");
        assert_eq!(
            rank_of(&r, "b"),
            3,
            "non-finalists rank by the sheet cascade"
        );
        assert_eq!(rank_of(&r, "a"), 4);
        assert_eq!(
            r.last().unwrap()["user_uid"].as_str(),
            Some("p"),
            "the proxy sorts last despite the second-best VP total"
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
