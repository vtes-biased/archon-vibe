use crate::model::{
    arg, deck_object, finals_table, player, raffle_draw, room, score, score_override, seat,
    standing, table, tournament, tournament_config,
};
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

pub use raffle::get_raffle_pool;
pub use scoring::{check_table_vps, compute_gw, compute_gw_finals, compute_tp};
pub use standings::{
    compute_final_standings, compute_rating_vp_gw, display_standings, final_played,
    finals_qualification, is_no_show, sort_standing_rows,
};
pub use types::{ActorContext, PlayerState, SeatScore, TournamentEvent, TournamentState, VpError};

use crate::error::EngineError;
use helpers::{
    all_rounds_finished, collect_previous_rounds, count_played_rounds, count_player_rounds_played,
    demote_unseated_players, find_player_index, past_registration_cap, player_exists,
    players_in_other_active_rounds, release_stamped_decks, require_can_edit_results,
    require_organizer, require_state, require_state_or_finished, stamp_round_decks, validate_enum,
};
use raffle::compute_deck_public;
use sanctions::{has_active_suspension, has_dq_sanction, table_sa_adjustments};
use standings::{
    compute_preliminary_standings, finals_candidates, top5_has_ties, toss_groups, tosses_are_total,
    update_standings,
};

/// Room-aware table label. `None` when no room covers `table_idx`.
pub fn table_label(table_rooms: &JsonValue, table_idx: usize) -> Option<String> {
    let mut offset = 0usize;
    for room in table_rooms.members() {
        let count = room[room::COUNT].as_usize().unwrap_or(0);
        let name = room[room::NAME].as_str().unwrap_or("");
        if table_idx < offset + count {
            return Some(if count == 1 {
                name.to_string()
            } else {
                format!("{name} {}", table_idx - offset + 1)
            });
        }
        offset += count;
    }
    None
}

pub const CONFIG_FIELDS: [&str; 27] = [
    tournament_config::NAME,
    tournament_config::FORMAT,
    tournament_config::RANK,
    tournament_config::ONLINE,
    tournament_config::START,
    tournament_config::FINISH,
    tournament_config::TIMEZONE,
    tournament_config::COUNTRY,
    tournament_config::VENUE,
    tournament_config::VENUE_URL,
    tournament_config::ADDRESS,
    tournament_config::MAP_URL,
    tournament_config::REGISTRATION_URL,
    tournament_config::PROXIES,
    tournament_config::MULTIDECK,
    tournament_config::DECKLIST_REQUIRED,
    tournament_config::DESCRIPTION,
    tournament_config::STANDINGS_MODE,
    tournament_config::DECKLISTS_MODE,
    tournament_config::MAX_ROUNDS,
    tournament_config::MAX_PLAYERS,
    tournament_config::OPEN_ROUNDS,
    tournament_config::SELF_ORGANIZED_ROUNDS,
    tournament_config::TABLE_ROOMS,
    tournament_config::LEAGUE_UID,
    tournament_config::ROUND_TIME,
    tournament_config::FINALS_TIME,
];

/// Shared between `UpdateConfig` and `CreateTournament`.
fn validate_config_fields(config: &JsonValue) -> Result<(), EngineError> {
    if let Some(f) = config[tournament_config::FORMAT].as_str() {
        validate_enum(
            f,
            &["Standard", "V5", "Limited", "Storyline"],
            tournament_config::FORMAT,
        )?;
    }
    if let Some(r) = config[tournament_config::RANK].as_str() {
        validate_enum(
            r,
            &["", "National Championship", "Continental Championship"],
            tournament_config::RANK,
        )?;
    }
    if let Some(s) = config[tournament_config::STANDINGS_MODE].as_str() {
        validate_enum(
            s,
            &["Private", "Cutoff", "Top 10", "Public"],
            tournament_config::STANDINGS_MODE,
        )?;
    }
    if let Some(d) = config[tournament_config::DECKLISTS_MODE].as_str() {
        validate_enum(
            d,
            &["Winner", "Finalists", "All"],
            tournament_config::DECKLISTS_MODE,
        )?;
    }
    if config.has_key(tournament_config::NAME) {
        if let Some(n) = config[tournament_config::NAME].as_str() {
            if n.trim().is_empty() {
                return Err(EngineError::NameRequired);
            }
        }
    }
    // self_organized_rounds implies open_rounds; reject the combo here so the
    // invariant is enforced by the engine, not just the UI form.
    if config[tournament_config::SELF_ORGANIZED_ROUNDS].as_bool() == Some(true)
        && config.has_key(tournament_config::OPEN_ROUNDS)
        && config[tournament_config::OPEN_ROUNDS].as_bool() == Some(false)
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
        let live = rounds[target].members().any(|t| {
            !matches!(
                t[table::STATE].as_str().unwrap_or(""),
                "Finished" | "Cancelled"
            )
        });
        if !live {
            return Err(EngineError::RoundNotLive);
        }
    }
    Ok(target)
}

/// Ranked events forbid proxies/multideck; only Standard/Limited can be ranked. Callers
/// must pass the MERGED view (config over current tournament).
fn validate_rank_legality(
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
fn validate_finish_after_start(start: &str, finish: &str) -> Result<(), EngineError> {
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
        config[tournament_config::FORMAT].as_str().unwrap_or(""),
        config[tournament_config::RANK].as_str().unwrap_or(""),
        config[tournament_config::PROXIES]
            .as_bool()
            .unwrap_or(false),
        config[tournament_config::MULTIDECK]
            .as_bool()
            .unwrap_or(false),
    )?;
    validate_finish_after_start(
        config[tournament_config::START].as_str().unwrap_or(""),
        config[tournament_config::FINISH].as_str().unwrap_or(""),
    )?;

    let name = config[tournament_config::NAME]
        .as_str()
        .ok_or("name is required")?;
    if name.trim().is_empty() {
        return Err(EngineError::NameRequired);
    }

    let uid = config[tournament_config::UID]
        .as_str()
        .unwrap_or("")
        .to_string();
    let now = config[arg::NOW].as_str().unwrap_or("").to_string();
    let format = config[tournament_config::FORMAT]
        .as_str()
        .unwrap_or("Standard");

    let tournament = json::object! {
        tournament::UID => if uid.is_empty() { json::JsonValue::Null } else { uid.into() },
        tournament::MODIFIED => if now.is_empty() { json::JsonValue::Null } else { now.clone().into() },
        tournament::NAME => name,
        tournament::FORMAT => format,
        tournament::RANK => config[tournament_config::RANK].as_str().unwrap_or(""),
        tournament::ONLINE => config[tournament_config::ONLINE].as_bool().unwrap_or(false),
        tournament::START => config[tournament_config::START].clone(),
        tournament::FINISH => config[tournament_config::FINISH].clone(),
        tournament::TIMEZONE => config[tournament_config::TIMEZONE].as_str().unwrap_or(""),
        tournament::COUNTRY => config[tournament_config::COUNTRY].clone(),
        tournament::STATE => "Planned",
        tournament::ORGANIZERS_UIDS => json::array![actor.uid.clone()],
        tournament::VENUE => config[tournament_config::VENUE].as_str().unwrap_or(""),
        tournament::VENUE_URL => config[tournament_config::VENUE_URL].as_str().unwrap_or(""),
        tournament::ADDRESS => config[tournament_config::ADDRESS].as_str().unwrap_or(""),
        tournament::MAP_URL => config[tournament_config::MAP_URL].as_str().unwrap_or(""),
        tournament::REGISTRATION_URL => config[tournament_config::REGISTRATION_URL].as_str().unwrap_or(""),
        tournament::PROXIES => config[tournament_config::PROXIES].as_bool().unwrap_or(false),
        tournament::MULTIDECK => config[tournament_config::MULTIDECK].as_bool().unwrap_or(false),
        tournament::DECKLIST_REQUIRED => format != "Storyline"
            && config[tournament_config::DECKLIST_REQUIRED].as_bool().unwrap_or(false),
        tournament::DESCRIPTION => config[tournament_config::DESCRIPTION].as_str().unwrap_or(""),
        tournament::STANDINGS_MODE => config[tournament_config::STANDINGS_MODE].as_str().unwrap_or("Private"),
        tournament::DECKLISTS_MODE => config[tournament_config::DECKLISTS_MODE].as_str().unwrap_or("Winner"),
        tournament::MAX_ROUNDS => config[tournament_config::MAX_ROUNDS].as_u32().unwrap_or(0),
        // Soft cap: UI-side warnings only (0 = none). Registration is never blocked.
        tournament::MAX_PLAYERS => config[tournament_config::MAX_PLAYERS].as_u32().unwrap_or(0),
        tournament::OPEN_ROUNDS => config[tournament_config::OPEN_ROUNDS].as_bool().unwrap_or(false),
        tournament::SELF_ORGANIZED_ROUNDS => config[tournament_config::SELF_ORGANIZED_ROUNDS].as_bool().unwrap_or(false),
        tournament::TABLE_ROOMS => if config[tournament_config::TABLE_ROOMS].is_array() {
            config[tournament_config::TABLE_ROOMS].clone()
        } else {
            json::array![]
        },
        tournament::LEAGUE_UID => config[tournament_config::LEAGUE_UID].clone(),
        tournament::ROUND_TIME => config[tournament_config::ROUND_TIME].as_u32().unwrap_or(0),
        tournament::FINALS_TIME => config[tournament_config::FINALS_TIME].as_u32().unwrap_or(0),
        tournament::PLAYERS => json::array![],
        tournament::ROUNDS => json::array![],
        tournament::FINALS => json::JsonValue::Null,
        tournament::WINNER => "",
        tournament::STANDINGS => json::array![],
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
        arg::TOURNAMENT => tournament,
        arg::DECK_OPS => deck_ops,
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
    let tournament = &config[arg::TOURNAMENT];
    let sanctions = &config[arg::SANCTIONS];
    let round = config[arg::ROUND]
        .as_usize()
        .ok_or_else(|| EngineError::internal("round required"))?;
    let rounds_len = tournament[tournament::ROUNDS].len();
    let is_finals = round >= rounds_len;
    let table = if is_finals {
        &tournament[tournament::FINALS]
    } else {
        let table_idx = config[arg::TABLE]
            .as_usize()
            .ok_or_else(|| EngineError::internal("table required"))?;
        &tournament[tournament::ROUNDS][round][table_idx]
    };
    let seating = &table[table::SEATING];
    let vps: Vec<f64> = config[arg::VPS]
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
            .map(|s| s[seat::PLAYER_UID].as_str().unwrap_or(""))
            .collect();
        let seed_order: Vec<String> = table[finals_table::SEED_ORDER]
            .members()
            .filter_map(|s| s.as_str().map(|v| v.to_string()))
            .collect();
        compute_gw_finals(&vps, &adjustments, &seating_uids, &seed_order)
    } else {
        compute_gw(&vps, &adjustments)
    };
    let tps = compute_tp(seating.len(), &vps, &adjustments);
    Ok(json::object! {
        score::GW => JsonValue::Array(gws.into_iter().map(Into::into).collect()),
        score::TP => JsonValue::Array(tps.into_iter().map(Into::into).collect()),
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
    let state =
        TournamentState::from_str(tournament[tournament::STATE].as_str().unwrap_or("Planned"))
            .ok_or("Invalid tournament state")?;

    match event {
        TournamentEvent::OpenRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Planned)?;
            tournament[tournament::STATE] = "Registration".into();
            Ok(())
        }

        TournamentEvent::CloseRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Registration)?;
            tournament[tournament::STATE] = "Waiting".into();
            Ok(())
        }

        TournamentEvent::CancelRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Registration)?;
            tournament[tournament::STATE] = "Planned".into();
            Ok(())
        }

        TournamentEvent::ReopenRegistration => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Waiting)?;
            tournament[tournament::STATE] = "Registration".into();
            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                if players[i][player::STATE].as_str() == Some("Checked-in") {
                    players[i][player::STATE] = "Registered".into();
                }
            }
            Ok(())
        }

        TournamentEvent::ReopenTournament => {
            require_organizer(actor)?;
            require_state(state, TournamentState::Finished)?;
            let has_finals = !tournament[tournament::FINALS].is_null();
            tournament[tournament::STATE] = if has_finals { "Playing" } else { "Waiting" }.into();

            let max_rounds = tournament[tournament::MAX_ROUNDS].as_usize().unwrap_or(0);
            let capped: std::collections::HashSet<String> = if max_rounds > 0 {
                tournament[tournament::PLAYERS]
                    .members()
                    .filter_map(|p| p[player::USER_UID].as_str().map(String::from))
                    .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                    .collect()
            } else {
                std::collections::HashSet::new()
            };
            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                if players[i][player::STATE].as_str() != Some("Finished") {
                    continue;
                }
                let uid = players[i][player::USER_UID]
                    .as_str()
                    .unwrap_or("")
                    .to_string();
                let finalist = players[i][player::FINALIST].as_bool().unwrap_or(false);
                players[i][player::STATE] = if has_finals && finalist {
                    "Playing"
                } else if capped.contains(&uid) {
                    "Completed"
                } else {
                    "Checked-in"
                }
                .into();
            }
            update_standings(tournament, sanctions);
            for d in decks.members() {
                let deck_uid = d[deck_object::UID].as_str().unwrap_or("");
                if !deck_uid.is_empty() {
                    let op = json::object! {
                        arg::OP => "set_public",
                        arg::DECK_UID => deck_uid,
                        arg::PUBLIC => false,
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

            if player_exists(&tournament[tournament::PLAYERS], user_uid) {
                return Err(EngineError::AlreadyRegistered);
            }

            if has_dq_sanction(sanctions, user_uid) {
                return Err(EngineError::PlayerDisqualified);
            }
            if has_active_suspension(sanctions, user_uid, &actor.now) {
                return Err(EngineError::PlayerSuspended);
            }

            let waitlisted = past_registration_cap(tournament);
            let mut player = json::object! {
                player::USER_UID => user_uid.as_str(),
                player::STATE => "Registered",
                player::PAYMENT_STATUS => "Pending",
                player::TOSS => 0,
                player::RESULT => json::object!{ score::GW => 0, score::VP => 0.0, score::TP => 0 },
                player::FINALIST => false,
                player::NON_COMPETING => false,
                player::WAITLISTED => waitlisted,
            };
            if let Some(dn) = display_name {
                if !dn.is_empty() {
                    player[player::DISPLAY_NAME] = dn.as_str().into();
                }
            }
            tournament[tournament::PLAYERS].push(player)?;
            Ok(())
        }

        TournamentEvent::Unregister { user_uid } => {
            require_state(state, TournamentState::Registration)?;

            if actor.uid != *user_uid {
                return Err(EngineError::UnregisterOnlySelf);
            }

            let players = &mut tournament[tournament::PLAYERS];
            let idx = find_player_index(players, user_uid).ok_or(EngineError::PlayerNotFound)?;
            players.array_remove(idx);
            Ok(())
        }

        TournamentEvent::AddPlayer {
            user_uid,
            vekn_id,
            display_name,
            waitlist_past_cap,
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

            if player_exists(&tournament[tournament::PLAYERS], user_uid) {
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
            let waitlisted =
                *waitlist_past_cap && !auto_checkin && past_registration_cap(tournament);
            let mut player = json::object! {
                player::USER_UID => user_uid.as_str(),
                player::STATE => player_state,
                player::PAYMENT_STATUS => "Pending",
                player::TOSS => 0,
                player::RESULT => json::object!{ score::GW => 0, score::VP => 0.0, score::TP => 0 },
                player::FINALIST => false,
                player::NON_COMPETING => false,
                player::WAITLISTED => waitlisted,
            };
            if let Some(dn) = display_name {
                if !dn.is_empty() {
                    player[player::DISPLAY_NAME] = dn.as_str().into();
                }
            }
            if auto_checkin
                && tournament[tournament::DECKLIST_REQUIRED]
                    .as_bool()
                    .unwrap_or(false)
                && !decks
                    .members()
                    .any(|d| d[deck_object::USER_UID].as_str() == Some(user_uid.as_str()))
            {
                player[player::MISSING_DECKLIST] = true.into();
            }
            tournament[tournament::PLAYERS].push(player)?;
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
            if !tournament[tournament::ROUNDS].is_empty() {
                return Err(EngineError::UseDropOut);
            }

            let players = &mut tournament[tournament::PLAYERS];
            let idx = find_player_index(players, user_uid).ok_or(EngineError::PlayerNotFound)?;
            players.array_remove(idx);
            Ok(())
        }

        TournamentEvent::DropOut { player_uid } => {
            if state != TournamentState::Waiting && state != TournamentState::Playing {
                return Err(EngineError::CannotDropOut);
            }

            let players = &mut tournament[tournament::PLAYERS];
            let idx = find_player_index(players, player_uid).ok_or(EngineError::PlayerNotFound)?;
            let player_state =
                PlayerState::from_str(players[idx][player::STATE].as_str().unwrap_or(""))
                    .ok_or("Invalid player state")?;

            if player_state == PlayerState::Finished {
                return Err(EngineError::PlayerAlreadyFinished);
            }

            if !actor.is_organizer && actor.uid != *player_uid {
                return Err(EngineError::DropOutForbidden);
            }

            players[idx][player::STATE] = "Finished".into();
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

            let idx = match find_player_index(&tournament[tournament::PLAYERS], player_uid) {
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
                        player::USER_UID => player_uid.as_str(),
                        player::STATE => "Registered",
                        player::PAYMENT_STATUS => "Pending",
                        player::TOSS => 0,
                        player::RESULT => json::object!{ score::GW => 0, score::VP => 0.0, score::TP => 0 },
                        player::FINALIST => false,
                        player::NON_COMPETING => false,
                        player::WAITLISTED => false,
                    };
                    if let Some(dn) = display_name {
                        if !dn.is_empty() {
                            player[player::DISPLAY_NAME] = dn.as_str().into();
                        }
                    }
                    tournament[tournament::PLAYERS].push(player)?;
                    tournament[tournament::PLAYERS].len() - 1
                }
            };

            if tournament[tournament::PLAYERS][idx][player::STATE].as_str() == Some("Disqualified")
            {
                return Err(EngineError::PlayerDisqualified);
            }

            if tournament[tournament::PLAYERS][idx][player::WAITLISTED]
                .as_bool()
                .unwrap_or(false)
            {
                return Err(EngineError::PlayerWaitlisted);
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
                    tournament[tournament::PLAYERS][idx][player::DISPLAY_NAME] = dn.as_str().into();
                }
            }

            // Open rounds: a player at their per-player cap can't check in for a new round — but a
            // capped DROP-OUT being reinstated returns to Completed (finals-eligible), not rejected.
            let was_finished =
                tournament[tournament::PLAYERS][idx][player::STATE].as_str() == Some("Finished");
            let max_rounds = tournament[tournament::MAX_ROUNDS].as_usize().unwrap_or(0);
            let at_cap =
                max_rounds > 0 && count_player_rounds_played(tournament, player_uid) >= max_rounds;
            if at_cap && !was_finished {
                return Err(EngineError::PlayerReachedMaxRounds);
            }
            if at_cap {
                // Reinstating a capped drop-out: done with prelims, finals-eligible, no new round.
                tournament[tournament::PLAYERS][idx][player::STATE] = "Completed".into();
                return Ok(());
            }

            let missing_decklist = tournament[tournament::DECKLIST_REQUIRED]
                .as_bool()
                .unwrap_or(false)
                && {
                    let pk = player_uid.as_str();
                    !decks
                        .members()
                        .any(|d| d[deck_object::USER_UID].as_str() == Some(pk))
                };

            // A drop-out reinstated mid-round keeps the seat they never left.
            let seated_live = tournament[tournament::ROUNDS].members().any(|round| {
                round.members().any(|t| {
                    t[table::STATE].as_str() != Some("Finished")
                        && t[table::SEATING]
                            .members()
                            .any(|s| s[seat::PLAYER_UID].as_str() == Some(player_uid.as_str()))
                })
            });
            tournament[tournament::PLAYERS][idx][player::STATE] = if was_finished && seated_live {
                "Playing"
            } else {
                "Checked-in"
            }
            .into();
            if missing_decklist {
                tournament[tournament::PLAYERS][idx][player::MISSING_DECKLIST] = true.into();
            }

            Ok(())
        }

        TournamentEvent::CheckOut { player_uid } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            let idx = find_player_index(&tournament[tournament::PLAYERS], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;

            if tournament[tournament::PLAYERS][idx][player::STATE].as_str() != Some("Checked-in") {
                return Err(EngineError::PlayerNotCheckedIn);
            }

            tournament[tournament::PLAYERS][idx][player::STATE] =
                if state == TournamentState::Finished {
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
            let max_rounds = tournament[tournament::MAX_ROUNDS].as_usize().unwrap_or(0);
            let capped: std::collections::HashSet<String> = if max_rounds > 0 {
                tournament[tournament::PLAYERS]
                    .members()
                    .filter_map(|p| p[player::USER_UID].as_str().map(String::from))
                    .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                    .collect()
            } else {
                std::collections::HashSet::new()
            };
            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                let ps = players[i][player::STATE].as_str().unwrap_or("");
                if ps == "Disqualified" {
                    continue;
                }
                let uid = players[i][player::USER_UID].as_str().unwrap_or("");
                if has_dq_sanction(sanctions, uid)
                    || has_active_suspension(sanctions, uid, &actor.now)
                {
                    continue;
                }
                if capped.contains(uid) {
                    continue;
                }
                if players[i][player::WAITLISTED].as_bool().unwrap_or(false) {
                    continue;
                }
                if ps == "Registered" || (state == TournamentState::Finished && ps == "Finished") {
                    players[i][player::STATE] = "Checked-in".into();
                }
            }
            Ok(())
        }

        TournamentEvent::ResetCheckIn => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                if players[i][player::STATE].as_str() == Some("Checked-in") {
                    players[i][player::STATE] = if state == TournamentState::Finished {
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
            let idx = find_player_index(&tournament[tournament::PLAYERS], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            tournament[tournament::PLAYERS][idx][player::PAYMENT_STATUS] = status.as_str().into();
            Ok(())
        }

        TournamentEvent::SetNonCompeting {
            player_uid,
            non_competing,
        } => {
            require_organizer(actor)?;
            // Blocked after finals are seeded or the tournament is finished, so a
            // proxied↔competing flip can't rewrite a concluded result; mid-prelim toggling is the use case.
            if !tournament[tournament::FINALS].is_null() || state == TournamentState::Finished {
                return Err(EngineError::CannotSetNonCompeting);
            }
            let idx = find_player_index(&tournament[tournament::PLAYERS], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            tournament[tournament::PLAYERS][idx][player::NON_COMPETING] = (*non_competing).into();
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::SetWaitlisted {
            player_uid,
            waitlisted,
        } => {
            require_organizer(actor)?;
            let idx = find_player_index(&tournament[tournament::PLAYERS], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            if *waitlisted
                && tournament[tournament::PLAYERS][idx][player::STATE].as_str()
                    != Some("Registered")
            {
                return Err(EngineError::CannotWaitlistPlayer);
            }
            tournament[tournament::PLAYERS][idx][player::WAITLISTED] = (*waitlisted).into();
            Ok(())
        }

        TournamentEvent::MarkAllPaid => {
            require_organizer(actor)?;
            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                if players[i][player::PAYMENT_STATUS].as_str() == Some("Pending") {
                    players[i][player::PAYMENT_STATUS] = "Paid".into();
                }
            }
            Ok(())
        }

        TournamentEvent::StartRound {
            seating: submitted_seating,
        } => {
            require_organizer(actor)?;
            let is_online = tournament[tournament::ONLINE].as_bool().unwrap_or(false);
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

            if !tournament[tournament::FINALS].is_null() {
                return Err(EngineError::PrelimAfterFinals);
            }

            // max_rounds is a per-player cap, not tournament-wide — more rounds may
            // run for players who haven't hit it yet.
            let max_rounds = tournament[tournament::MAX_ROUNDS].as_usize().unwrap_or(0);

            // Playing counts too, for online parallel rounds.
            let checked_in: Vec<String> = tournament[tournament::PLAYERS]
                .members()
                .filter(|p| {
                    let s = p[player::STATE].as_str();
                    s == Some("Checked-in") || (is_online && s == Some("Playing"))
                })
                .filter_map(|p| p[player::USER_UID].as_str().map(|s| s.to_string()))
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
                    tournament[tournament::UID].as_str().unwrap_or(""),
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
                                seat::PLAYER_UID => player_uid.as_str(),
                                seat::RESULT => json::object!{ score::GW => 0, score::VP => 0.0, score::TP => 0 },
                                seat::JUDGE_UID => "",
                            }
                        })
                        .collect();
                    json::object! {
                        table::SEATING => seating,
                        table::STATE => "In Progress",
                        table::OVERRIDE => json::Null,
                    }
                })
                .collect();

            tournament[tournament::ROUNDS].push(JsonValue::Array(tables))?;
            if state != TournamentState::Finished {
                tournament[tournament::STATE] = "Playing".into();
            }

            let seated_uids: std::collections::HashSet<String> = new_round
                .iter()
                .flat_map(|table| table.iter().cloned())
                .collect();

            // Only round 1 of a standard tournament withdraws no-show Registered players
            // (reinstatable via CheckIn/SeatPlayer); later and open rounds leave them untouched.
            let prior_real_rounds = (0..tournament[tournament::ROUNDS].len().saturating_sub(1))
                .filter(|&r| {
                    tournament[tournament::ROUNDS][r]
                        .members()
                        .any(|t| t[table::STATE].as_str() != Some("Cancelled"))
                })
                .count();
            let open_rounds = tournament[tournament::OPEN_ROUNDS]
                .as_bool()
                .unwrap_or(false);
            let drop_no_shows = prior_real_rounds == 0 && !open_rounds;

            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                match players[i][player::STATE].as_str() {
                    Some("Checked-in") => {
                        if let Some(uid) = players[i][player::USER_UID].as_str() {
                            if seated_uids.contains(uid) {
                                players[i][player::STATE] = "Playing".into();
                            }
                        }
                    }
                    Some("Registered")
                        if drop_no_shows
                            && !players[i][player::WAITLISTED].as_bool().unwrap_or(false) =>
                    {
                        players[i][player::STATE] = "Finished".into()
                    }
                    _ => {}
                }
            }

            stamp_round_decks(
                tournament,
                decks,
                deck_ops,
                tournament[tournament::ROUNDS].len() - 1,
            );
            Ok(())
        }

        TournamentEvent::SelfOrganizeRound { player_uids } => {
            // NOT organizer-gated: integrity gate is registration only — collusion risk
            // accepted, mitigated by organizer veto (FinishRound/CancelRound/Override).
            if !tournament[tournament::SELF_ORGANIZED_ROUNDS]
                .as_bool()
                .unwrap_or(false)
            {
                return Err(EngineError::SelfOrganizeDisabled);
            }
            // 0 == no per-player cap; only enforced below when a cap is set.
            let max_rounds = tournament[tournament::MAX_ROUNDS].as_usize().unwrap_or(0);
            // Same state rule as an online parallel StartRound: seat while Waiting/Playing.
            if state != TournamentState::Waiting && state != TournamentState::Playing {
                return Err(EngineError::WrongState {
                    expected: "Waiting".to_string(),
                    current: state.as_str().to_string(),
                });
            }
            if !tournament[tournament::FINALS].is_null() {
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
                let p = tournament[tournament::PLAYERS]
                    .members()
                    .find(|p| p[player::USER_UID].as_str() == Some(uid.as_str()))
                    .ok_or(EngineError::NotRegistered)?;
                let pstate = p[player::STATE].as_str().unwrap_or("");
                if pstate == "Disqualified" {
                    return Err(EngineError::PlayerDisqualified);
                }
                if pstate != "Registered" && pstate != "Checked-in" {
                    return Err(EngineError::SelfOrganizeIneligible {
                        player: uid.clone(),
                    });
                }
                if p[player::WAITLISTED].as_bool().unwrap_or(false) {
                    return Err(EngineError::PlayerWaitlisted);
                }
                if max_rounds > 0 && count_player_rounds_played(tournament, uid) >= max_rounds {
                    return Err(EngineError::PlayerReachedMaxRounds);
                }
            }
            let previous_rounds = collect_previous_rounds(tournament);
            let seed = seating::seed_for_round(
                tournament[tournament::UID].as_str().unwrap_or(""),
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
                                seat::PLAYER_UID => player_uid.as_str(),
                                seat::RESULT => json::object!{ score::GW => 0, score::VP => 0.0, score::TP => 0 },
                                seat::JUDGE_UID => "",
                            }
                        })
                        .collect();
                    json::object! {
                        table::SEATING => seating,
                        table::STATE => "In Progress",
                        table::OVERRIDE => json::Null,
                        table::ORGANIZED_BY => actor.uid.as_str(),
                    }
                })
                .collect();
            tournament[tournament::ROUNDS].push(JsonValue::Array(tables))?;
            tournament[tournament::STATE] = "Playing".into();
            // Seat ONLY the chosen players; every other Registered player stays available
            // (unlike StartRound, which withdraws unseated Registered players).
            let seated: std::collections::HashSet<&str> =
                player_uids.iter().map(|s| s.as_str()).collect();
            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                if let Some(uid) = players[i][player::USER_UID].as_str() {
                    if seated.contains(uid) {
                        players[i][player::STATE] = "Playing".into();
                    }
                }
            }
            stamp_round_decks(
                tournament,
                decks,
                deck_ops,
                tournament[tournament::ROUNDS].len() - 1,
            );
            Ok(())
        }

        TournamentEvent::FinishRound { round } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &tournament[tournament::ROUNDS];
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
                .filter(|(_, t)| t[table::STATE].as_str() != Some("Finished"))
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
            let max_rounds = tournament[tournament::MAX_ROUNDS].as_usize().unwrap_or(0);
            let maxed: std::collections::HashSet<String> =
                if max_rounds > 0 && state != TournamentState::Finished {
                    tournament[tournament::PLAYERS]
                        .members()
                        .filter_map(|p| p[player::USER_UID].as_str().map(String::from))
                        .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                        .collect()
                } else {
                    std::collections::HashSet::new()
                };
            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                if players[i][player::STATE].as_str() == Some("Playing") {
                    if let Some(uid) = players[i][player::USER_UID].as_str() {
                        if !still_playing.contains(uid) {
                            players[i][player::STATE] = if maxed.contains(uid) {
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
                tournament[tournament::STATE] = "Waiting".into();
            }
            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::CancelRound { round } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let len = tournament[tournament::ROUNDS].len();
            if len == 0 {
                return Err(EngineError::NoRoundToCancel);
            }
            let target_idx = round.unwrap_or(len - 1);
            if target_idx >= len {
                return Err(EngineError::InvalidRound);
            }

            if target_idx == len - 1 {
                // Last round: hard-remove — no later round's index can shift.
                tournament[tournament::ROUNDS].array_remove(len - 1);
                let mut removed = vec![len - 1];
                loop {
                    let n = tournament[tournament::ROUNDS].len();
                    if n == 0 {
                        break;
                    }
                    let last = &tournament[tournament::ROUNDS][n - 1];
                    if last.is_empty()
                        || !last
                            .members()
                            .all(|t| t[table::STATE].as_str() == Some("Cancelled"))
                    {
                        break;
                    }
                    tournament[tournament::ROUNDS].array_remove(n - 1);
                    removed.push(n - 1);
                }
                release_stamped_decks(decks, deck_ops, &removed, None);
                // update_standings keeps a rounds-less tournament's standings, for the
                // round-less VEKN imports; a cancel must not inherit that.
                if tournament[tournament::ROUNDS].is_empty() {
                    tournament[tournament::STANDINGS] = JsonValue::new_array();
                }
            } else {
                // Soft-cancel: mark tables Cancelled, keep the slot — a mid-array removal
                // would shift deck.round / standings_adjustment.round_number, which are index-tagged.
                let r = &mut tournament[tournament::ROUNDS][target_idx];
                for i in 0..r.len() {
                    r[i][table::STATE] = "Cancelled".into();
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
            let max_rounds = tournament[tournament::MAX_ROUNDS].as_usize().unwrap_or(0);
            let rearm: std::collections::HashSet<String> =
                if max_rounds > 0 && state != TournamentState::Finished {
                    tournament[tournament::PLAYERS]
                        .members()
                        .filter(|p| p[player::STATE].as_str() == Some("Completed"))
                        .filter_map(|p| p[player::USER_UID].as_str().map(String::from))
                        .filter(|uid| count_player_rounds_played(tournament, uid) < max_rounds)
                        .collect()
                } else {
                    std::collections::HashSet::new()
                };
            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                let st = players[i][player::STATE].as_str();
                let uid = players[i][player::USER_UID].as_str().map(String::from);
                if st == Some("Playing") {
                    if let Some(uid) = uid {
                        if !still_playing.contains(&uid) {
                            players[i][player::STATE] = target_state.into();
                        }
                    }
                } else if st == Some("Completed") {
                    if let Some(uid) = uid {
                        if rearm.contains(&uid) {
                            players[i][player::STATE] = target_state.into();
                        }
                    }
                }
            }

            if state != TournamentState::Finished
                && (all_rounds_finished(tournament) || tournament[tournament::ROUNDS].is_empty())
            {
                tournament[tournament::STATE] = "Waiting".into();
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
            if !tournament[tournament::FINALS].is_null() {
                return Err(EngineError::PrelimAfterFinals);
            }

            let len = tournament[tournament::ROUNDS].len();
            let target_idx = round.ok_or(EngineError::InvalidRound)?;
            if target_idx >= len {
                return Err(EngineError::InvalidRound);
            }
            // Only a fully-Cancelled round is restorable (the last round is hard-
            // removed on cancel, so any Cancelled round is a non-last soft-cancel).
            if tournament[tournament::ROUNDS][target_idx].is_empty()
                || !tournament[tournament::ROUNDS][target_idx]
                    .members()
                    .all(|t| t[table::STATE].as_str() == Some("Cancelled"))
            {
                return Err(EngineError::RoundNotCancelled);
            }

            let seated: std::collections::HashSet<String> = tournament[tournament::ROUNDS]
                [target_idx]
                .members()
                .flat_map(|t| t[table::SEATING].members())
                .filter_map(|s| s[seat::PLAYER_UID].as_str().map(String::from))
                .collect();

            // All-or-nothing: reject the whole restore if any seated player can no longer
            // be reinstated. Runs before any mutation; the cap check sees this round still Cancelled.
            let max_rounds = tournament[tournament::MAX_ROUNDS].as_usize().unwrap_or(0);
            for uid in &seated {
                let pstate = tournament[tournament::PLAYERS]
                    .members()
                    .find(|p| p[player::USER_UID].as_str() == Some(uid.as_str()))
                    .and_then(|p| p[player::STATE].as_str());
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
                let r = &mut tournament[tournament::ROUNDS][target_idx];
                for i in 0..r.len() {
                    let new_state = if !r[i][table::OVERRIDE].is_null() {
                        "Finished"
                    } else {
                        let size = r[i][table::SEATING].len();
                        let vps: Vec<f64> = (0..size)
                            .map(|j| {
                                r[i][table::SEATING][j][seat::RESULT][score::VP]
                                    .as_f64()
                                    .unwrap_or(0.0)
                            })
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
                    r[i][table::STATE] = new_state.into();
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
            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                let uid = match players[i][player::USER_UID].as_str() {
                    Some(u) => u.to_string(),
                    None => continue,
                };
                if !seated.contains(&uid) {
                    continue;
                }
                if players[i][player::STATE].as_str() == Some("Playing") {
                    continue;
                }
                players[i][player::STATE] = if round_is_live {
                    "Playing"
                } else if capped.contains(&uid) {
                    "Completed"
                } else {
                    "Checked-in"
                }
                .into();
            }

            if round_is_live {
                tournament[tournament::STATE] = "Playing".into();
            } else if all_rounds_finished(tournament) {
                tournament[tournament::STATE] = "Waiting".into();
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
            let is_finals = *round == tournament[tournament::ROUNDS].len()
                && !tournament[tournament::FINALS].is_null()
                && *table1 == 0
                && *table2 == 0;

            if is_finals {
                let seating = &mut tournament[tournament::FINALS][finals_table::SEATING];
                if *seat1 >= seating.len() || *seat2 >= seating.len() {
                    return Err(EngineError::InvalidSeat);
                }
                let uid1 = seating[*seat1][seat::PLAYER_UID]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                let uid2 = seating[*seat2][seat::PLAYER_UID]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                seating[*seat1][seat::PLAYER_UID] = uid2.as_str().into();
                seating[*seat2][seat::PLAYER_UID] = uid1.as_str().into();
            } else {
                let rounds = &mut tournament[tournament::ROUNDS];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                let round_tables = &mut rounds[*round];
                if *table1 >= round_tables.len() || *table2 >= round_tables.len() {
                    return Err(EngineError::InvalidTable);
                }
                if *seat1 >= round_tables[*table1][table::SEATING].len()
                    || *seat2 >= round_tables[*table2][table::SEATING].len()
                {
                    return Err(EngineError::InvalidSeat);
                }
                let uid1 = round_tables[*table1][table::SEATING][*seat1][seat::PLAYER_UID]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                let uid2 = round_tables[*table2][table::SEATING][*seat2][seat::PLAYER_UID]
                    .as_str()
                    .ok_or(EngineError::InvalidSeat)?
                    .to_string();
                round_tables[*table1][table::SEATING][*seat1][seat::PLAYER_UID] =
                    uid2.as_str().into();
                round_tables[*table2][table::SEATING][*seat2][seat::PLAYER_UID] =
                    uid1.as_str().into();
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

            let rounds_len = tournament[tournament::ROUNDS].len();
            let is_finals = *round == rounds_len && !tournament[tournament::FINALS].is_null();

            {
                let all_uids: Vec<&String> = seating.iter().flat_map(|t| t.iter()).collect();
                let unique: std::collections::HashSet<&String> = all_uids.iter().copied().collect();
                if all_uids.len() != unique.len() {
                    return Err(EngineError::DuplicatePlayer);
                }
            }

            if is_finals {
                let finals = &mut tournament[tournament::FINALS][finals_table::SEATING];
                if seating.len() != 1 {
                    return Err(EngineError::FinalsOneTable);
                }
                let new_players = &seating[0];
                if new_players.len() != finals.len() {
                    return Err(EngineError::FinalsPlayerCount);
                }
                let old_set: std::collections::HashSet<String> = (0..finals.len())
                    .map(|i| {
                        finals[i][seat::PLAYER_UID]
                            .as_str()
                            .unwrap_or("")
                            .to_string()
                    })
                    .collect();
                let new_set: std::collections::HashSet<&String> = new_players.iter().collect();
                if old_set.len() != new_set.len()
                    || !new_players.iter().all(|uid| old_set.contains(uid))
                {
                    return Err(EngineError::FinalsPlayerSet);
                }
                for (i, uid) in new_players.iter().enumerate() {
                    finals[i][seat::PLAYER_UID] = uid.as_str().into();
                }
            } else {
                if *round >= rounds_len {
                    return Err(EngineError::InvalidRound);
                }

                // Positional: tables 0..table_count match existing by index (results
                // preserved per index); extras appended; empty tables are draft
                // workspaces, dropped after rebuild.
                let table_count = tournament[tournament::ROUNDS][*round].len();
                if seating.len() < table_count {
                    return Err(EngineError::TableCountMismatch);
                }
                for table in seating.iter() {
                    if !table.is_empty() && !(4..=5).contains(&table.len()) {
                        return Err(EngineError::InvalidTableSize { size: table.len() });
                    }
                }
                if seating.iter().all(|t| t.is_empty()) {
                    return Err(EngineError::EmptyRound);
                }
                for uid in seating.iter().flat_map(|t| t.iter()) {
                    if !player_exists(&tournament[tournament::PLAYERS], uid) {
                        return Err(EngineError::PlayerNotFound);
                    }
                }

                // Read before the rebuild: it resets reseated tables to In Progress,
                // so a finished round would look live to the state rules below.
                let round_is_live = tournament[tournament::ROUNDS][*round]
                    .members()
                    .any(|table| {
                        !matches!(
                            table[table::STATE].as_str(),
                            Some("Finished") | Some("Cancelled")
                        )
                    });

                let mut old_results: std::collections::HashMap<String, (usize, JsonValue, String)> =
                    std::collections::HashMap::new();
                for t in 0..table_count {
                    for s in 0..tournament[tournament::ROUNDS][*round][t][table::SEATING].len() {
                        let uid = tournament[tournament::ROUNDS][*round][t][table::SEATING][s]
                            [seat::PLAYER_UID]
                            .as_str()
                            .unwrap_or("")
                            .to_string();
                        let result = tournament[tournament::ROUNDS][*round][t][table::SEATING][s]
                            [seat::RESULT]
                            .clone();
                        let judge = tournament[tournament::ROUNDS][*round][t][table::SEATING][s]
                            [seat::JUDGE_UID]
                            .as_str()
                            .unwrap_or("")
                            .to_string();
                        old_results.insert(uid, (t, result, judge));
                    }
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

                let round_data = &mut tournament[tournament::ROUNDS][*round];

                for t in 0..seating.len() {
                    if t >= round_data.len() {
                        round_data.push(json::object! {
                            table::SEATING => json::array![],
                            table::STATE => "In Progress",
                            table::OVERRIDE => json::Null,
                        })?;
                    }
                    let new_players = &seating[t];
                    let mut new_seating = Vec::new();
                    for uid in new_players {
                        let (result, judge) = match old_results.get(uid) {
                            Some((old_table, old_result, old_judge)) if *old_table == t => {
                                (old_result.clone(), old_judge.as_str())
                            }
                            _ => (
                                json::object! { score::GW => 0, score::VP => 0.0, score::TP => 0 },
                                "",
                            ),
                        };
                        new_seating.push(json::object! {
                            seat::PLAYER_UID => uid.as_str(),
                            seat::RESULT => result,
                            seat::JUDGE_UID => judge,
                        });
                    }
                    round_data[t][table::SEATING] = JsonValue::Array(new_seating);

                    let vps: Vec<f64> = (0..round_data[t][table::SEATING].len())
                        .map(|s| {
                            round_data[t][table::SEATING][s][seat::RESULT][score::VP]
                                .as_f64()
                                .unwrap_or(0.0)
                        })
                        .collect();
                    if round_data[t][table::OVERRIDE].is_null() {
                        let all_zero = vps.iter().all(|&v| v == 0.0);
                        if all_zero {
                            round_data[t][table::STATE] = "In Progress".into();
                        }
                    }
                }

                for t in (0..round_data.len()).rev() {
                    if round_data[t][table::SEATING].is_empty() {
                        round_data.array_remove(t);
                    }
                }

                if round_is_live {
                    let new_set: std::collections::HashSet<&String> =
                        seating.iter().flat_map(|t| t.iter()).collect();
                    let joined: Vec<String> = new_set
                        .iter()
                        .filter(|uid| !old_results.contains_key(**uid))
                        .map(|uid| (*uid).clone())
                        .collect();
                    let left: std::collections::HashSet<String> = old_results
                        .keys()
                        .filter(|uid| !new_set.contains(uid))
                        .cloned()
                        .collect();
                    let joined_state = if state == TournamentState::Finished {
                        "Finished"
                    } else {
                        "Playing"
                    };
                    for uid in joined {
                        if has_dq_sanction(sanctions, &uid) {
                            continue;
                        }
                        if let Some(idx) = find_player_index(&tournament[tournament::PLAYERS], &uid)
                        {
                            if tournament[tournament::PLAYERS][idx][player::STATE].as_str()
                                == Some("Disqualified")
                            {
                                continue;
                            }
                            tournament[tournament::PLAYERS][idx][player::STATE] =
                                joined_state.into();
                            tournament[tournament::PLAYERS][idx][player::WAITLISTED] = false.into();
                        }
                    }
                    demote_unseated_players(tournament, &left, *round);
                }

                let seated_now: std::collections::HashSet<&String> =
                    seating.iter().flat_map(|t| t.iter()).collect();
                for uid in old_results.keys().filter(|u| !seated_now.contains(u)) {
                    release_stamped_decks(decks, deck_ops, &[*round], Some(uid));
                }
                stamp_round_decks(tournament, decks, deck_ops, *round);
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
            let player_idx = find_player_index(&tournament[tournament::PLAYERS], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            let player_state = tournament[tournament::PLAYERS][player_idx][player::STATE]
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
            let rounds = &mut tournament[tournament::ROUNDS];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = resolve_live_round(rounds, *round)?;
            if *table >= rounds[last].len() {
                return Err(EngineError::InvalidTable);
            }

            let seating = &mut rounds[last][*table][table::SEATING];
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
                seat::PLAYER_UID => player_uid.as_str(),
                seat::RESULT => json::object!{ score::GW => 0, score::VP => 0.0, score::TP => 0 },
                seat::JUDGE_UID => "",
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
            rounds[last][*table][table::SEATING] = JsonValue::Array(new_seating);

            tournament[tournament::PLAYERS][player_idx][player::STATE] =
                if state == TournamentState::Finished {
                    "Finished"
                } else {
                    "Playing"
                }
                .into();
            tournament[tournament::PLAYERS][player_idx][player::WAITLISTED] = false.into();
            update_standings(tournament, sanctions);
            stamp_round_decks(tournament, decks, deck_ops, last);
            Ok(())
        }

        TournamentEvent::UnseatPlayer { player_uid, round } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament[tournament::ROUNDS];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = resolve_live_round(rounds, *round)?;

            let mut found = false;
            for t in 0..rounds[last].len() {
                let seating = &rounds[last][t][table::SEATING];
                let mut seat_idx = None;
                for s in 0..seating.len() {
                    if seating[s][seat::PLAYER_UID].as_str() == Some(player_uid) {
                        seat_idx = Some(s);
                        break;
                    }
                }
                if let Some(s) = seat_idx {
                    rounds[last][t][table::SEATING].array_remove(s);
                    found = true;
                    break;
                }
            }

            if !found {
                return Err(EngineError::PlayerNotInRound {
                    player: player_uid.to_string(),
                });
            }

            demote_unseated_players(
                tournament,
                &std::iter::once(player_uid.clone()).collect(),
                last,
            );
            update_standings(tournament, sanctions);
            release_stamped_decks(decks, deck_ops, &[last], Some(player_uid));
            Ok(())
        }

        TournamentEvent::AddTable => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament[tournament::ROUNDS];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = rounds.len() - 1;

            let empty_table = json::object! {
                table::SEATING => json::array![],
                table::STATE => "In Progress",
                table::OVERRIDE => json::Null,
            };
            rounds[last].push(empty_table)?;
            Ok(())
        }

        TournamentEvent::RemoveTable { table } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament[tournament::ROUNDS];
            if rounds.is_empty() {
                return Err(EngineError::NoRoundInProgress);
            }
            let last = rounds.len() - 1;
            if *table >= rounds[last].len() {
                return Err(EngineError::InvalidTable);
            }
            if !rounds[last][*table][table::SEATING].is_empty() {
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

            let rounds_len = tournament[tournament::ROUNDS].len();
            let is_finals =
                *round == rounds_len && !tournament[tournament::FINALS].is_null() && *table == 0;

            // Resolved before the mutable borrow of `t` below: scores don't move
            // seats, so this ordering is equivalent and avoids a borrow conflict.
            let effective_sas = sanctions::resolve_sa_effective_rounds(tournament, sanctions);

            let t = if is_finals {
                &mut tournament[tournament::FINALS]
            } else {
                let rounds = &tournament[tournament::ROUNDS];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                if *table >= rounds[*round].len() {
                    return Err(EngineError::InvalidTable);
                }
                &mut tournament[tournament::ROUNDS][*round][*table]
            };

            let is_at_table = t[table::SEATING]
                .members()
                .any(|s| s[seat::PLAYER_UID].as_str() == Some(&actor.uid));

            if !actor.is_organizer && !is_at_table {
                return Err(EngineError::ScoreForbidden);
            }

            if !t[table::OVERRIDE].is_null() && !actor.is_organizer {
                return Err(EngineError::ScoreLocked);
            }

            if !actor.is_organizer {
                let has_judge_score = t[table::SEATING]
                    .members()
                    .any(|s| !s[seat::JUDGE_UID].as_str().unwrap_or("").is_empty());
                if has_judge_score {
                    return Err(EngineError::ScoreSetByOrganizer);
                }
            }

            let table_size = t[table::SEATING].len();

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
                let player_uid = t[table::SEATING][i][seat::PLAYER_UID]
                    .as_str()
                    .unwrap_or("");
                let vp = vp_map.get(player_uid).copied().unwrap_or(
                    t[table::SEATING][i][seat::RESULT][score::VP]
                        .as_f64()
                        .unwrap_or(0.0),
                );
                vps.push(vp);
            }

            // Per-seat SA adjustments (-1.0 VP per SA on this round). Same helper the
            // standings/rating recompute uses, so GW/TP stay consistent everywhere.
            let current_round = if is_finals { rounds_len } else { *round };
            let adjustments =
                table_sa_adjustments(&t[table::SEATING], current_round, &effective_sas);

            let gws = if is_finals {
                let seating_uids: Vec<&str> = (0..table_size)
                    .map(|i| {
                        t[table::SEATING][i][seat::PLAYER_UID]
                            .as_str()
                            .unwrap_or("")
                    })
                    .collect();
                let seed_order: Vec<String> = t[finals_table::SEED_ORDER]
                    .members()
                    .filter_map(|s| s.as_str().map(|v| v.to_string()))
                    .collect();
                compute_gw_finals(&vps, &adjustments, &seating_uids, &seed_order)
            } else {
                compute_gw(&vps, &adjustments)
            };
            let tps = compute_tp(table_size, &vps, &adjustments);

            for i in 0..table_size {
                let player_uid = t[table::SEATING][i][seat::PLAYER_UID]
                    .as_str()
                    .unwrap_or("")
                    .to_string();
                if vp_map.contains_key(player_uid.as_str()) {
                    t[table::SEATING][i][seat::RESULT][score::VP] = vps[i].into();
                    t[table::SEATING][i][seat::RESULT][score::GW] = gws[i].into();
                    t[table::SEATING][i][seat::RESULT][score::TP] = tps[i].into();
                    // A seated organizer plays, not adjudicates: stamping would lock
                    // their own tablemates out. Override still locks a table you sit at.
                    if actor.is_organizer && !is_at_table {
                        t[table::SEATING][i][seat::JUDGE_UID] = actor.uid.as_str().into();
                    }
                }
            }

            if t[table::OVERRIDE].is_null() {
                let vp_err = check_table_vps(&vps);
                match vp_err {
                    Some(VpError::IncompleteTotal) => {
                        t[table::STATE] = "In Progress".into();
                    }
                    Some(VpError::RedirectedVp) => {
                        // Previously read as a half-filled table and accepted; keep
                        // accepting, but flag what it is — only a judge can close it.
                        t[table::STATE] = "Invalid".into();
                    }
                    Some(_) => {
                        if !actor.is_organizer {
                            return Err(EngineError::InvalidScore);
                        }
                        t[table::STATE] = "Invalid".into();
                    }
                    None => {
                        t[table::STATE] = "Finished".into();
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

            let is_finals = *round == tournament[tournament::ROUNDS].len()
                && !tournament[tournament::FINALS].is_null()
                && *table == 0;
            let t = if is_finals {
                &mut tournament[tournament::FINALS]
            } else {
                let rounds = &tournament[tournament::ROUNDS];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                if *table >= rounds[*round].len() {
                    return Err(EngineError::InvalidTable);
                }
                &mut tournament[tournament::ROUNDS][*round][*table]
            };
            t[table::OVERRIDE] = json::object! {
                score_override::JUDGE_UID => actor.uid.as_str(),
                score_override::COMMENT => comment.as_str(),
            };
            t[table::STATE] = "Finished".into();

            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::Unoverride { round, table } => {
            require_organizer(actor)?;
            require_can_edit_results(actor, state)?;

            let is_finals = *round == tournament[tournament::ROUNDS].len()
                && !tournament[tournament::FINALS].is_null()
                && *table == 0;
            let t = if is_finals {
                &mut tournament[tournament::FINALS]
            } else {
                let rounds = &tournament[tournament::ROUNDS];
                if *round >= rounds.len() {
                    return Err(EngineError::InvalidRound);
                }
                if *table >= rounds[*round].len() {
                    return Err(EngineError::InvalidTable);
                }
                &mut tournament[tournament::ROUNDS][*round][*table]
            };
            t[table::OVERRIDE] = json::Null;

            let table_size = t[table::SEATING].len();
            let vps: Vec<f64> = (0..table_size)
                .map(|i| {
                    t[table::SEATING][i][seat::RESULT][score::VP]
                        .as_f64()
                        .unwrap_or(0.0)
                })
                .collect();
            let vp_err = check_table_vps(&vps);
            match vp_err {
                Some(VpError::IncompleteTotal) => {
                    t[table::STATE] = "In Progress".into();
                }
                Some(_) => {
                    t[table::STATE] = "Invalid".into();
                }
                None => {
                    t[table::STATE] = "Finished".into();
                }
            }

            update_standings(tournament, sanctions);
            Ok(())
        }

        TournamentEvent::SetToss { player_uid, toss } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if count_played_rounds(tournament) < 2 {
                return Err(EngineError::TossMinRounds);
            }
            let idx = find_player_index(&tournament[tournament::PLAYERS], player_uid)
                .ok_or(EngineError::PlayerNotFound)?;
            tournament[tournament::PLAYERS][idx][player::TOSS] = (*toss).into();
            Ok(())
        }

        TournamentEvent::RandomToss => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if count_played_rounds(tournament) < 2 {
                return Err(EngineError::TossMinRounds);
            }

            let standings = compute_preliminary_standings(tournament, sanctions);
            let candidates = finals_candidates(&tournament[tournament::PLAYERS], &standings);

            // The client applies this event through WASM before the server replays it,
            // so the shuffle must be a pure function of the tournament — an OS random
            // source would leave the two copies seating a different top five.
            let seed: u64 = tournament[tournament::UID]
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
                    if let Some(pi) =
                        find_player_index(&tournament[tournament::PLAYERS], &s.user_uid)
                    {
                        tournament[tournament::PLAYERS][pi][player::TOSS] = toss_counter.into();
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
            if !tournament[tournament::FINALS].is_null() {
                return Err(EngineError::FinalsAlreadyStarted);
            }

            let standings = compute_preliminary_standings(tournament, sanctions);
            let eligible = finals_candidates(&tournament[tournament::PLAYERS], &standings);

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
                        seat::PLAYER_UID => s.user_uid.as_str(),
                        seat::RESULT => json::object!{ score::GW => 0, score::VP => 0.0, score::TP => 0 },
                        seat::JUDGE_UID => "",
                    }
                })
                .collect();

            tournament[tournament::FINALS] = json::object! {
                finals_table::SEATING => JsonValue::Array(seating),
                finals_table::STATE => "In Progress",
                finals_table::OVERRIDE => json::Null,
                finals_table::SEED_ORDER => JsonValue::Array(seed_order),
            };

            for s in &top5 {
                if let Some(idx) = find_player_index(&tournament[tournament::PLAYERS], &s.user_uid)
                {
                    tournament[tournament::PLAYERS][idx][player::STATE] = "Playing".into();
                    tournament[tournament::PLAYERS][idx][player::FINALIST] = true.into();
                }
            }

            if state != TournamentState::Finished {
                tournament[tournament::STATE] = "Playing".into();
            }
            stamp_round_decks(
                tournament,
                decks,
                deck_ops,
                tournament[tournament::ROUNDS].len(),
            );
            Ok(())
        }

        TournamentEvent::FinishFinals => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;
            if tournament[tournament::FINALS].is_null() {
                return Err(EngineError::NoFinalsInProgress);
            }

            let finals_state = tournament[tournament::FINALS][finals_table::STATE]
                .as_str()
                .unwrap_or("");
            if finals_state != "Finished" {
                return Err(EngineError::FinalsTableUnfinished);
            }

            // compute_gw_finals is the single source of finals-winner derivation — the same
            // call SetScore and update_standings use, so the winner can never diverge from the scored GW.
            let effective_sas = sanctions::resolve_sa_effective_rounds(tournament, sanctions);
            let finals_round = tournament[tournament::ROUNDS].len();
            let seating = &tournament[tournament::FINALS][finals_table::SEATING];
            let vps: Vec<f64> = seating
                .members()
                .map(|s| s[seat::RESULT][score::VP].as_f64().unwrap_or(0.0))
                .collect();
            let seating_uids: Vec<&str> = seating
                .members()
                .map(|s| s[seat::PLAYER_UID].as_str().unwrap_or(""))
                .collect();
            let adjustments = table_sa_adjustments(seating, finals_round, &effective_sas);
            let seed_order: Vec<String> = tournament[tournament::FINALS][finals_table::SEED_ORDER]
                .members()
                .filter_map(|s| s.as_str().map(|v| v.to_string()))
                .collect();
            let gws = compute_gw_finals(&vps, &adjustments, &seating_uids, &seed_order);
            let winner = gws
                .iter()
                .position(|&g| g == 1.0)
                .map(|i| seating_uids[i].to_string())
                .unwrap_or_default();

            tournament[tournament::WINNER] = winner.as_str().into();
            if state != TournamentState::Finished {
                tournament[tournament::STATE] = "Finished".into();
            }

            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                if players[i][player::STATE].as_str() != Some("Disqualified") {
                    players[i][player::STATE] = "Finished".into();
                }
            }

            update_standings(tournament, sanctions);

            for d in decks.members() {
                let user_uid = d[deck_object::USER_UID].as_str().unwrap_or("");
                if user_uid.is_empty() {
                    continue;
                }
                let is_public = compute_deck_public(tournament, user_uid);
                if is_public {
                    let op = json::object! {
                        arg::OP => "set_public",
                        arg::DECK_UID => d[deck_object::UID].as_str().unwrap_or(""),
                        arg::PUBLIC => true,
                    };
                    let _ = deck_ops.push(op);
                }
            }

            Ok(())
        }

        TournamentEvent::CancelFinals => {
            // Revert a not-yet-finalized finals to Waiting so the organizer can drop a
            // no-show and re-run StartFinals, which promotes the next qualifier.
            require_organizer(actor)?;
            require_state(state, TournamentState::Playing)?;
            if tournament[tournament::FINALS].is_null() {
                return Err(EngineError::NoFinalsInProgress);
            }

            // Capped (open-rounds) finalists return to Completed; the rest to Checked-in.
            let max_rounds = tournament[tournament::MAX_ROUNDS].as_usize().unwrap_or(0);
            let capped: std::collections::HashSet<String> = if max_rounds > 0 {
                tournament[tournament::PLAYERS]
                    .members()
                    .filter(|p| p[player::FINALIST].as_bool().unwrap_or(false))
                    .filter_map(|p| p[player::USER_UID].as_str().map(String::from))
                    .filter(|uid| count_player_rounds_played(tournament, uid) >= max_rounds)
                    .collect()
            } else {
                std::collections::HashSet::new()
            };
            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                if players[i][player::FINALIST].as_bool().unwrap_or(false) {
                    let uid = players[i][player::USER_UID]
                        .as_str()
                        .unwrap_or("")
                        .to_string();
                    players[i][player::FINALIST] = false.into();
                    players[i][player::STATE] = if capped.contains(&uid) {
                        "Completed"
                    } else {
                        "Checked-in"
                    }
                    .into();
                }
            }

            tournament[tournament::FINALS] = json::Null;
            // "" (not null): the backend Tournament model types `winner` as `str`, so a
            // null fails msgspec validation and 500s the action.
            tournament[tournament::WINNER] = "".into();
            tournament[tournament::STATE] = "Waiting".into();
            update_standings(tournament, sanctions);
            release_stamped_decks(
                decks,
                deck_ops,
                &[tournament[tournament::ROUNDS].len()],
                None,
            );
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

            tournament[tournament::STATE] = "Finished".into();

            let players = &mut tournament[tournament::PLAYERS];
            for i in 0..players.len() {
                if players[i][player::STATE].as_str() != Some("Disqualified") {
                    players[i][player::STATE] = "Finished".into();
                }
            }

            update_standings(tournament, sanctions);

            for d in decks.members() {
                let user_uid = d[deck_object::USER_UID].as_str().unwrap_or("");
                if user_uid.is_empty() {
                    continue;
                }
                let is_public = compute_deck_public(tournament, user_uid);
                if is_public {
                    let op = json::object! {
                        arg::OP => "set_public",
                        arg::DECK_UID => d[deck_object::UID].as_str().unwrap_or(""),
                        arg::PUBLIC => true,
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
            if tournament[tournament::FORMAT].as_str() == Some("Storyline") {
                return Err(EngineError::FormatForbidsDecks);
            }
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err(EngineError::DeckUploadForbidden);
            }
            let is_registered = tournament[tournament::PLAYERS]
                .members()
                .any(|p| p[player::USER_UID].as_str() == Some(player_uid.as_str()));
            if !is_registered {
                return Err(EngineError::NotRegistered);
            }
            let existing_count = decks
                .members()
                .filter(|d| d[deck_object::USER_UID].as_str() == Some(player_uid.as_str()))
                .count();
            if !actor.is_organizer {
                match state {
                    TournamentState::Playing if !*multideck && existing_count > 0 => {
                        return Err(EngineError::DeckLockedPlaying);
                    }
                    TournamentState::Finished if existing_count > 0 => {
                        return Err(EngineError::DeckLockedFinished);
                    }
                    _ => {}
                }
            }
            let is_public = compute_deck_public(tournament, player_uid);
            let mut deck_data = deck.clone();
            deck_data[deck_object::PUBLIC] = is_public.into();
            if !actor.is_organizer {
                deck_data[deck_object::ROUND] = JsonValue::Null;
            }
            let op = json::object! {
                arg::OP => "upsert",
                arg::PLAYER_UID => player_uid.as_str(),
                arg::DECK => deck_data,
                arg::MULTIDECK => *multideck,
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
                if *multideck && deck_index.is_some() {
                    return Err(EngineError::DeckLockedRound);
                }
                match state {
                    TournamentState::Playing if !*multideck => {
                        return Err(EngineError::DeckLockedPlaying);
                    }
                    TournamentState::Finished => {
                        return Err(EngineError::DeckLockedFinished);
                    }
                    _ => {} // Planned, Registration, Waiting: always allowed
                }
            }
            let op = json::object! {
                arg::OP => "delete",
                arg::PLAYER_UID => player_uid.as_str(),
                arg::DECK_INDEX => match deck_index { Some(i) => JsonValue::from(*i), None => JsonValue::Null },
                arg::MULTIDECK => *multideck,
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
                raffle_draw::LABEL => label.as_str(),
                raffle_draw::POOL => pool.as_str(),
                raffle_draw::WINNERS => JsonValue::Array(winners),
            };
            if let Some(promo_uid) = prize_promo_uid {
                draw[raffle_draw::PRIZE_PROMO_UID] = promo_uid.as_str().into();
            }
            if tournament[tournament::RAFFLES].is_null() {
                tournament[tournament::RAFFLES] = JsonValue::new_array();
            }
            tournament[tournament::RAFFLES].push(draw)?;
            Ok(())
        }

        TournamentEvent::RaffleUndo => {
            require_organizer(actor)?;
            if tournament[tournament::RAFFLES].is_null()
                || tournament[tournament::RAFFLES].is_empty()
            {
                return Err(EngineError::RaffleNoDraws);
            }
            let last = tournament[tournament::RAFFLES].len() - 1;
            tournament[tournament::RAFFLES].array_remove(last);
            Ok(())
        }

        TournamentEvent::RaffleClear => {
            require_organizer(actor)?;
            tournament[tournament::RAFFLES] = JsonValue::new_array();
            Ok(())
        }

        TournamentEvent::ReportPromos {
            promos,
            stock_source_uid,
        } => {
            require_organizer(actor)?;
            // No state gate: usually entered at/after finish, and corrections
            // to an already-submitted report are first-class.
            tournament[tournament::PROMOS_DISTRIBUTED] = promos.clone();
            let source = stock_source_uid
                .clone()
                .unwrap_or_else(|| actor.uid.clone());
            tournament[tournament::PROMO_STOCK_SOURCE_UID] = source.into();
            Ok(())
        }

        TournamentEvent::UpdateConfig { config } => {
            require_organizer(actor)?;

            validate_config_fields(config)?;

            // rank/format/start freeze once VEKN-published: calendar create and results
            // push are both write-once, so a later edit would silently diverge from vekn.net.
            let vekn_id = tournament[tournament::EXTERNAL_IDS][arg::VEKN]
                .as_str()
                .unwrap_or("");
            if !vekn_id.is_empty() {
                for field in [
                    tournament_config::RANK,
                    tournament_config::FORMAT,
                    tournament_config::START,
                ] {
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
            if config.has_key(tournament_config::RANK)
                || config.has_key(tournament_config::FORMAT)
                || config.has_key(tournament_config::PROXIES)
                || config.has_key(tournament_config::MULTIDECK)
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
            if config.has_key(tournament_config::START) || config.has_key(tournament_config::FINISH)
            {
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

            if let Some(mr) = config[tournament_config::MAX_ROUNDS].as_usize() {
                if mr != 0 {
                    // Per-player cap: can't drop below what any single player has already played.
                    let completed = tournament[tournament::PLAYERS]
                        .members()
                        .filter_map(|p| p[player::USER_UID].as_str())
                        .map(|uid| count_player_rounds_played(tournament, uid))
                        .max()
                        .unwrap_or(0);
                    if mr < completed {
                        return Err(EngineError::MaxRoundsBelowCompleted { max: mr, completed });
                    }
                }
            }
            // Validate league_uid: only league organizers (or IC) can link
            if config.has_key(tournament_config::LEAGUE_UID)
                && !config[tournament_config::LEAGUE_UID].is_null()
            {
                let league_uid = config[tournament_config::LEAGUE_UID].as_str().unwrap_or("");
                if !league_uid.is_empty()
                    && !actor.roles.contains(&"IC".to_string())
                    && !actor
                        .can_organize_league_uids
                        .contains(&league_uid.to_string())
                {
                    return Err(EngineError::LeagueLinkForbidden);
                }
            }

            let decklists_mode_changing = config.has_key(tournament_config::DECKLISTS_MODE)
                && state == TournamentState::Finished;

            // Apply config fields (key present = apply, even if null)
            for field in CONFIG_FIELDS {
                if config.has_key(field) {
                    tournament[field] = config[field].clone();
                }
            }

            // Storyline takes no deck at all, so a surviving flag or check-in stamp
            // would strand check-in with nothing able to clear it — UpsertDeck refuses.
            if tournament[tournament::FORMAT].as_str() == Some("Storyline") {
                tournament[tournament::DECKLIST_REQUIRED] = false.into();
                for p in tournament[tournament::PLAYERS].members_mut() {
                    p.remove(player::MISSING_DECKLIST);
                }
            }

            if decklists_mode_changing {
                for d in decks.members() {
                    let user_uid = d[deck_object::USER_UID].as_str().unwrap_or("");
                    let deck_uid = d[deck_object::UID].as_str().unwrap_or("");
                    if user_uid.is_empty() || deck_uid.is_empty() {
                        continue;
                    }
                    let is_public = compute_deck_public(tournament, user_uid);
                    let op = json::object! {
                        arg::OP => "set_public",
                        arg::DECK_UID => deck_uid,
                        arg::PUBLIC => is_public,
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
            if !tournament[tournament::EXTERNAL_IDS][arg::VEKN]
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
            let existing = tournament[tournament::PLAYERS].clone();
            let nameless: Vec<JsonValue> = existing
                .members()
                .filter(|p| p[player::USER_UID].as_str().unwrap_or("").is_empty())
                .cloned()
                .collect();
            tournament[tournament::PLAYERS] = JsonValue::Array(
                ordered
                    .iter()
                    .map(|uid| {
                        let prior = existing
                            .members()
                            .find(|p| p[player::USER_UID].as_str() == Some(uid.as_str()));
                        let mut player = json::object! {
                            player::USER_UID => uid.as_str(),
                            player::STATE => "Finished",
                            player::PAYMENT_STATUS => prior
                                .and_then(|p| p[player::PAYMENT_STATUS].as_str())
                                .unwrap_or("Paid"),
                            player::TOSS => 0,
                            player::RESULT => json::object!{ score::GW => 0, score::VP => 0.0, score::TP => 0 },
                            player::FINALIST => *uid == winner,
                            player::NON_COMPETING => false,
                            player::WAITLISTED => false,
                        };
                        if let Some(dn) = prior.and_then(|p| p[player::DISPLAY_NAME].as_str()) {
                            player[player::DISPLAY_NAME] = dn.into();
                        }
                        player
                    })
                    .chain(nameless)
                    .collect(),
            );
            tournament[tournament::STANDINGS] = JsonValue::Array(
                ordered
                    .iter()
                    .map(|uid| {
                        json::object! {
                            standing::USER_UID => uid.as_str(),
                            standing::GW => 0.0,
                            standing::VP => 0.0,
                            standing::TP => 0,
                            standing::TOSS => 0,
                            standing::FINALIST => *uid == winner,
                            standing::DISQUALIFIED => false,
                            standing::NON_COMPETING => false,
                        }
                    })
                    .collect(),
            );
            tournament[tournament::WINNER] = winner.as_str().into();
            tournament[tournament::REPORTED_PLAYER_COUNT] = (*reported_player_count).into();
            Ok(())
        }
    }
}
