use crate::model::{
    arg, finals_table, player, score, seat, standing, standing_row, table, tournament,
};
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

    for (round_index, round) in tournament[tournament::ROUNDS].members().enumerate() {
        for table in round.members() {
            if table[table::STATE].as_str() != Some("Finished") {
                continue;
            }
            let seating = &table[table::SEATING];
            let vps: Vec<f64> = seating
                .members()
                .map(|s| s[seat::RESULT][score::VP].as_f64().unwrap_or(0.0))
                .collect();
            let adjustments = table_sa_adjustments(seating, round_index, &effective_sas);
            let gws = compute_gw(&vps, &adjustments);
            let tps = compute_tp(vps.len(), &vps, &adjustments);
            for (i, seat) in seating.members().enumerate() {
                let uid = seat[seat::PLAYER_UID].as_str().unwrap_or("").to_string();
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
    let nrounds = tournament[tournament::ROUNDS].len();
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
            let player = tournament[tournament::PLAYERS]
                .members()
                .find(|p| p[player::USER_UID].as_str() == Some(&uid));
            let toss = player.and_then(|p| p[player::TOSS].as_u32()).unwrap_or(0);
            let finalist = player
                .and_then(|p| p[player::FINALIST].as_bool())
                .unwrap_or(false);
            // DQ signal is state=="Disqualified" OR an active DQ sanction — the same
            // combined signal used elsewhere; forfeits the player's own score only.
            let disqualified = player.and_then(|p| p[player::STATE].as_str())
                == Some("Disqualified")
                || has_dq_sanction(sanctions, &uid);
            let non_competing = player
                .and_then(|p| p[player::NON_COMPETING].as_bool())
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

type RankKey<'a> = (bool, f64, f64, f64, u32, &'a str);

/// GW > VP > TP > toss, excluded rows parked last. user_uid is a deterministic
/// terminal tiebreak: without it, players tied on all five come out in
/// nondeterministic HashMap order. Toss only ever orders finals candidates.
fn cmp_rank(a: RankKey, b: RankKey) -> std::cmp::Ordering {
    a.0.cmp(&b.0)
        .then(b.1.partial_cmp(&a.1).unwrap())
        .then(b.2.partial_cmp(&a.2).unwrap())
        .then(b.3.partial_cmp(&a.3).unwrap())
        .then(b.4.cmp(&a.4))
        .then(a.5.cmp(b.5))
}

fn rank_key(s: &Standing) -> RankKey<'_> {
    (
        s.disqualified || s.non_competing,
        s.gw,
        s.vp,
        s.tp,
        s.toss,
        s.user_uid.as_str(),
    )
}

fn row_rank_key(s: &JsonValue) -> RankKey<'_> {
    (
        s[standing::DISQUALIFIED].as_bool().unwrap_or(false)
            || s[standing::NON_COMPETING].as_bool().unwrap_or(false),
        s[standing::GW].as_f64().unwrap_or(0.0),
        s[standing::VP].as_f64().unwrap_or(0.0),
        s[standing::TP].as_f64().unwrap_or(0.0),
        s[standing::TOSS].as_u32().unwrap_or(0),
        s[standing::USER_UID].as_str().unwrap_or(""),
    )
}

fn sort_by_rank(standings: &mut [Standing]) {
    standings.sort_by(|a, b| cmp_rank(rank_key(a), rank_key(b)));
}

/// The same order for a sheet an importer built rather than play produced.
pub fn sort_standing_rows(rows: &mut [JsonValue]) {
    rows.sort_by(|a, b| cmp_rank(row_rank_key(a), row_rank_key(b)));
}

/// Refresh per-seat GW/TP from raw VPs plus current sanctions, so a late SA cascades.
/// State is set where a table changes and never re-judged here; `Cancelled` keeps its
/// scores untouched, since `RestoreRound` re-derives the round from them.
fn refresh_round_scoring(tournament: &mut JsonValue, sanctions: &JsonValue) {
    let effective_sas = resolve_sa_effective_rounds(tournament, sanctions);
    for r in 0..tournament[tournament::ROUNDS].len() {
        for t in 0..tournament[tournament::ROUNDS][r].len() {
            let table = &tournament[tournament::ROUNDS][r][t];
            if table[table::STATE].as_str() == Some("Cancelled") {
                continue;
            }
            let scored = table[table::STATE].as_str() == Some("Finished");
            let seating = &table[table::SEATING];
            let vps: Vec<f64> = seating
                .members()
                .map(|s| s[seat::RESULT][score::VP].as_f64().unwrap_or(0.0))
                .collect();
            let adjustments = table_sa_adjustments(seating, r, &effective_sas);
            let gws = compute_gw(&vps, &adjustments);
            let tps = compute_tp(vps.len(), &vps, &adjustments);
            let table = &mut tournament[tournament::ROUNDS][r][t];
            for i in 0..vps.len() {
                table[table::SEATING][i][seat::RESULT][score::GW] =
                    if scored { gws[i] } else { 0.0 }.into();
                table[table::SEATING][i][seat::RESULT][score::TP] =
                    if scored { tps[i] } else { 0.0 }.into();
            }
        }
    }
}

/// Guard: skips when rounds are empty, preserving VEKN-synced standings.
pub(super) fn update_standings(tournament: &mut JsonValue, sanctions: &JsonValue) {
    refresh_round_scoring(tournament, sanctions);
    if tournament[tournament::ROUNDS].is_empty() {
        return;
    }
    let standings = compute_preliminary_standings(tournament, sanctions);
    let arr: Vec<JsonValue> = standings
        .into_iter()
        .map(|s| {
            json::object! {
                standing::USER_UID => s.user_uid,
                standing::GW => s.gw,
                standing::VP => s.vp,
                standing::TP => s.tp,
                standing::TOSS => s.toss,
                standing::FINALIST => s.finalist,
                standing::DISQUALIFIED => s.disqualified,
                standing::NON_COMPETING => s.non_competing,
            }
        })
        .collect();
    tournament[tournament::STANDINGS] = JsonValue::Array(arr);
    refresh_finals_scoring(tournament, sanctions);
}

/// Re-score a Finished finals table from raw VPs + current sanctions and re-derive
/// `winner` when already set, using the same [`compute_gw_finals`] call SetScore/FinishFinals use.
fn refresh_finals_scoring(tournament: &mut JsonValue, sanctions: &JsonValue) {
    if tournament[tournament::FINALS][finals_table::STATE].as_str() != Some("Finished") {
        return;
    }
    let finals_round = tournament[tournament::ROUNDS].len();
    let effective_sas = resolve_sa_effective_rounds(tournament, sanctions);
    let seating = &tournament[tournament::FINALS][finals_table::SEATING];
    let vps: Vec<f64> = seating
        .members()
        .map(|s| s[seat::RESULT][score::VP].as_f64().unwrap_or(0.0))
        .collect();
    let seating_uids: Vec<String> = seating
        .members()
        .map(|s| s[seat::PLAYER_UID].as_str().unwrap_or("").to_string())
        .collect();
    let uid_refs: Vec<&str> = seating_uids.iter().map(String::as_str).collect();
    let adjustments = table_sa_adjustments(seating, finals_round, &effective_sas);
    let seed_order: Vec<String> = tournament[tournament::FINALS][finals_table::SEED_ORDER]
        .members()
        .filter_map(|s| s.as_str().map(String::from))
        .collect();
    let gws = compute_gw_finals(&vps, &adjustments, &uid_refs, &seed_order);
    let tps = compute_tp(vps.len(), &vps, &adjustments);
    for i in 0..vps.len() {
        tournament[tournament::FINALS][finals_table::SEATING][i][seat::RESULT][score::GW] =
            gws[i].into();
        tournament[tournament::FINALS][finals_table::SEATING][i][seat::RESULT][score::TP] =
            tps[i].into();
    }
    // Re-derive the winner only once FinishFinals set one (never crown early),
    // and never blank it (an empty derivation means an empty table).
    if !tournament[tournament::WINNER]
        .as_str()
        .unwrap_or("")
        .is_empty()
    {
        if let Some(w) = gws.iter().position(|&g| g == 1.0) {
            tournament[tournament::WINNER] = uid_refs[w].into();
        }
    }
}

fn with_placement(standing: &JsonValue, rank: usize, finalist_position: i32) -> JsonValue {
    let mut obj = standing.clone();
    obj[arg::RANK] = (rank as i32).into();
    obj[standing_row::FINALIST_POSITION] = finalist_position.into();
    obj
}

/// The DQ signal must decide first: DQ'd rows are stored zeroed, so every one of
/// them would otherwise classify as a no-show.
pub fn is_no_show(standing: &JsonValue, winner: &str) -> bool {
    !standing[standing::DISQUALIFIED].as_bool().unwrap_or(false)
        && !standing[standing::FINALIST].as_bool().unwrap_or(false)
        && standing[standing::USER_UID].as_str() != Some(winner)
        && standing[standing::GW].as_f64().unwrap_or(0.0) == 0.0
        && standing[standing::VP].as_f64().unwrap_or(0.0) == 0.0
        && standing[standing::TP].as_f64().unwrap_or(0.0) == 0.0
}

/// Reorders preliminary `standings` (must arrive sorted desc by score) into final
/// placement per §3.7.5/§3.1: `winner` is rank 1, finalists share rank 2, DQ'd/proxy/no-show excluded and appended last.
/// Stamps `finalist_position` too, 0 throughout when no row is flagged a finalist.
pub fn compute_final_standings(standings: &JsonValue, winner: &str) -> Vec<JsonValue> {
    let winner_present = !winner.is_empty()
        && standings
            .members()
            .any(|s| s[standing::USER_UID].as_str() == Some(winner));

    let final_played = standings
        .members()
        .any(|s| s[standing::FINALIST].as_bool().unwrap_or(false));

    let stamped: Vec<JsonValue> = standings
        .members()
        .map(|s| {
            let mut row = s.clone();
            row[standing_row::NO_SHOW] = is_no_show(s, winner).into();
            row
        })
        .collect();

    let mut winner_entry: Option<&JsonValue> = None;
    let mut finalists: Vec<&JsonValue> = Vec::new();
    let mut non_finalists: Vec<&JsonValue> = Vec::new();
    let mut excluded: Vec<&JsonValue> = Vec::new();
    for s in &stamped {
        if s[standing::DISQUALIFIED].as_bool().unwrap_or(false)
            || s[standing::NON_COMPETING].as_bool().unwrap_or(false)
            || s[standing_row::NO_SHOW].as_bool().unwrap_or(false)
        {
            // Never place — excluded here so they can't tie with or displace a real
            // competitor. UI renders their row via the flag, not the rank value.
            excluded.push(s);
        } else if winner_present && s[standing::USER_UID].as_str() == Some(winner) {
            winner_entry = Some(s);
        } else if s[standing::FINALIST].as_bool().unwrap_or(false) {
            finalists.push(s);
        } else {
            non_finalists.push(s);
        }
    }

    let finalist_count = winner_entry.is_some() as usize + finalists.len();

    let mut out: Vec<JsonValue> = Vec::new();
    if let Some(w) = winner_entry {
        out.push(with_placement(w, 1, if final_played { 1 } else { 0 }));
    }
    for s in &finalists {
        out.push(with_placement(s, 2, 2));
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
            (s[standing::GW].as_f64().unwrap_or(0.0) * 10.0) as i64,
            (s[standing::VP].as_f64().unwrap_or(0.0) * 10.0) as i64,
            s[standing::TP].as_i32().unwrap_or(0) as i64,
        );
        if prev_key != Some(key) {
            rank = start + idx;
            prev_key = Some(key);
        }
        out.push(with_placement(s, rank, 0));
    }

    // Ranks here just need to sort last; the value itself is never shown (UI
    // renders these rows via the flag, not the rank).
    let excluded_start = finalist_count + non_finalists.len() + 1;
    for (i, s) in excluded.iter().enumerate() {
        out.push(with_placement(s, excluded_start + i, 0));
    }
    out
}

pub fn display_standings(tournament: &JsonValue, sanctions: &JsonValue) -> Vec<JsonValue> {
    let players = &tournament[tournament::PLAYERS];
    let sheet = &tournament[tournament::STANDINGS];
    let rounds_less = tournament[tournament::ROUNDS].is_empty();
    let finals = &tournament[tournament::FINALS];
    let use_finals = !rounds_less
        && tournament[tournament::STATE].as_str() == Some("Finished")
        && !finals.is_null();

    let player_of = |uid: &str| {
        players
            .members()
            .find(|p| p[player::USER_UID].as_str() == Some(uid))
    };
    let sheet_of = |uid: &str| {
        sheet
            .members()
            .find(|s| s[standing::USER_UID].as_str() == Some(uid))
    };
    let finals_seat = |uid: &str| {
        use_finals
            .then(|| {
                finals[finals_table::SEATING]
                    .members()
                    .find(|s| s[seat::PLAYER_UID].as_str() == Some(uid))
            })
            .flatten()
    };

    let mut winner = if rounds_less || use_finals {
        tournament[tournament::WINNER]
            .as_str()
            .unwrap_or("")
            .to_string()
    } else {
        String::new()
    };
    if use_finals && winner.is_empty() {
        let mut best: Option<(&str, f64, f64)> = None;
        for seat in finals[finals_table::SEATING].members() {
            let gw = seat[seat::RESULT][score::GW].as_f64().unwrap_or(0.0);
            let vp = seat[seat::RESULT][score::VP].as_f64().unwrap_or(0.0);
            if best.is_none_or(|(_, bg, bv)| gw > bg || (gw == bg && vp > bv)) {
                best = Some((seat[seat::PLAYER_UID].as_str().unwrap_or(""), gw, vp));
            }
        }
        winner = best.map(|(uid, _, _)| uid).unwrap_or("").to_string();
    }

    let raw: Vec<(String, f64, f64, f64, u32, bool)> = if !sheet.is_empty() {
        sheet
            .members()
            .map(|s| {
                let uid = s[standing::USER_UID].as_str().unwrap_or("").to_string();
                let (toss, finalist) = if rounds_less {
                    (
                        s[standing::TOSS].as_u32().unwrap_or(0),
                        s[standing::FINALIST].as_bool().unwrap_or_else(|| {
                            player_of(&uid)
                                .and_then(|p| p[player::FINALIST].as_bool())
                                .unwrap_or(false)
                        }),
                    )
                } else {
                    (
                        player_of(&uid)
                            .and_then(|p| p[player::TOSS].as_u32())
                            .unwrap_or(0),
                        finals_seat(&uid).is_some(),
                    )
                };
                (
                    uid,
                    s[standing::GW].as_f64().unwrap_or(0.0),
                    s[standing::VP].as_f64().unwrap_or(0.0),
                    s[standing::TP].as_f64().unwrap_or(0.0),
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
                let uid = p[player::USER_UID].as_str().unwrap_or("");
                let gw = p[player::RESULT][score::GW].as_f64().unwrap_or(0.0);
                let vp = p[player::RESULT][score::VP].as_f64().unwrap_or(0.0);
                let tp = p[player::RESULT][score::TP].as_f64().unwrap_or(0.0);
                if uid.is_empty() || (gw == 0.0 && vp == 0.0 && tp == 0.0) {
                    return None;
                }
                Some((
                    uid.to_string(),
                    gw,
                    vp,
                    tp,
                    p[player::TOSS].as_u32().unwrap_or(0),
                    p[player::FINALIST].as_bool().unwrap_or(false),
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
            let disqualified = player.and_then(|p| p[player::STATE].as_str())
                == Some("Disqualified")
                || row.is_some_and(|r| r[standing::DISQUALIFIED].as_bool().unwrap_or(false))
                || has_dq_sanction(sanctions, &uid);
            let non_competing = player
                .and_then(|p| p[player::NON_COMPETING].as_bool())
                .unwrap_or(false)
                || row.is_some_and(|r| r[standing::NON_COMPETING].as_bool().unwrap_or(false));
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
                standing::USER_UID => s.user_uid.as_str(),
                standing::GW => s.gw,
                standing::VP => s.vp,
                standing::TP => s.tp,
                standing::TOSS => s.toss,
                standing::FINALIST => s.finalist,
                standing::DISQUALIFIED => s.disqualified,
                standing::NON_COMPETING => s.non_competing,
            };
            if let Some(seat) = finals_seat(&s.user_uid) {
                obj[arg::FINALS] = json::object! {
                    score::GW => seat[seat::RESULT][score::GW].as_f64().unwrap_or(0.0),
                    score::VP => seat[seat::RESULT][score::VP].as_f64().unwrap_or(0.0),
                    score::TP => seat[seat::RESULT][score::TP].as_f64().unwrap_or(0.0),
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
    let disqualified = tournament[tournament::PLAYERS].members().any(|p| {
        p[player::USER_UID].as_str() == Some(user_uid)
            && p[player::STATE].as_str() == Some("Disqualified")
    }) || has_dq_sanction(sanctions, user_uid);
    // Proxies earn no rating either (non-competing official stood in for the player).
    let non_competing = tournament[tournament::PLAYERS].members().any(|p| {
        p[player::USER_UID].as_str() == Some(user_uid)
            && p[player::NON_COMPETING].as_bool() == Some(true)
    });
    if disqualified || non_competing {
        return (0.0, 0.0);
    }

    let mut vp = 0.0;
    let mut gw = 0.0;
    if tournament[tournament::ROUNDS].is_empty() {
        for s in tournament[tournament::STANDINGS].members() {
            if s[standing::USER_UID].as_str() == Some(user_uid) {
                vp += s[standing::VP].as_f64().unwrap_or(0.0);
                gw += s[standing::GW].as_f64().unwrap_or(0.0);
                break;
            }
        }
    } else {
        let effective_sas = resolve_sa_effective_rounds(tournament, sanctions);
        for (round_index, round) in tournament[tournament::ROUNDS].members().enumerate() {
            for table in round.members() {
                if table[table::STATE].as_str() != Some("Finished") {
                    continue;
                }
                let seating = &table[table::SEATING];
                let Some(i) = seating
                    .members()
                    .position(|s| s[seat::PLAYER_UID].as_str() == Some(user_uid))
                else {
                    continue;
                };
                let vps: Vec<f64> = seating
                    .members()
                    .map(|s| s[seat::RESULT][score::VP].as_f64().unwrap_or(0.0))
                    .collect();
                let adjustments = table_sa_adjustments(seating, round_index, &effective_sas);
                vp += vps[i];
                gw += compute_gw(&vps, &adjustments)[i];
            }
        }
        vp -= sa_vp_penalty(&effective_sas, user_uid);
    }
    for seat in tournament[tournament::FINALS][finals_table::SEATING].members() {
        if seat[seat::PLAYER_UID].as_str() == Some(user_uid) {
            vp += seat[seat::RESULT][score::VP].as_f64().unwrap_or(0.0);
            gw += seat[seat::RESULT][score::GW].as_f64().unwrap_or(0.0);
        }
    }
    if tournament[tournament::FINALS].is_null()
        && tournament[tournament::WINNER].as_str() == Some(user_uid)
    {
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
                .find(|p| p[player::USER_UID].as_str() == Some(&s.user_uid))
                .and_then(|p| p[player::STATE].as_str())
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
            user_uid: s[standing::USER_UID].as_str().unwrap_or("").to_string(),
            gw: s[standing::GW].as_f64().unwrap_or(0.0),
            vp: s[standing::VP].as_f64().unwrap_or(0.0),
            tp: s[standing::TP].as_f64().unwrap_or(0.0),
            toss: s[standing::TOSS].as_u32().unwrap_or(0),
            finalist: s[standing::FINALIST].as_bool().unwrap_or(false),
            disqualified: s[standing::DISQUALIFIED].as_bool().unwrap_or(false),
            non_competing: s[standing::NON_COMPETING].as_bool().unwrap_or(false),
        })
        .collect();
    sort_by_rank(&mut rows);
    let candidates = finals_candidates(&tournament[tournament::PLAYERS], &rows);

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
        arg::ENOUGH_ROUNDS => enough_rounds,
        arg::POSSIBLE => possible,
        arg::HAS_TIES => possible && top5_has_ties(&candidates),
        arg::TIED_UIDS => JsonValue::Array(tied),
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

    fn fp_of(ranked: &[JsonValue], uid: &str) -> i32 {
        ranked
            .iter()
            .find(|s| s["user_uid"].as_str() == Some(uid))
            .unwrap_or_else(|| panic!("{uid} missing"))[standing_row::FINALIST_POSITION]
            .as_i32()
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
        assert_eq!(fp_of(&r, "p3"), 1, "winner takes the winner bonus");
        for u in ["p1", "p2", "p4", "p5"] {
            assert_eq!(fp_of(&r, u), 2, "{u} takes the finalist bonus");
        }
        for u in ["p6", "p7", "p8"] {
            assert_eq!(fp_of(&r, u), 0, "{u} takes no finalist bonus");
        }
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
        // Import artifact: a winner no final produced. Winner must still be 1st;
        // everyone else ranks from 2 by preliminary standing.
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
        assert_eq!(fp_of(&r, "w"), 0, "no final played, so no winner bonus");
        assert_eq!(fp_of(&r, "x"), 0);
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
