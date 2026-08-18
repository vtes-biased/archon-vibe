use json::JsonValue;

use crate::seating;

mod helpers;
mod parsing;
mod raffle;
mod sanctions;
mod scoring;
mod standings;
#[cfg(test)]
mod tests;
mod types;

pub use scoring::{check_table_vps, compute_gw, compute_gw_finals, compute_tp};
pub use standings::{compute_final_standings, compute_rating_vp_gw, finals_qualification};
pub use types::{ActorContext, PlayerState, SeatScore, TournamentEvent, TournamentState, VpError};

use crate::error::EngineError;
use helpers::{
    all_rounds_finished, collect_previous_rounds, count_played_rounds, count_player_rounds_played,
    find_player_index, is_deck_locked, player_exists, players_in_other_active_rounds,
    require_can_edit_results, require_organizer, require_state, require_state_or_finished,
    validate_enum,
};
use raffle::{compute_deck_public, get_raffle_pool};
use sanctions::{has_active_suspension, has_dq_sanction, table_sa_adjustments};
use standings::{
    compute_preliminary_standings, finals_candidates, top5_has_ties, toss_groups, tosses_are_total,
    update_standings,
};

/// Shared between `UpdateConfig` and `CreateTournament`.
fn validate_config_fields(config: &JsonValue) -> Result<(), EngineError> {
    if let Some(f) = config["format"].as_str() {
        validate_enum(f, &["Standard", "V5", "Limited"], "format")?;
    }
    if let Some(r) = config["rank"].as_str() {
        validate_enum(
            r,
            &["", "National Championship", "Continental Championship"],
            "rank",
        )?;
    }
    if let Some(s) = config["standings_mode"].as_str() {
        validate_enum(
            s,
            &["Private", "Cutoff", "Top 10", "Public"],
            "standings_mode",
        )?;
    }
    if let Some(d) = config["decklists_mode"].as_str() {
        validate_enum(d, &["Winner", "Finalists", "All"], "decklists_mode")?;
    }
    if config.has_key("name") {
        if let Some(n) = config["name"].as_str() {
            if n.trim().is_empty() {
                return Err(EngineError::NameRequired);
            }
        }
    }
    // self_organized_rounds implies open_rounds; reject the combo here so the
    // invariant is enforced by the engine, not just the UI form.
    if config["self_organized_rounds"].as_bool() == Some(true)
        && config.has_key("open_rounds")
        && config["open_rounds"].as_bool() == Some(false)
    {
        return Err(EngineError::SelfOrganizeNotOpenRounds);
    }
    Ok(())
}

/// None = last round (unchecked). An explicit earlier round must be LIVE — substitutes
/// join a running open-rounds pod, but finished/cancelled rounds stay closed.
fn resolve_live_round(rounds: &JsonValue, round: Option<usize>) -> Result<usize, EngineError> {
    let last = rounds.len() - 1;
    let target = round.unwrap_or(last);
    if target > last {
        return Err(EngineError::InvalidRound);
    }
    if target != last {
        let live = rounds[target]
            .members()
            .any(|t| !matches!(t["state"].as_str().unwrap_or(""), "Finished" | "Cancelled"));
        if !live {
            return Err(EngineError::RoundNotLive);
        }
    }
    Ok(target)
}

/// Ranked events forbid proxies/multideck; only Standard/Limited can be ranked. Callers
/// must pass the MERGED view (config over current tournament); pub(crate) for the online create route.
pub(crate) fn validate_rank_legality(
    format: &str,
    rank: &str,
    proxies: bool,
    multideck: bool,
) -> Result<(), EngineError> {
    if rank.is_empty() {
        return Ok(());
    }
    if !matches!(format, "Standard" | "Limited") {
        return Err(EngineError::FormatForbidsRank);
    }
    if proxies {
        return Err(EngineError::RankForbidsProxies);
    }
    if multideck {
        return Err(EngineError::RankForbidsMultideck);
    }
    Ok(())
}

/// Naive wall-clock times share the tournament's single `timezone`, so comparing the
/// fixed-width `YYYY-MM-DDTHH:MM` prefix orders them correctly despite minute-vs-second precision.
pub(crate) fn validate_finish_after_start(start: &str, finish: &str) -> Result<(), EngineError> {
    if start.is_empty() || finish.is_empty() {
        return Ok(());
    }
    fn minute(s: &str) -> &str {
        s.get(..16).unwrap_or(s)
    }
    if minute(finish) < minute(start) {
        return Err(EngineError::FinishBeforeStart);
    }
    Ok(())
}

pub fn create_tournament(config_json: &str, actor_json: &str) -> Result<String, EngineError> {
    let config = json::parse(config_json)?;
    let actor = ActorContext::from_json(&json::parse(actor_json)?)?;

    if !actor.can_manage_tournaments() {
        return Err(EngineError::CreateForbidden);
    }

    validate_config_fields(&config)?;
    validate_rank_legality(
        config["format"].as_str().unwrap_or(""),
        config["rank"].as_str().unwrap_or(""),
        config["proxies"].as_bool().unwrap_or(false),
        config["multideck"].as_bool().unwrap_or(false),
    )?;
    validate_finish_after_start(
        config["start"].as_str().unwrap_or(""),
        config["finish"].as_str().unwrap_or(""),
    )?;

    let name = config["name"].as_str().ok_or("name is required")?;
    if name.trim().is_empty() {
        return Err(EngineError::NameRequired);
    }

    let uid = config["uid"].as_str().unwrap_or("").to_string();
    let now = config["now"].as_str().unwrap_or("").to_string();

    let tournament = json::object! {
        "uid" => if uid.is_empty() { json::JsonValue::Null } else { uid.into() },
        "modified" => if now.is_empty() { json::JsonValue::Null } else { now.clone().into() },
        "name" => name,
        "format" => config["format"].as_str().unwrap_or("Standard"),
        "rank" => config["rank"].as_str().unwrap_or(""),
        "online" => config["online"].as_bool().unwrap_or(false),
        "start" => config["start"].clone(),
        "finish" => config["finish"].clone(),
        "timezone" => config["timezone"].as_str().unwrap_or(""),
        "country" => config["country"].clone(),
        "state" => "Planned",
        "organizers_uids" => json::array![actor.uid.clone()],
        "venue" => config["venue"].as_str().unwrap_or(""),
        "venue_url" => config["venue_url"].as_str().unwrap_or(""),
        "address" => config["address"].as_str().unwrap_or(""),
        "map_url" => config["map_url"].as_str().unwrap_or(""),
        "proxies" => config["proxies"].as_bool().unwrap_or(false),
        "multideck" => config["multideck"].as_bool().unwrap_or(false),
        "decklist_required" => config["decklist_required"].as_bool().unwrap_or(false),
        "description" => config["description"].as_str().unwrap_or(""),
        "standings_mode" => config["standings_mode"].as_str().unwrap_or("Private"),
        "decklists_mode" => config["decklists_mode"].as_str().unwrap_or("Winner"),
        "max_rounds" => config["max_rounds"].as_u32().unwrap_or(0),
        // Soft cap: UI-side warnings only (0 = none). Registration is never blocked.
        "max_players" => config["max_players"].as_u32().unwrap_or(0),
        "open_rounds" => config["open_rounds"].as_bool().unwrap_or(false),
        "self_organized_rounds" => config["self_organized_rounds"].as_bool().unwrap_or(false),
        "league_uid" => config["league_uid"].clone(),
        "round_time" => config["round_time"].as_u32().unwrap_or(0),
        "finals_time" => config["finals_time"].as_u32().unwrap_or(0),
        "players" => json::array![],
        "rounds" => json::array![],
        "finals" => json::JsonValue::Null,
        "winner" => "",
        "standings" => json::array![],
    };

    Ok(tournament.dump())
}

pub fn process_tournament_event(
    tournament_json: &str,
    event_json: &str,
    actor_json: &str,
    sanctions_json: &str,
    decks_json: &str,
) -> Result<String, EngineError> {
    let mut tournament = json::parse(tournament_json)?;
    let event_value = json::parse(event_json)?;
    let actor_value = json::parse(actor_json)?;
    let sanctions = json::parse(sanctions_json)?;
    let decks = json::parse(decks_json)?;

    let event = TournamentEvent::from_json(&event_value)?;
    let actor = ActorContext::from_json(&actor_value)?;

    let mut deck_ops = JsonValue::new_array();
    apply_event(
        &mut tournament,
        &event,
        &actor,
        &sanctions,
        &decks,
        &mut deck_ops,
    )?;

    let result = json::object! {
        "tournament" => tournament,
        "deck_ops" => deck_ops,
    };
    Ok(result.dump())
}

/// Sanction issue/lift/delete flows aren't `TournamentEvent`s, so they call this
/// directly for the same recompute every event ends with. No-op on empty rounds.
pub fn update_standings_json(
    tournament_json: &str,
    sanctions_json: &str,
) -> Result<String, EngineError> {
    let mut tournament = json::parse(tournament_json)?;
    let sanctions = json::parse(sanctions_json)?;
    update_standings(&mut tournament, &sanctions);
    Ok(tournament.dump())
}

/// Mirrors SetScore's SA cascade exactly, so live UI previews never drift from
/// persisted results. `round == rounds.len()` is the finals sentinel (`table` ignored).
pub fn preview_scores_json(config_json: &str) -> Result<String, EngineError> {
    let config = json::parse(config_json)?;
    let tournament = &config["tournament"];
    let sanctions = &config["sanctions"];
    let round = config["round"]
        .as_usize()
        .ok_or_else(|| EngineError::internal("round required"))?;
    let rounds_len = tournament["rounds"].len();
    let is_finals = round >= rounds_len;
    let table = if is_finals {
        &tournament["finals"]
    } else {
        let table_idx = config["table"]
            .as_usize()
            .ok_or_else(|| EngineError::internal("table required"))?;
        &tournament["rounds"][round][table_idx]
    };
    let seating = &table["seating"];
    let vps: Vec<f64> = config["vps"]
        .members()
        .map(|v| v.as_f64().unwrap_or(0.0))
        .collect();
    if seating.is_empty() || vps.len() != seating.len() {
        return Err(EngineError::internal("vps/seating length mismatch"));
    }
    let effective_sas = sanctions::resolve_sa_effective_rounds(tournament, sanctions);
    let adjustments = table_sa_adjustments(seating, round, &effective_sas);
    let gws = if is_finals {
        let seating_uids: Vec<&str> = seating
            .members()
            .map(|s| s["player_uid"].as_str().unwrap_or(""))
            .collect();
        let seed_order: Vec<String> = table["seed_order"]
            .members()
            .filter_map(|s| s.as_str().map(|v| v.to_string()))
            .collect();
        compute_gw_finals(&vps, &adjustments, &seating_uids, &seed_order)
    } else {
        compute_gw(&vps, &adjustments)
    };
    let tps = compute_tp(seating.len(), &vps, &adjustments);
    Ok(json::object! {
        "gw" => JsonValue::Array(gws.into_iter().map(Into::into).collect()),
        "tp" => JsonValue::Array(tps.into_iter().map(Into::into).collect()),
    }
    .dump())
}

fn apply_event(
    tournament: &mut JsonValue,
    event: &TournamentEvent,
    actor: &ActorContext,
    sanctions: &JsonValue,
    decks: &JsonValue,
    deck_ops: &mut JsonValue,
) -> Result<(), EngineError> {
    let state = TournamentState::from_str(tournament["state"].as_str().unwrap_or("Planned"))
        .ok_or("Invalid tournament state")?;

    match event {
        TournamentEvent::OpenRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Planned)?;
            tournament["state"] = "Registration".into();
            Ok(())
        }

        TournamentEvent::CloseRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Registration)?;
            tournament["state"] = "Waiting".into();
            Ok(())
        }

        TournamentEvent::CancelRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Registration)?;
            tournament["state"] = "Planned".into();
            Ok(())
        }

        TournamentEvent::ReopenRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Waiting)?;
            tournament["state"] = "Registration".into();
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Checked-in") {
                    players[i]["state"] = "Registered".into();
                }
            }
            Ok(())
        }

        TournamentEvent::ReopenTournament => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Finished)?;
            tournament["state"] = "Waiting".into();
            // winner is "" (not null): the backend Tournament model types it `str`
            // (""=no winner), so a null fails msgspec validation and 500s the action.
            tournament["finals"] = json::Null;
            tournament["winner"] = "".into();
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Finished") {
                    players[i]["state"] = "Checked-in".into();
                }
                players[i]["finalist"] = false.into();
                // Disqualified players stay Disqualified (no reset)
            }
            update_standings(tournament, sanctions);
            for d in decks.members() {
                let deck_uid = d["uid"].as_str().unwrap_or("");
                if !deck_uid.is_empty() {
                    let op = json::object! {
                        "op" => "set_public",
                        "deck_uid" => deck_uid,
                        "public" => false,
                    };
                    let _ = deck_ops.push(op);
                }
            }
            Ok(())
        }

        TournamentEvent::Register {
            user_uid,
            vekn_id,
            display_name,
        } => {
            require_state(state, TournamentState::Registration)?;

            if vekn_id.as_ref().is_none_or(|v| v.is_empty()) {
                return Err(EngineError::VeknIdRequired);
            }

            if player_exists(&tournament["players"], user_uid) {
                return Err(EngineError::AlreadyRegistered);
            }

            if has_dq_sanction(sanctions, user_uid) {
                return Err(EngineError::PlayerDisqualified);
            }
            if has_active_suspension(sanctions, user_uid, &actor.now) {
                return Err(EngineError::PlayerSuspended);
            }

            let mut player = json::object! {
                user_uid: user_uid.as_str(),
                state: "Registered",
                payment_status: "Pending",
                toss: 0,
                result: { gw: 0, vp: 0.0, tp: 0 },
                finalist: false,
                non_competing: false,
            };
            if let Some(dn) = display_name {
                if !dn.is_empty() {
                    player["display_name"] = dn.as_str().into();
                }
            }
            tournament["players"].push(player)?;
            Ok(())
        }

        TournamentEvent::Unregister { user_uid } => {
            require_state(state, TournamentState::Registration)?;

            if actor.uid != *user_uid {
                return Err(EngineError::UnregisterOnlySelf);
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, user_uid).ok_or(EngineError::PlayerNotFound)?;
            players.array_remove(idx);
            Ok(())
        }

        TournamentEvent::AddPlayer {
            user_uid,
            vekn_id,
            display_name,
        } => {
            require_organizer(actor)?;
            if state != TournamentState::Planned
                && state != TournamentState::Registration
                && state != TournamentState::Waiting
                && state != TournamentState::Playing
                && state != TournamentState::Finished
            {
                return Err(EngineError::CannotAddPlayers);
            }

            if vekn_id.as_ref().is_none_or(|v| v.is_empty()) {
                return Err(EngineError::VeknIdRequired);
            }

            if player_exists(&tournament["players"], user_uid) {
                return Err(EngineError::AlreadyRegistered);
            }

            if has_dq_sanction(sanctions, user_uid) {
                return Err(EngineError::PlayerDisqualified);
            }
            if has_active_suspension(sanctions, user_uid, &actor.now) {
                return Err(EngineError::PlayerSuspended);
            }

            let auto_checkin = state == TournamentState::Waiting;
            let player_state = if auto_checkin {
                "Checked-in"
            } else {
                "Registered"
            };
            let mut player = json::object! {
                user_uid: user_uid.as_str(),
                state: player_state,
                payment_status: "Pending",
                toss: 0,
                result: { gw: 0, vp: 0.0, tp: 0 },
                finalist: false,
                non_competing: false,
            };
            if let Some(dn) = display_name {
                if !dn.is_empty() {
                    player["display_name"] = dn.as_str().into();
                }
            }
            if auto_checkin
                && tournament["decklist_required"].as_bool().unwrap_or(false)
                && !decks
                    .members()
                    .any(|d| d["user_uid"].as_str() == Some(user_uid.as_str()))
            {
                player["missing_decklist"] = true.into();
            }
            tournament["players"].push(player)?;
            Ok(())
        }

        TournamentEvent::RemovePlayer { user_uid } => {
            require_organizer(actor)?;
            if state != TournamentState::Planned
                && state != TournamentState::Registration
                && state != TournamentState::Waiting
                && state != TournamentState::Finished
            {
                return Err(EngineError::CannotRemovePlayers);
            }
            if !tournament["rounds"].is_empty() {
                return Err(EngineError::UseDropOut);
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, user_uid).ok_or(EngineError::PlayerNotFound)?;
            players.array_remove(idx);
            Ok(())
        }

        TournamentEvent::DropOut { player_uid } => {
            if state != TournamentState::Waiting && state != TournamentState::Playing {
                return Err(EngineError::CannotDropOut);
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, player_uid).ok_or(EngineError::PlayerNotFound)?;
            let player_state = PlayerState::from_str(players[idx]["state"].as_str().unwrap_or(""))
                .ok_or("Invalid player state")?;

            if player_state == PlayerState::Finished {
                return Err(EngineError::PlayerAlreadyFinished);
            }

            if !actor.is_organizer && actor.uid != *player_uid {
                return Err(EngineError::DropOutForbidden);
            }

            players[idx]["state"] = "Finished".into();
            Ok(())
        }

        TournamentEvent::CheckIn {
            player_uid,
            vekn_id,
            display_name,
        } => {
            // The door stays open mid-round — check-in never seats, that's a
            // separate organizer action.
            if !matches!(
                state,
                TournamentState::Waiting | TournamentState::Playing | TournamentState::Finished
            ) {
                return Err(EngineError::WrongState {
                    expected: TournamentState::Waiting.as_str().to_string(),
                    current: state.as_str().to_string(),
                });
            }

            if !actor.is_organizer && actor.uid != *player_uid {
                return Err(EngineError::CheckInForbidden);
            }

            let idx = match find_player_index(&tournament["players"], player_uid) {
                Some(idx) => idx,
                None => {
                    if state != TournamentState::Waiting && state != TournamentState::Playing {
                        return Err(EngineError::PlayerNotFound);
                    }
                    if vekn_id.as_ref().is_none_or(|v| v.is_empty()) {
                        return Err(EngineError::VeknIdRequired);
                    }
                    if has_dq_sanction(sanctions, player_uid) {
                        return Err(EngineError::PlayerDisqualified);
                    }
                    if has_active_suspension(sanctions, player_uid, &actor.now) {
                        return Err(EngineError::PlayerSuspended);
                    }
                    let mut player = json::object! {
                        user_uid: player_uid.as_str(),
                        state: "Registered",
                        payment_status: "Pending",
                        toss: 0,
                        result: { gw: 0, vp: 0.0, tp: 0 },
                        finalist: false,
                        non_competing: false,
                    };
                    if let Some(dn) = display_name {
                        if !dn.is_empty() {
                            player["display_name"] = dn.as_str().into();
                        }
                    }
                    tournament["players"].push(player)?;
                    tournament["players"].len() - 1
                }
            };

            if tournament["players"][idx]["state"].as_str() == Some("Disqualified") {
                return Err(EngineError::PlayerDisqualified);
            }

            if has_dq_sanction(sanctions, player_uid) {
                return Err(EngineError::PlayerDisqualified);
            }
            if has_active_suspension(sanctions, player_uid, &actor.now) {
                return Err(EngineError::PlayerSuspended);
            }

            // The bot resends display_name on every check-in; refresh it here so a
            // player already on the roster doesn't keep a stale registered name.
            if let Some(dn) = display_name {
                if !dn.is_empty() {
                    tournament["players"][idx]["display_name"] = dn.as_str().into();
                }
            }

            // Open rounds: a player at their per-player cap can't check in for a new round — but a
            // capped DROP-OUT being reinstated returns to Completed (finals-eligible), not rejected.
            let was_finished = tournament["players"][idx]["state"].as_str() == Some("Finished");
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let at_cap =
                max_rounds > 0 && count_player_rounds_played(tournament, player_uid) >= max_rounds;
            if at_cap && !was_finished {
                return Err(EngineError::PlayerReachedMaxRounds);
            }
            if at_cap {
                // Reinstating a capped drop-out: done with prelims, finals-eligible, no new round.
                tournament["players"][idx]["state"] = "Completed".into();
                return Ok(());
            }

            let missing_decklist = tournament["decklist_required"].as_bool().unwrap_or(false) && {
                let pk = player_uid.as_str();
                !decks.members().any(|d| d["user_uid"].as_str() == Some(pk))
            };

            // A drop-out reinstated mid-round keeps the seat they never left.
            let seated_live = tournament["rounds"].members().any(|round| {
                round.members().any(|t| {
                    t["state"].as_str() != Some("Finished")
                        && t["seating"]
                            .members()
                            .any(|s| s["player_uid"].as_str() == Some(player_uid.as_str()))
                })
            });
            tournament["players"][idx]["state"] = if was_finished && seated_live {
                "Playing"
            } else {
                "Checked-in"
            }
            .into();
            if missing_decklist {
                tournament["players"][idx]["missing_decklist"] = true.into();
            }

            Ok(())
        }

        TournamentEvent::CheckOut { player_uid } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            let idx = find_player_index(&tournament["players"], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;

            if tournament["players"][idx]["state"].as_str() != Some("Checked-in") {
                return Err(EngineError::PlayerNotCheckedIn);
            }

            tournament["players"][idx]["state"] = if state == TournamentState::Finished {
                "Finished"
            } else {
                "Registered"
            }
            .into();
            Ok(())
        }

        TournamentEvent::CheckInAll => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            // Never re-arm a player already at their per-player cap —
            // Registered/Finished-at-cap can arise after a reopen or a post-cap drop-out.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let capped: std::collections::HashSet<String> = if max_rounds > 0 {
                tournament["players"]
                    .members()
                    .filter_map(|p| p["user_uid"].as_str().map(String::from))
                    .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                    .collect()
            } else {
                std::collections::HashSet::new()
            };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                let ps = players[i]["state"].as_str().unwrap_or("");
                if ps == "Disqualified" {
                    continue;
                }
                let uid = players[i]["user_uid"].as_str().unwrap_or("");
                if has_dq_sanction(sanctions, uid)
                    || has_active_suspension(sanctions, uid, &actor.now)
                {
                    continue;
                }
                if capped.contains(uid) {
                    continue;
                }
                if ps == "Registered" || (state == TournamentState::Finished && ps == "Finished") {
                    players[i]["state"] = "Checked-in".into();
                }
            }
            Ok(())
        }

        TournamentEvent::ResetCheckIn => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Checked-in") {
                    players[i]["state"] = if state == TournamentState::Finished {
                        "Finished"
                    } else {
                        "Registered"
                    }
                    .into();
                }
            }
            Ok(())
        }

        TournamentEvent::SetPaymentStatus { player_uid, status } => {
            require_organizer(actor)?;
            match status.as_str() {
                "Pending" | "Paid" | "Refunded" | "Cancelled" => {}
                _ => {
                    return Err(EngineError::internal(format!(
                        "Invalid payment status: {}",
                        status
                    )))
                }
            }
            let idx = find_player_index(&tournament["players"], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            tournament["players"][idx]["payment_status"] = status.as_str().into();
            Ok(())
        }

        TournamentEvent::SetNonCompeting {
            player_uid,
            non_competing,
        } => {
            require_organizer(actor)?;
            // Blocked after finals are seeded or the tournament is finished, so a
            // proxied↔competing flip can't rewrite a concluded result; mid-prelim toggling is the use case.
            if !tournament["finals"].is_null() || state == TournamentState::Finished {
                return Err(EngineError::CannotSetNonCompeting);
            }
            let idx = find_player_index(&tournament["players"], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            tournament["players"][idx]["non_competing"] = (*non_competing).into();
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::MarkAllPaid => {
            require_organizer(actor)?;
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["payment_status"].as_str() == Some("Pending") {
                    players[i]["payment_status"] = "Paid".into();
                }
            }
            Ok(())
        }

        TournamentEvent::StartRound {
            seating: submitted_seating,
        } => {
            require_organizer(actor)?;
            let is_online = tournament["online"].as_bool().unwrap_or(false);
            if is_online {
                // Online: allow starting a round while Playing (parallel rounds)
                if state != TournamentState::Waiting
                    && state != TournamentState::Playing
                    && state != TournamentState::Finished
                {
                    return Err(EngineError::WrongState {
                        expected: "Waiting".to_string(),
                        current: state.as_str().to_string(),
                    });
                }
            } else {
                require_state_or_finished(state, TournamentState::Waiting)?;
            }

            if !tournament["finals"].is_null() {
                return Err(EngineError::PrelimAfterFinals);
            }

            // max_rounds is a per-player cap, not tournament-wide — more rounds may
            // run for players who haven't hit it yet.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);

            // Playing counts too, for online parallel rounds.
            let checked_in: Vec<String> = tournament["players"]
                .members()
                .filter(|p| {
                    let s = p["state"].as_str();
                    s == Some("Checked-in") || (is_online && s == Some("Playing"))
                })
                .filter_map(|p| p["user_uid"].as_str().map(|s| s.to_string()))
                .filter(|uid| {
                    max_rounds == 0 || count_player_rounds_played(tournament, uid) < max_rounds
                })
                .collect();

            let n = checked_in.len();
            if n < 4 {
                return Err(EngineError::NotEnoughPlayers);
            }

            let previous_rounds = collect_previous_rounds(tournament);

            // Handles awkward counts (6, 7, 11) via staggered seating.
            let players_to_seat = seating::select_players_for_round(&checked_in, &previous_rounds);

            let new_round: Vec<Vec<String>> = if let Some(submitted) = submitted_seating {
                let seat_set: std::collections::HashSet<&str> =
                    players_to_seat.iter().map(|s| s.as_str()).collect();
                let mut seen: std::collections::HashSet<&str> = std::collections::HashSet::new();
                for table in submitted.iter() {
                    if table.len() < 4 || table.len() > 5 {
                        return Err(EngineError::InvalidTableSize { size: table.len() });
                    }
                    for uid in table {
                        if !seat_set.contains(uid.as_str()) {
                            return Err(EngineError::PlayerNotInSubset {
                                player: uid.to_string(),
                            });
                        }
                        if !seen.insert(uid.as_str()) {
                            return Err(EngineError::DuplicatePlayer);
                        }
                    }
                }
                if seen.len() != players_to_seat.len() {
                    return Err(EngineError::SeatingIncomplete);
                }
                submitted.clone()
            } else {
                let seed = seating::seed_for_round(
                    tournament["uid"].as_str().unwrap_or(""),
                    previous_rounds.len(),
                );
                let (computed, _score) =
                    seating::compute_next_round(&players_to_seat, &previous_rounds, seed)?;
                computed
            };

            let tables: Vec<JsonValue> = new_round
                .iter()
                .map(|table| {
                    let seating: Vec<JsonValue> = table
                        .iter()
                        .map(|player_uid| {
                            json::object! {
                                player_uid: player_uid.as_str(),
                                result: { gw: 0, vp: 0.0, tp: 0 },
                                judge_uid: "",
                            }
                        })
                        .collect();
                    json::object! {
                        seating: seating,
                        state: "In Progress",
                        override: json::Null,
                    }
                })
                .collect();

            tournament["rounds"].push(JsonValue::Array(tables))?;
            if state != TournamentState::Finished {
                tournament["state"] = "Playing".into();
            }

            let seated_uids: std::collections::HashSet<String> = new_round
                .iter()
                .flat_map(|table| table.iter().cloned())
                .collect();

            // Only round 1 of a standard tournament withdraws no-show Registered players
            // (reinstatable via CheckIn/SeatPlayer); later and open rounds leave them untouched.
            let prior_real_rounds = (0..tournament["rounds"].len().saturating_sub(1))
                .filter(|&r| {
                    tournament["rounds"][r]
                        .members()
                        .any(|t| t["state"].as_str() != Some("Cancelled"))
                })
                .count();
            let open_rounds = tournament["open_rounds"].as_bool().unwrap_or(false);
            let drop_no_shows = prior_real_rounds == 0 && !open_rounds;

            let players = &mut tournament["players"];
            for i in 0..players.len() {
                match players[i]["state"].as_str() {
                    Some("Checked-in") => {
                        if let Some(uid) = players[i]["user_uid"].as_str() {
                            if seated_uids.contains(uid) {
                                players[i]["state"] = "Playing".into();
                            }
                        }
                    }
                    Some("Registered") if drop_no_shows => players[i]["state"] = "Finished".into(),
                    _ => {}
                }
            }

            Ok(())
        }

        TournamentEvent::SelfOrganizeRound { player_uids } => {
            // NOT organizer-gated: integrity gate is registration only — collusion risk
            // accepted, mitigated by organizer veto (FinishRound/CancelRound/Override).
            if !tournament["self_organized_rounds"]
                .as_bool()
                .unwrap_or(false)
            {
                return Err(EngineError::SelfOrganizeDisabled);
            }
            // 0 == no per-player cap; only enforced below when a cap is set.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            // Same state rule as an online parallel StartRound: seat while Waiting/Playing.
            if state != TournamentState::Waiting && state != TournamentState::Playing {
                return Err(EngineError::WrongState {
                    expected: "Waiting".to_string(),
                    current: state.as_str().to_string(),
                });
            }
            if !tournament["finals"].is_null() {
                return Err(EngineError::PrelimAfterFinals);
            }
            if player_uids.len() < 4 || player_uids.len() > 5 {
                return Err(EngineError::InvalidTableSize {
                    size: player_uids.len(),
                });
            }
            let mut seen: std::collections::HashSet<&str> = std::collections::HashSet::new();
            for uid in player_uids {
                if !seen.insert(uid.as_str()) {
                    return Err(EngineError::DuplicatePlayer);
                }
            }
            if !player_uids.iter().any(|uid| uid == &actor.uid) {
                return Err(EngineError::SelfOrganizeNotSeated);
            }
            // Reject Playing (already in a concurrent pod), Completed/Finished,
            // Disqualified, and at-cap players.
            for uid in player_uids {
                let p = tournament["players"]
                    .members()
                    .find(|p| p["user_uid"].as_str() == Some(uid.as_str()))
                    .ok_or(EngineError::NotRegistered)?;
                let pstate = p["state"].as_str().unwrap_or("");
                if pstate == "Disqualified" {
                    return Err(EngineError::PlayerDisqualified);
                }
                if pstate != "Registered" && pstate != "Checked-in" {
                    return Err(EngineError::SelfOrganizeIneligible {
                        player: uid.clone(),
                    });
                }
                if max_rounds > 0 && count_player_rounds_played(tournament, uid) >= max_rounds {
                    return Err(EngineError::PlayerReachedMaxRounds);
                }
            }
            let previous_rounds = collect_previous_rounds(tournament);
            let seed = seating::seed_for_round(
                tournament["uid"].as_str().unwrap_or(""),
                previous_rounds.len(),
            );
            let (computed, _score) =
                seating::compute_next_round(player_uids, &previous_rounds, seed)?;
            // Stamp `organized_by` for the audit trail.
            let tables: Vec<JsonValue> = computed
                .iter()
                .map(|table| {
                    let seating: Vec<JsonValue> = table
                        .iter()
                        .map(|player_uid| {
                            json::object! {
                                player_uid: player_uid.as_str(),
                                result: { gw: 0, vp: 0.0, tp: 0 },
                                judge_uid: "",
                            }
                        })
                        .collect();
                    json::object! {
                        seating: seating,
                        state: "In Progress",
                        override: json::Null,
                        organized_by: actor.uid.as_str(),
                    }
                })
                .collect();
            tournament["rounds"].push(JsonValue::Array(tables))?;
            tournament["state"] = "Playing".into();
            // Seat ONLY the chosen players; every other Registered player stays available
            // (unlike StartRound, which withdraws unseated Registered players).
            let seated: std::collections::HashSet<&str> =
                player_uids.iter().map(|s| s.as_str()).collect();
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if let Some(uid) = players[i]["user_uid"].as_str() {
                    if seated.contains(uid) {
                        players[i]["state"] = "Playing".into();
                    }
                }
            }
            Ok(())
        }

        TournamentEvent::FinishRound { round } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundToFinish);
            }

            let target_round_idx = round.unwrap_or(rounds.len() - 1);
            if target_round_idx >= rounds.len() {
                return Err(EngineError::InvalidRound);
            }

            let target_round = &rounds[target_round_idx];

            let unfinished: Vec<usize> = target_round
                .members()
                .enumerate()
                .filter(|(_, t)| t["state"].as_str() != Some("Finished"))
                .map(|(i, _)| i)
                .collect();

            if !unfinished.is_empty() {
                return Err(EngineError::TablesNotFinished {
                    tables: unfinished
                        .iter()
                        .map(|i| (i + 1).to_string())
                        .collect::<Vec<_>>()
                        .join(", "),
                });
            }

            let target_state = if state == TournamentState::Finished {
                "Finished"
            } else {
                "Checked-in"
            };
            let still_playing = players_in_other_active_rounds(tournament, target_round_idx);
            // A player who just reached their per-player cap retires to Completed
            // instead of being re-armed as Checked-in.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let maxed: std::collections::HashSet<String> =
                if max_rounds > 0 && state != TournamentState::Finished {
                    tournament["players"]
                        .members()
                        .filter_map(|p| p["user_uid"].as_str().map(String::from))
                        .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                        .collect()
                } else {
                    std::collections::HashSet::new()
                };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Playing") {
                    if let Some(uid) = players[i]["user_uid"].as_str() {
                        if !still_playing.contains(uid) {
                            players[i]["state"] = if maxed.contains(uid) {
                                "Completed"
                            } else {
                                target_state
                            }
                            .into();
                        }
                    }
                }
            }

            if state != TournamentState::Finished && all_rounds_finished(tournament) {
                tournament["state"] = "Waiting".into();
            }
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::CancelRound { round } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let len = tournament["rounds"].len();
            if len == 0 {
                return Err(EngineError::NoRoundToCancel);
            }
            let target_idx = round.unwrap_or(len - 1);
            if target_idx >= len {
                return Err(EngineError::InvalidRound);
            }

            if target_idx == len - 1 {
                // Last round: hard-remove — no later round's index can shift.
                tournament["rounds"].array_remove(len - 1);
                loop {
                    let n = tournament["rounds"].len();
                    if n == 0 {
                        break;
                    }
                    let last = &tournament["rounds"][n - 1];
                    if last.is_empty()
                        || !last
                            .members()
                            .all(|t| t["state"].as_str() == Some("Cancelled"))
                    {
                        break;
                    }
                    tournament["rounds"].array_remove(n - 1);
                }
            } else {
                // Soft-cancel: mark tables Cancelled, keep the slot — a mid-array removal
                // would shift deck.round / standings_adjustment.round_number, which are index-tagged.
                let r = &mut tournament["rounds"][target_idx];
                for i in 0..r.len() {
                    r[i]["state"] = "Cancelled".into();
                }
            }

            // After a hard-remove, exclude_round=len-1 no longer exists, so this checks
            // ALL remaining rounds; after a soft-cancel it skips the now-Cancelled tables.
            let target_state = if state == TournamentState::Finished {
                "Finished"
            } else {
                "Checked-in"
            };
            let still_playing = players_in_other_active_rounds(tournament, target_idx);
            // Cancelling a round lowers per-player counts; re-arm any Completed (capped)
            // player now back under their cap so they aren't stranded.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let rearm: std::collections::HashSet<String> =
                if max_rounds > 0 && state != TournamentState::Finished {
                    tournament["players"]
                        .members()
                        .filter(|p| p["state"].as_str() == Some("Completed"))
                        .filter_map(|p| p["user_uid"].as_str().map(String::from))
                        .filter(|uid| count_player_rounds_played(tournament, uid) < max_rounds)
                        .collect()
                } else {
                    std::collections::HashSet::new()
                };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                let st = players[i]["state"].as_str();
                let uid = players[i]["user_uid"].as_str().map(String::from);
                if st == Some("Playing") {
                    if let Some(uid) = uid {
                        if !still_playing.contains(&uid) {
                            players[i]["state"] = target_state.into();
                        }
                    }
                } else if st == Some("Completed") {
                    if let Some(uid) = uid {
                        if rearm.contains(&uid) {
                            players[i]["state"] = target_state.into();
                        }
                    }
                }
            }

            if state != TournamentState::Finished
                && (all_rounds_finished(tournament) || tournament["rounds"].is_empty())
            {
                tournament["state"] = "Waiting".into();
            }
            // else: stay Playing (other rounds still in progress)
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::RestoreRound { round } => {
            require_organizer(actor)?;
            // Prelim-phase correction only: allowed while Playing/Waiting and before
            // finals are seeded — deliberate asymmetry: CancelRound also accepts Finished, restore refuses it.
            if state != TournamentState::Playing && state != TournamentState::Waiting {
                return Err(EngineError::WrongState {
                    expected: TournamentState::Playing.as_str().to_string(),
                    current: state.as_str().to_string(),
                });
            }
            if !tournament["finals"].is_null() {
                return Err(EngineError::PrelimAfterFinals);
            }

            let len = tournament["rounds"].len();
            let target_idx = round.ok_or(EngineError::InvalidRound)?;
            if target_idx >= len {
                return Err(EngineError::InvalidRound);
            }
            // Only a fully-Cancelled round is restorable (the last round is hard-
            // removed on cancel, so any Cancelled round is a non-last soft-cancel).
            if tournament["rounds"][target_idx].is_empty()
                || !tournament["rounds"][target_idx]
                    .members()
                    .all(|t| t["state"].as_str() == Some("Cancelled"))
            {
                return Err(EngineError::RoundNotCancelled);
            }

            let seated: std::collections::HashSet<String> = tournament["rounds"][target_idx]
                .members()
                .flat_map(|t| t["seating"].members())
                .filter_map(|s| s["player_uid"].as_str().map(String::from))
                .collect();

            // All-or-nothing: reject the whole restore if any seated player can no longer
            // be reinstated. Runs before any mutation; the cap check sees this round still Cancelled.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            for uid in &seated {
                let pstate = tournament["players"]
                    .members()
                    .find(|p| p["user_uid"].as_str() == Some(uid.as_str()))
                    .and_then(|p| p["state"].as_str());
                if matches!(pstate, Some("Disqualified") | Some("Finished")) {
                    return Err(EngineError::CannotRestoreRound);
                }
                if max_rounds > 0 && count_player_rounds_played(tournament, uid) >= max_rounds {
                    return Err(EngineError::CannotRestoreRound);
                }
            }

            // Same derivation path as Unoverride: override forces Finished, otherwise
            // check_table_vps maps complete+valid -> Finished, partial -> In Progress, else Invalid.
            let mut round_is_live = false;
            {
                let r = &mut tournament["rounds"][target_idx];
                for i in 0..r.len() {
                    let new_state = if !r[i]["override"].is_null() {
                        "Finished"
                    } else {
                        let size = r[i]["seating"].len();
                        let vps: Vec<f64> = (0..size)
                            .map(|j| r[i]["seating"][j]["result"]["vp"].as_f64().unwrap_or(0.0))
                            .collect();
                        match check_table_vps(&vps) {
                            Some(VpError::IncompleteTotal) => "In Progress",
                            Some(_) => "Invalid",
                            None => "Finished",
                        }
                    };
                    if new_state != "Finished" {
                        round_is_live = true;
                    }
                    r[i]["state"] = new_state.into();
                }
            }

            // A seated player at cap on a round that re-derived to fully Finished
            // retires to Completed, mirroring FinishRound.
            let capped: std::collections::HashSet<String> = if max_rounds > 0 {
                seated
                    .iter()
                    .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                    .cloned()
                    .collect()
            } else {
                std::collections::HashSet::new()
            };

            // Validation above guarantees every seat is reinstatable; the only one left
            // untouched is a player already Playing in another live round.
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                let uid = match players[i]["user_uid"].as_str() {
                    Some(u) => u.to_string(),
                    None => continue,
                };
                if !seated.contains(&uid) {
                    continue;
                }
                if players[i]["state"].as_str() == Some("Playing") {
                    continue;
                }
                players[i]["state"] = if round_is_live {
                    "Playing"
                } else if capped.contains(&uid) {
                    "Completed"
                } else {
                    "Checked-in"
                }
                .into();
            }

            if round_is_live {
                tournament["state"] = "Playing".into();
            } else if all_rounds_finished(tournament) {
                tournament["state"] = "Waiting".into();
            }
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::SwapSeats {
            round,
            table1,
            seat1,
            table2,
            seat2,
        } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            // Finals sentinel: round == rounds.len() && table1 == 0 && table2 == 0
            let is_finals = *round == tournament["rounds"].len()
                && !tournament["finals"].is_null()
                && *table1 == 0
                && *table2 == 0;

            if is_finals {
                let seating = &mut tournament["finals"]["seating"];
                if *seat1 >= seating.len() || *seat2 >= seating.len() {
                    return Err(EngineError::InvalidSeat);
                }
                let uid1 = seating[*seat1]["player_uid"]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                let uid2 = seating[*seat2]["player_uid"]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                seating[*seat1]["player_uid"] = uid2.as_str().into();
                seating[*seat2]["player_uid"] = uid1.as_str().into();
            } else {
                let rounds = &mut tournament["rounds"];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                let round_tables = &mut rounds[*round];
                if *table1 >= round_tables.len() || *table2 >= round_tables.len() {
                    return Err(EngineError::InvalidTable);
                }
                if *seat1 >= round_tables[*table1]["seating"].len()
                    || *seat2 >= round_tables[*table2]["seating"].len()
                {
                    return Err(EngineError::InvalidSeat);
                }
                let uid1 = round_tables[*table1]["seating"][*seat1]["player_uid"]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                let uid2 = round_tables[*table2]["seating"][*seat2]["player_uid"]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                round_tables[*table1]["seating"][*seat1]["player_uid"] = uid2.as_str().into();
                round_tables[*table2]["seating"][*seat2]["player_uid"] = uid1.as_str().into();
            }

            // Recompute: no later FinishRound refreshes this in Finished state. No-op
            // for the finals branch — prelim standings read from rounds only.
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::AlterSeating { round, seating } => {
            require_organizer(actor)?;
            if state != TournamentState::Playing
                && state != TournamentState::Finished
                && state != TournamentState::Waiting
            {
                return Err(EngineError::CannotAlterSeating);
            }

            let rounds_len = tournament["rounds"].len();
            let is_finals = *round == rounds_len && !tournament["finals"].is_null();

            {
                let all_uids: Vec<&String> = seating.iter().flat_map(|t| t.iter()).collect();
                let unique: std::collections::HashSet<&String> = all_uids.iter().copied().collect();
                if all_uids.len() != unique.len() {
                    return Err(EngineError::DuplicatePlayer);
                }
            }

            if is_finals {
                let finals = &mut tournament["finals"]["seating"];
                if seating.len() != 1 {
                    return Err(EngineError::FinalsOneTable);
                }
                let new_players = &seating[0];
                if new_players.len() != finals.len() {
                    return Err(EngineError::FinalsPlayerCount);
                }
                let old_set: std::collections::HashSet<String> = (0..finals.len())
                    .map(|i| finals[i]["player_uid"].as_str().unwrap_or("").to_string())
                    .collect();
                let new_set: std::collections::HashSet<&String> = new_players.iter().collect();
                if old_set.len() != new_set.len()
                    || !new_players.iter().all(|uid| old_set.contains(uid))
                {
                    return Err(EngineError::FinalsPlayerSet);
                }
                for (i, uid) in new_players.iter().enumerate() {
                    finals[i]["player_uid"] = uid.as_str().into();
                }
            } else {
                if *round >= rounds_len {
                    return Err(EngineError::InvalidRound);
                }

                // Positional: tables 0..table_count match existing by index (results
                // preserved per index); extras appended; empty tables are draft
                // workspaces, dropped after rebuild.
                let table_count = tournament["rounds"][*round].len();
                if seating.len() < table_count {
                    return Err(EngineError::TableCountMismatch);
                }
                for table in seating.iter() {
                    if !table.is_empty() && !(4..=5).contains(&table.len()) {
                        return Err(EngineError::InvalidTableSize { size: table.len() });
                    }
                }

                let mut old_results: std::collections::HashMap<String, (usize, JsonValue, String)> =
                    std::collections::HashMap::new();
                for t in 0..table_count {
                    for s in 0..tournament["rounds"][*round][t]["seating"].len() {
                        let uid = tournament["rounds"][*round][t]["seating"][s]["player_uid"]
                            .as_str()
                            .unwrap_or("")
                            .to_string();
                        let result =
                            tournament["rounds"][*round][t]["seating"][s]["result"].clone();
                        let judge = tournament["rounds"][*round][t]["seating"][s]["judge_uid"]
                            .as_str()
                            .unwrap_or("")
                            .to_string();
                        old_results.insert(uid, (t, result, judge));
                    }
                }

                let new_total: usize = seating.iter().map(|t| t.len()).sum();
                if new_total != old_results.len() {
                    return Err(EngineError::PlayerCountMismatch);
                }

                {
                    // Reject predator-prey repeats: reuse collect_previous_rounds
                    // (Cancelled-filtered) with the proposed seating swapped in.
                    let mut check_rounds = collect_previous_rounds(tournament);
                    check_rounds[*round] = seating.clone();
                    let issues = seating::compute_player_issues(&check_rounds);
                    if issues.iter().any(|i| i.rule == 0) {
                        return Err(EngineError::SeatingViolatesR1);
                    }
                }

                let round_data = &mut tournament["rounds"][*round];

                for t in 0..seating.len() {
                    if t >= round_data.len() {
                        round_data.push(json::object! {
                            seating: [],
                            state: "In Progress",
                            override: json::Null,
                        })?;
                    }
                    let new_players = &seating[t];
                    let mut new_seating = Vec::new();
                    for uid in new_players {
                        let (old_table, old_result, old_judge) =
                            old_results
                                .get(uid)
                                .ok_or_else(|| EngineError::PlayerNotInRound {
                                    player: uid.to_string(),
                                })?;
                        let (result, judge) = if *old_table == t {
                            (old_result.clone(), old_judge.as_str())
                        } else {
                            (json::object! { gw: 0, vp: 0.0, tp: 0 }, "")
                        };
                        new_seating.push(json::object! {
                            player_uid: uid.as_str(),
                            result: result,
                            judge_uid: judge,
                        });
                    }
                    round_data[t]["seating"] = JsonValue::Array(new_seating);

                    let vps: Vec<f64> = (0..round_data[t]["seating"].len())
                        .map(|s| {
                            round_data[t]["seating"][s]["result"]["vp"]
                                .as_f64()
                                .unwrap_or(0.0)
                        })
                        .collect();
                    if round_data[t]["override"].is_null() {
                        let all_zero = vps.iter().all(|&v| v == 0.0);
                        if all_zero {
                            round_data[t]["state"] = "In Progress".into();
                        }
                    }
                }

                for t in (0..round_data.len()).rev() {
                    if round_data[t]["seating"].is_empty() {
                        round_data.array_remove(t);
                    }
                }
            }

            // Refresh after the reseat (no later round event refreshes in Finished
            // state). No-op for the finals branch: prelim standings read rounds only.
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::SeatPlayer {
            player_uid,
            table,
            seat,
            round,
        } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            // Registered/Checked-in are unseated-and-present; a Finished player with
            // ZERO rounds played is a no-show reinstated by seating them.
            let player_idx = find_player_index(&tournament["players"], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            let player_state = tournament["players"][player_idx]["state"]
                .as_str()
                .unwrap_or("");
            let reinstatable_no_show = player_state == "Finished"
                && count_player_rounds_played(tournament, player_uid) == 0;
            let present_and_unseated = player_state == "Registered" || player_state == "Checked-in";
            if !present_and_unseated
                && !(state == TournamentState::Finished && player_state == "Finished")
                && !reinstatable_no_show
            {
                return Err(EngineError::PlayerWrongState {
                    current: player_state.to_string(),
                });
            }

            // An earlier round may take a substitute too, but only while it is
            // live (see resolve_live_round).
            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = resolve_live_round(rounds, *round)?;
            if *table >= rounds[last].len() {
                return Err(EngineError::InvalidTable);
            }

            let seating = &mut rounds[last][*table]["seating"];
            let seating_len = seating.len();
            if seating_len >= 5 {
                return Err(EngineError::TableFull);
            }
            let insert_pos = if *seat > seating_len {
                seating_len
            } else {
                *seat
            };

            let seat_entry = json::object! {
                player_uid: player_uid.as_str(),
                result: { gw: 0, vp: 0.0, tp: 0 },
                judge_uid: "",
            };

            let mut new_seating = Vec::new();
            for i in 0..seating_len {
                if i == insert_pos {
                    new_seating.push(seat_entry.clone());
                }
                new_seating.push(seating[i].clone());
            }
            if insert_pos >= seating_len {
                new_seating.push(seat_entry);
            }
            rounds[last][*table]["seating"] = JsonValue::Array(new_seating);

            // Set player state — mirror CheckOut/UnseatPlayer: a Finished tournament
            // keeps the player Finished, otherwise they join the live round as Playing.
            tournament["players"][player_idx]["state"] = if state == TournamentState::Finished {
                "Finished"
            } else {
                "Playing"
            }
            .into();
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::UnseatPlayer { player_uid, round } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = resolve_live_round(rounds, *round)?;

            let mut found = false;
            for t in 0..rounds[last].len() {
                let seating = &rounds[last][t]["seating"];
                let mut seat_idx = None;
                for s in 0..seating.len() {
                    if seating[s]["player_uid"].as_str() == Some(player_uid) {
                        seat_idx = Some(s);
                        break;
                    }
                }
                if let Some(s) = seat_idx {
                    rounds[last][t]["seating"].array_remove(s);
                    found = true;
                    break;
                }
            }

            if !found {
                return Err(EngineError::PlayerNotInRound {
                    player: player_uid.to_string(),
                });
            }

            // Reset player state — mirror CheckOut: Finished tournament keeps the
            // player Finished, otherwise back to Registered.
            if let Some(idx) = find_player_index(&tournament["players"], player_uid) {
                tournament["players"][idx]["state"] = if state == TournamentState::Finished {
                    "Finished"
                } else {
                    "Registered"
                }
                .into();
            }
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::AddTable => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = rounds.len() - 1;

            let empty_table = json::object! {
                seating: [],
                state: "In Progress",
                override: json::Null,
            };
            rounds[last].push(empty_table)?;
            Ok(())
        }

        TournamentEvent::RemoveTable { table } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = rounds.len() - 1;
            if *table >= rounds[last].len() {
                return Err(EngineError::InvalidTable);
            }
            if !rounds[last][*table]["seating"].is_empty() {
                return Err(EngineError::TableNotEmpty);
            }
            rounds[last].array_remove(*table);
            Ok(())
        }

        TournamentEvent::SetScore {
            round,
            table,
            scores,
        } => {
            require_can_edit_results(actor, state)?;

            let rounds_len = tournament["rounds"].len();
            let is_finals = *round == rounds_len && !tournament["finals"].is_null() && *table == 0;

            // Resolved before the mutable borrow of `t` below: scores don't move
            // seats, so this ordering is equivalent and avoids a borrow conflict.
            let effective_sas = sanctions::resolve_sa_effective_rounds(tournament, sanctions);

            let t = if is_finals {
                &mut tournament["finals"]
            } else {
                let rounds = &tournament["rounds"];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                if *table >= rounds[*round].len() {
                    return Err(EngineError::InvalidTable);
                }
                &mut tournament["rounds"][*round][*table]
            };

            let is_at_table = t["seating"]
                .members()
                .any(|s| s["player_uid"].as_str() == Some(&actor.uid));

            if !actor.is_organizer && !is_at_table {
                return Err(EngineError::ScoreForbidden);
            }

            if !t["override"].is_null() && !actor.is_organizer {
                return Err(EngineError::ScoreLocked);
            }

            if !actor.is_organizer {
                let has_judge_score = t["seating"]
                    .members()
                    .any(|s| !s["judge_uid"].as_str().unwrap_or("").is_empty());
                if has_judge_score {
                    return Err(EngineError::ScoreSetByOrganizer);
                }
            }

            let table_size = t["seating"].len();

            for score in scores.iter() {
                let vp = score.vp;
                // Must be in [0, table_size] in 0.5 steps
                if (vp < 0.0 || vp > table_size as f64 || (vp * 2.0).fract() != 0.0)
                    && !actor.is_organizer
                {
                    return Err(EngineError::internal(format!("Invalid VP value: {}", vp)));
                }
                // table_size - 0.5 is impossible (non-organizer blocked)
                if !actor.is_organizer && vp == table_size as f64 - 0.5 {
                    return Err(EngineError::internal(format!(
                        "VP value {} is impossible",
                        vp
                    )));
                }
            }

            let vp_map: std::collections::HashMap<&str, f64> = scores
                .iter()
                .map(|s| (s.player_uid.as_str(), s.vp))
                .collect();

            // Gathered in seating order (predator-prey order), for oust-order validation.
            let mut vps: Vec<f64> = Vec::with_capacity(table_size);
            for i in 0..table_size {
                let player_uid = t["seating"][i]["player_uid"].as_str().unwrap_or("");
                let vp = vp_map
                    .get(player_uid)
                    .copied()
                    .unwrap_or(t["seating"][i]["result"]["vp"].as_f64().unwrap_or(0.0));
                vps.push(vp);
            }

            // Per-seat SA adjustments (-1.0 VP per SA on this round). Same helper the
            // standings/rating recompute uses, so GW/TP stay consistent everywhere.
            let current_round = if is_finals { rounds_len } else { *round };
            let adjustments = table_sa_adjustments(&t["seating"], current_round, &effective_sas);

            let gws = if is_finals {
                let seating_uids: Vec<&str> = (0..table_size)
                    .map(|i| t["seating"][i]["player_uid"].as_str().unwrap_or(""))
                    .collect();
                let seed_order: Vec<String> = t["seed_order"]
                    .members()
                    .filter_map(|s| s.as_str().map(|v| v.to_string()))
                    .collect();
                compute_gw_finals(&vps, &adjustments, &seating_uids, &seed_order)
            } else {
                compute_gw(&vps, &adjustments)
            };
            let tps = compute_tp(table_size, &vps, &adjustments);

            for i in 0..table_size {
                let player_uid = t["seating"][i]["player_uid"]
                    .as_str()
                    .unwrap_or("")
                    .to_string();
                if vp_map.contains_key(player_uid.as_str()) {
                    t["seating"][i]["result"]["vp"] = vps[i].into();
                    t["seating"][i]["result"]["gw"] = gws[i].into();
                    t["seating"][i]["result"]["tp"] = tps[i].into();
                    // A seated organizer plays, not adjudicates: stamping would lock
                    // their own tablemates out. Override still locks a table you sit at.
                    if actor.is_organizer && !is_at_table {
                        t["seating"][i]["judge_uid"] = actor.uid.as_str().into();
                    }
                }
            }

            if t["override"].is_null() {
                let vp_err = check_table_vps(&vps);
                match vp_err {
                    Some(VpError::IncompleteTotal) => {
                        t["state"] = "In Progress".into();
                    }
                    Some(VpError::RedirectedVp) => {
                        // Previously read as a half-filled table and accepted; keep
                        // accepting, but flag what it is — only a judge can close it.
                        t["state"] = "Invalid".into();
                    }
                    Some(_) => {
                        if !actor.is_organizer {
                            return Err(EngineError::InvalidScore);
                        }
                        t["state"] = "Invalid".into();
                    }
                    None => {
                        t["state"] = "Finished".into();
                    }
                }
            }

            // Required for out-of-round corrections and edits to an already-finished round
            // while another is still Playing — ratings/VEKN-push/exports read the stored standings.
            update_standings(tournament, sanctions);

            Ok(())
        }

        TournamentEvent::Override {
            round,
            table,
            comment,
        } => {
            require_organizer(actor)?;
            require_can_edit_results(actor, state)?;

            let is_finals = *round == tournament["rounds"].len()
                && !tournament["finals"].is_null()
                && *table == 0;
            let t = if is_finals {
                &mut tournament["finals"]
            } else {
                let rounds = &tournament["rounds"];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                if *table >= rounds[*round].len() {
                    return Err(EngineError::InvalidTable);
                }
                &mut tournament["rounds"][*round][*table]
            };
            t["override"] = json::object! {
                judge_uid: actor.uid.as_str(),
                comment: comment.as_str(),
            };
            t["state"] = "Finished".into();

            Ok(())
        }

        TournamentEvent::Unoverride { round, table } => {
            require_organizer(actor)?;
            require_can_edit_results(actor, state)?;

            let is_finals = *round == tournament["rounds"].len()
                && !tournament["finals"].is_null()
                && *table == 0;
            let t = if is_finals {
                &mut tournament["finals"]
            } else {
                let rounds = &tournament["rounds"];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                if *table >= rounds[*round].len() {
                    return Err(EngineError::InvalidTable);
                }
                &mut tournament["rounds"][*round][*table]
            };
            t["override"] = json::Null;

            let table_size = t["seating"].len();
            let vps: Vec<f64> = (0..table_size)
                .map(|i| t["seating"][i]["result"]["vp"].as_f64().unwrap_or(0.0))
                .collect();
            let vp_err = check_table_vps(&vps);
            match vp_err {
                Some(VpError::IncompleteTotal) => {
                    t["state"] = "In Progress".into();
                }
                Some(_) => {
                    t["state"] = "Invalid".into();
                }
                None => {
                    t["state"] = "Finished".into();
                }
            }

            Ok(())
        }

        TournamentEvent::SetToss { player_uid, toss } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if count_played_rounds(tournament) < 2 {
                return Err(EngineError::TossMinRounds);
            }
            let idx = find_player_index(&tournament["players"], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            tournament["players"][idx]["toss"] = (*toss).into();
            Ok(())
        }

        TournamentEvent::RandomToss => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if count_played_rounds(tournament) < 2 {
                return Err(EngineError::TossMinRounds);
            }

            let standings = compute_preliminary_standings(tournament, sanctions);
            let candidates = finals_candidates(&tournament["players"], &standings);

            // The client applies this event through WASM before the server replays it,
            // so the shuffle must be a pure function of the tournament — an OS random
            // source would leave the two copies seating a different top five.
            let seed: u64 = tournament["uid"]
                .as_str()
                .unwrap_or("")
                .bytes()
                .fold(0u64, |acc, b| acc.wrapping_mul(31).wrapping_add(b as u64));

            let mut toss_counter: u32 = 1;
            for group in toss_groups(&candidates) {
                let mut shuffled: Vec<&standings::Standing> = candidates[group.clone()].to_vec();
                if tosses_are_total(&shuffled) {
                    continue;
                }
                let mut rng = seed.wrapping_add(group.start as u64);
                for k in (1..shuffled.len()).rev() {
                    rng = rng
                        .wrapping_mul(6364136223846793005)
                        .wrapping_add(1442695040888963407);
                    let swap_idx = (rng >> 33) as usize % (k + 1);
                    shuffled.swap(k, swap_idx);
                }
                for s in shuffled {
                    if let Some(pi) = find_player_index(&tournament["players"], &s.user_uid) {
                        tournament["players"][pi]["toss"] = toss_counter.into();
                    }
                    toss_counter += 1;
                }
            }

            Ok(())
        }

        TournamentEvent::StartFinals => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if count_played_rounds(tournament) < 2 {
                return Err(EngineError::FinalsMinRounds);
            }
            if !tournament["finals"].is_null() {
                return Err(EngineError::FinalsAlreadyStarted);
            }

            let standings = compute_preliminary_standings(tournament, sanctions);
            let eligible = finals_candidates(&tournament["players"], &standings);

            if eligible.len() < 5 {
                return Err(EngineError::FinalsNotEnoughPlayers);
            }
            if top5_has_ties(&eligible) {
                return Err(EngineError::FinalsUnresolvedTies);
            }

            let top5: Vec<&standings::Standing> = eligible.into_iter().take(5).collect();
            let seed_order: Vec<JsonValue> =
                top5.iter().map(|s| s.user_uid.as_str().into()).collect();
            let seating: Vec<JsonValue> = top5
                .iter()
                .map(|s| {
                    json::object! {
                        player_uid: s.user_uid.as_str(),
                        result: { gw: 0, vp: 0.0, tp: 0 },
                        judge_uid: "",
                    }
                })
                .collect();

            tournament["finals"] = json::object! {
                seating: JsonValue::Array(seating),
                state: "In Progress",
                override: json::Null,
                seed_order: JsonValue::Array(seed_order),
            };

            for s in &top5 {
                if let Some(idx) = find_player_index(&tournament["players"], &s.user_uid) {
                    tournament["players"][idx]["state"] = "Playing".into();
                    tournament["players"][idx]["finalist"] = true.into();
                }
            }

            if state != TournamentState::Finished {
                tournament["state"] = "Playing".into();
            }
            Ok(())
        }

        TournamentEvent::FinishFinals => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;
            if tournament["finals"].is_null() {
                return Err(EngineError::NoFinalsInProgress);
            }

            let finals_state = tournament["finals"]["state"].as_str().unwrap_or("");
            if finals_state != "Finished" {
                return Err(EngineError::FinalsTableUnfinished);
            }

            // compute_gw_finals is the single source of finals-winner derivation — the same
            // call SetScore and update_standings use, so the winner can never diverge from the scored GW.
            let effective_sas = sanctions::resolve_sa_effective_rounds(tournament, sanctions);
            let finals_round = tournament["rounds"].len();
            let seating = &tournament["finals"]["seating"];
            let vps: Vec<f64> = seating
                .members()
                .map(|s| s["result"]["vp"].as_f64().unwrap_or(0.0))
                .collect();
            let seating_uids: Vec<&str> = seating
                .members()
                .map(|s| s["player_uid"].as_str().unwrap_or(""))
                .collect();
            let adjustments = table_sa_adjustments(seating, finals_round, &effective_sas);
            let seed_order: Vec<String> = tournament["finals"]["seed_order"]
                .members()
                .filter_map(|s| s.as_str().map(|v| v.to_string()))
                .collect();
            let gws = compute_gw_finals(&vps, &adjustments, &seating_uids, &seed_order);
            let winner = gws
                .iter()
                .position(|&g| g == 1.0)
                .map(|i| seating_uids[i].to_string())
                .unwrap_or_default();

            tournament["winner"] = winner.as_str().into();
            if state != TournamentState::Finished {
                tournament["state"] = "Finished".into();
            }

            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() != Some("Disqualified") {
                    players[i]["state"] = "Finished".into();
                }
            }

            update_standings(tournament, sanctions);

            Ok(())
        }

        TournamentEvent::CancelFinals => {
            // Revert a not-yet-finalized finals to Waiting so the organizer can drop a
            // no-show and re-run StartFinals, which promotes the next qualifier.
            require_organizer(actor)?;
            require_state(state, TournamentState::Playing)?;
            if tournament["finals"].is_null() {
                return Err(EngineError::NoFinalsInProgress);
            }

            // Capped (open-rounds) finalists return to Completed; the rest to Checked-in.
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let capped: std::collections::HashSet<String> = if max_rounds > 0 {
                tournament["players"]
                    .members()
                    .filter(|p| p["finalist"].as_bool().unwrap_or(false))
                    .filter_map(|p| p["user_uid"].as_str().map(String::from))
                    .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                    .collect()
            } else {
                std::collections::HashSet::new()
            };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["finalist"].as_bool().unwrap_or(false) {
                    let uid = players[i]["user_uid"].as_str().unwrap_or("").to_string();
                    players[i]["finalist"] = false.into();
                    players[i]["state"] = if capped.contains(&uid) {
                        "Completed"
                    } else {
                        "Checked-in"
                    }
                    .into();
                }
            }

            tournament["finals"] = json::Null;
            tournament["state"] = "Waiting".into();
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::FinishTournament => {
            require_organizer(actor)?;
            if state != TournamentState::Waiting
                && state != TournamentState::Playing
                && state != TournamentState::Finished
            {
                return Err(EngineError::CannotFinish);
            }

            tournament["state"] = "Finished".into();

            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() != Some("Disqualified") {
                    players[i]["state"] = "Finished".into();
                }
            }

            update_standings(tournament, sanctions);

            for d in decks.members() {
                let user_uid = d["user_uid"].as_str().unwrap_or("");
                if user_uid.is_empty() {
                    continue;
                }
                let is_public = compute_deck_public(tournament, user_uid);
                if is_public {
                    let op = json::object! {
                        "op" => "set_public",
                        "deck_uid" => d["uid"].as_str().unwrap_or(""),
                        "public" => true,
                    };
                    let _ = deck_ops.push(op);
                }
            }
            Ok(())
        }

        TournamentEvent::UpsertDeck {
            player_uid,
            deck,
            multideck,
        } => {
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err(EngineError::DeckUploadForbidden);
            }
            let is_registered = tournament["players"]
                .members()
                .any(|p| p["user_uid"].as_str() == Some(player_uid.as_str()));
            if !is_registered {
                return Err(EngineError::NotRegistered);
            }
            if !actor.is_organizer {
                let existing_count = decks
                    .members()
                    .filter(|d| d["user_uid"].as_str() == Some(player_uid.as_str()))
                    .count();
                match state {
                    TournamentState::Playing => {
                        if *multideck {
                            if is_deck_locked(tournament, player_uid, existing_count) {
                                return Err(EngineError::DeckLockedRound);
                            }
                        } else if existing_count > 0 {
                            return Err(EngineError::DeckLockedPlaying);
                        }
                    }
                    TournamentState::Finished if existing_count > 0 => {
                        return Err(EngineError::DeckLockedFinished);
                    }
                    _ => {} // Planned, Registration, Waiting: always allowed
                }
            }
            let is_public = compute_deck_public(tournament, player_uid);
            let mut deck_data = deck.clone();
            deck_data["public"] = is_public.into();
            let op = json::object! {
                "op" => "upsert",
                "player_uid" => player_uid.as_str(),
                "deck" => deck_data,
                "multideck" => *multideck,
            };
            let _ = deck_ops.push(op);
            Ok(())
        }

        TournamentEvent::DeleteDeck {
            player_uid,
            deck_index,
            multideck,
        } => {
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err(EngineError::DeckDeleteForbidden);
            }
            if !actor.is_organizer {
                match state {
                    TournamentState::Playing => {
                        if *multideck {
                            if let Some(idx) = deck_index {
                                if is_deck_locked(tournament, player_uid, *idx) {
                                    return Err(EngineError::DeckLockedRound);
                                }
                            } else {
                                return Err(EngineError::internal(
                                    "deck_index required for multideck delete",
                                ));
                            }
                        } else {
                            return Err(EngineError::DeckLockedPlaying);
                        }
                    }
                    TournamentState::Finished => {
                        return Err(EngineError::DeckLockedFinished);
                    }
                    _ => {} // Planned, Registration, Waiting: always allowed
                }
            }
            let op = json::object! {
                "op" => "delete",
                "player_uid" => player_uid.as_str(),
                "deck_index" => match deck_index { Some(i) => JsonValue::from(*i), None => JsonValue::Null },
                "multideck" => *multideck,
            };
            let _ = deck_ops.push(op);
            Ok(())
        }

        TournamentEvent::RaffleDraw {
            label,
            pool,
            exclude_drawn,
            count,
            seed,
            prize_promo_uid,
        } => {
            require_organizer(actor)?;
            if state != TournamentState::Waiting
                && state != TournamentState::Playing
                && state != TournamentState::Finished
            {
                return Err(EngineError::RaffleWrongState);
            }
            if *count == 0 {
                return Err(EngineError::RaffleCountMin);
            }
            let mut eligible = get_raffle_pool(tournament, sanctions, pool, *exclude_drawn)?;
            if eligible.is_empty() {
                return Err(EngineError::RaffleNoPlayers);
            }
            // Fisher-Yates, same LCG as RandomToss.
            let mut rng = *seed;
            for k in (1..eligible.len()).rev() {
                rng = rng
                    .wrapping_mul(6364136223846793005)
                    .wrapping_add(1442695040888963407);
                let swap_idx = (rng >> 33) as usize % (k + 1);
                eligible.swap(k, swap_idx);
            }
            let winners: Vec<JsonValue> = eligible
                .into_iter()
                .take(*count)
                .map(|uid| uid.into())
                .collect();
            let mut draw = json::object! {
                "label" => label.as_str(),
                "pool" => pool.as_str(),
                "winners" => JsonValue::Array(winners),
            };
            if let Some(promo_uid) = prize_promo_uid {
                draw["prize_promo_uid"] = promo_uid.as_str().into();
            }
            if tournament["raffles"].is_null() {
                tournament["raffles"] = JsonValue::new_array();
            }
            tournament["raffles"].push(draw)?;
            Ok(())
        }

        TournamentEvent::RaffleUndo => {
            require_organizer(actor)?;
            if tournament["raffles"].is_null() || tournament["raffles"].is_empty() {
                return Err(EngineError::RaffleNoDraws);
            }
            let last = tournament["raffles"].len() - 1;
            tournament["raffles"].array_remove(last);
            Ok(())
        }

        TournamentEvent::RaffleClear => {
            require_organizer(actor)?;
            tournament["raffles"] = JsonValue::new_array();
            Ok(())
        }

        TournamentEvent::ReportPromos {
            promos,
            stock_source_uid,
        } => {
            require_organizer(actor)?;
            // No state gate: usually entered at/after finish, and corrections
            // to an already-submitted report are first-class.
            tournament["promos_distributed"] = promos.clone();
            let source = stock_source_uid
                .clone()
                .unwrap_or_else(|| actor.uid.clone());
            tournament["promo_stock_source_uid"] = source.into();
            Ok(())
        }

        TournamentEvent::UpdateConfig { config } => {
            require_organizer(actor)?;

            validate_config_fields(config)?;

            // rank/format/start freeze once VEKN-published: calendar create and results
            // push are both write-once, so a later edit would silently diverge from vekn.net.
            let vekn_id = tournament["external_ids"]["vekn"].as_str().unwrap_or("");
            if !vekn_id.is_empty() {
                for field in ["rank", "format", "start"] {
                    // String compare with null ≡ "" (the form posts "" for "no rank")
                    if config.has_key(field)
                        && config[field].as_str().unwrap_or("")
                            != tournament[field].as_str().unwrap_or("")
                    {
                        return Err(EngineError::VeknFrozenField {
                            field: field.to_string(),
                        });
                    }
                }
            }

            // Only when the edit touches one of the four keys, on the merged view — an
            // already-illegal stored combo (legacy import) must not block unrelated edits.
            if config.has_key("rank")
                || config.has_key("format")
                || config.has_key("proxies")
                || config.has_key("multideck")
            {
                let merged_str = |field: &str| -> String {
                    if config.has_key(field) {
                        config[field].as_str().unwrap_or("").to_string()
                    } else {
                        tournament[field].as_str().unwrap_or("").to_string()
                    }
                };
                let merged_bool = |field: &str| -> bool {
                    if config.has_key(field) {
                        config[field].as_bool().unwrap_or(false)
                    } else {
                        tournament[field].as_bool().unwrap_or(false)
                    }
                };
                validate_rank_legality(
                    &merged_str("format"),
                    &merged_str("rank"),
                    merged_bool("proxies"),
                    merged_bool("multideck"),
                )?;
            }

            // Date ordering on the merged view: a partial update can carry `finish` while
            // `start` still lives on the stored tournament, so a config-only check would see half the pair.
            if config.has_key("start") || config.has_key("finish") {
                let merged_date = |field: &str| -> String {
                    let src = if config.has_key(field) {
                        &config[field]
                    } else {
                        &tournament[field]
                    };
                    src.as_str().unwrap_or("").to_string()
                };
                validate_finish_after_start(&merged_date("start"), &merged_date("finish"))?;
            }

            if let Some(mr) = config["max_rounds"].as_usize() {
                if mr != 0 {
                    // Per-player cap: can't drop below what any single player has already played.
                    let completed = tournament["players"]
                        .members()
                        .filter_map(|p| p["user_uid"].as_str())
                        .map(|uid| count_player_rounds_played(tournament, uid))
                        .max()
                        .unwrap_or(0);
                    if mr < completed {
                        return Err(EngineError::MaxRoundsBelowCompleted { max: mr, completed });
                    }
                }
            }
            // Validate league_uid: only league organizers (or IC) can link
            if config.has_key("league_uid") && !config["league_uid"].is_null() {
                let league_uid = config["league_uid"].as_str().unwrap_or("");
                if !league_uid.is_empty()
                    && !actor.roles.contains(&"IC".to_string())
                    && !actor
                        .can_organize_league_uids
                        .contains(&league_uid.to_string())
                {
                    return Err(EngineError::LeagueLinkForbidden);
                }
            }

            let decklists_mode_changing =
                config.has_key("decklists_mode") && state == TournamentState::Finished;

            // Apply config fields (key present = apply, even if null)
            let config_fields = [
                "name",
                "format",
                "rank",
                "online",
                "start",
                "finish",
                "timezone",
                "country",
                "venue",
                "venue_url",
                "address",
                "map_url",
                "proxies",
                "multideck",
                "decklist_required",
                "description",
                "standings_mode",
                "decklists_mode",
                "max_rounds",
                "max_players",
                "open_rounds",
                "self_organized_rounds",
                "table_rooms",
                "league_uid",
                "round_time",
                "finals_time",
            ];
            for field in config_fields {
                if config.has_key(field) {
                    tournament[field] = config[field].clone();
                }
            }

            if decklists_mode_changing {
                for d in decks.members() {
                    let user_uid = d["user_uid"].as_str().unwrap_or("");
                    let deck_uid = d["uid"].as_str().unwrap_or("");
                    if user_uid.is_empty() || deck_uid.is_empty() {
                        continue;
                    }
                    let is_public = compute_deck_public(tournament, user_uid);
                    let op = json::object! {
                        "op" => "set_public",
                        "deck_uid" => deck_uid,
                        "public" => is_public,
                    };
                    let _ = deck_ops.push(op);
                }
            }

            Ok(())
        }

        TournamentEvent::SetArchivalResults {
            winner,
            players,
            reported_player_count,
        } => {
            if !crate::permissions::allows(
                crate::permissions::Capability::SetArchivalResults,
                &crate::permissions::Request::new(&actor.user_context(), &actor.uid),
            ) {
                return Err(EngineError::ArchivalResultsForbidden);
            }
            require_state(state, TournamentState::Finished)?;
            // The data-shape gate, not a mode flag: every legacy import is
            // rounds-less while carrying a real scored result sheet, and this
            // must never overwrite one.
            if crate::ratings::players_with_rounds(tournament) != 0 {
                return Err(EngineError::ArchivalResultsHasPlay);
            }
            // The nightly calendar sync rebuilds any rounds-less vekn-linked row
            // from upstream, so the correction would vanish on its next run.
            if !tournament["external_ids"]["vekn"]
                .as_str()
                .unwrap_or("")
                .is_empty()
            {
                return Err(EngineError::ArchivalResultsVeknLinked);
            }
            if !players.iter().any(|p| p == winner) {
                return Err(EngineError::ArchivalResultsWinnerNotListed);
            }
            if *reported_player_count < players.len() {
                return Err(EngineError::ArchivalResultsCountBelowRoster {
                    reported: *reported_player_count,
                    listed: players.len(),
                });
            }

            let ordered = std::iter::once(winner)
                .chain(players.iter().filter(|p| *p != winner))
                .collect::<Vec<_>>();
            // A native event finished from Waiting also reaches here: a name-only
            // player has no uid the payload could name, so they are carried
            // through rather than deleted by an event that cannot address them.
            let existing = tournament["players"].clone();
            let nameless: Vec<JsonValue> = existing
                .members()
                .filter(|p| p["user_uid"].as_str().unwrap_or("").is_empty())
                .cloned()
                .collect();
            tournament["players"] = JsonValue::Array(
                ordered
                    .iter()
                    .map(|uid| {
                        let prior = existing
                            .members()
                            .find(|p| p["user_uid"].as_str() == Some(uid.as_str()));
                        let mut player = json::object! {
                            user_uid: uid.as_str(),
                            state: "Finished",
                            payment_status: prior
                                .and_then(|p| p["payment_status"].as_str())
                                .unwrap_or("Paid"),
                            toss: 0,
                            result: { gw: 0, vp: 0.0, tp: 0 },
                            finalist: *uid == winner,
                            non_competing: false,
                        };
                        if let Some(dn) = prior.and_then(|p| p["display_name"].as_str()) {
                            player["display_name"] = dn.into();
                        }
                        player
                    })
                    .chain(nameless)
                    .collect(),
            );
            tournament["standings"] = JsonValue::Array(
                ordered
                    .iter()
                    .map(|uid| {
                        json::object! {
                            user_uid: uid.as_str(),
                            gw: 0.0,
                            vp: 0.0,
                            tp: 0,
                            toss: 0,
                            finalist: *uid == winner,
                            disqualified: false,
                            non_competing: false,
                        }
                    })
                    .collect(),
            );
            tournament["winner"] = winner.as_str().into();
            tournament["reported_player_count"] = (*reported_player_count).into();
            Ok(())
        }
    }
}
