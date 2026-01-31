//! Tournament business logic engine.
//!
//! Processes tournament events and returns updated tournament state.
//! Same code runs in WASM (frontend offline) and PyO3 (backend).

use json::JsonValue;

use crate::seating;

// ============================================================================
// TYPES (mirror Python/TypeScript models)
// ============================================================================

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TournamentState {
    Planned,
    Registration,
    Waiting,
    Playing,
    Finished,
}

impl TournamentState {
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "Planned" => Some(Self::Planned),
            "Registration" => Some(Self::Registration),
            "Waiting" => Some(Self::Waiting),
            "Playing" => Some(Self::Playing),
            "Finished" => Some(Self::Finished),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Planned => "Planned",
            Self::Registration => "Registration",
            Self::Waiting => "Waiting",
            Self::Playing => "Playing",
            Self::Finished => "Finished",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlayerState {
    Registered,
    CheckedIn,
    Playing,
    Finished,
}

impl PlayerState {
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "Registered" => Some(Self::Registered),
            "Checked-in" => Some(Self::CheckedIn),
            "Playing" => Some(Self::Playing),
            "Finished" => Some(Self::Finished),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Registered => "Registered",
            Self::CheckedIn => "Checked-in",
            Self::Playing => "Playing",
            Self::Finished => "Finished",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TableState {
    InProgress,
    Finished,
    Invalid,
}

impl TableState {
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "In Progress" => Some(Self::InProgress),
            "Finished" => Some(Self::Finished),
            "Invalid" => Some(Self::Invalid),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::InProgress => "In Progress",
            Self::Finished => "Finished",
            Self::Invalid => "Invalid",
        }
    }
}

// ============================================================================
// TOURNAMENT EVENTS
// ============================================================================

#[derive(Debug, Clone)]
pub enum TournamentEvent {
    // State transitions
    OpenRegistration,
    CloseRegistration,
    CancelRegistration,
    ReopenRegistration,
    ReopenTournament,
    FinishTournament,

    // Player management
    Register { user_uid: String },
    Unregister { user_uid: String },
    AddPlayer { user_uid: String },
    RemovePlayer { user_uid: String },
    DropOut { player_uid: String },
    CheckIn { player_uid: String },
    CheckInAll,
    ResetCheckIn,

    // Round management
    StartRound,
    FinishRound,
    CancelRound,
    SwapSeats {
        round: usize,
        table1: usize,
        seat1: usize,
        table2: usize,
        seat2: usize,
    },
    SeatPlayer {
        player_uid: String,
        table: usize,
        seat: usize,
    },
    UnseatPlayer {
        player_uid: String,
    },
    AddTable,
    RemoveTable { table: usize },
    SetScore {
        round: usize,
        table: usize,
        scores: Vec<SeatScore>,
    },
    Override {
        round: usize,
        table: usize,
        comment: String,
    },
    Unoverride {
        round: usize,
        table: usize,
    },

    // Finals
    SetToss {
        player_uid: String,
        toss: u32,
    },
    RandomToss,
    StartFinals,
    FinishFinals,
}

#[derive(Debug, Clone)]
pub struct SeatScore {
    pub player_uid: String,
    pub vp: f64,
}

/// VP validation error types
#[derive(Debug, Clone, PartialEq)]
pub enum VpError {
    InvalidTableSize,
    InsufficientTotal,
    ExcessiveTotal,
    MissingVp(usize),    // seat index (0-based)
    MissingHalfVp(Vec<usize>), // seat indices
}

/// Check VP validity on a table, replicating archon's oust-order validation.
/// VPs are in seating (predator-prey) order around the table.
/// Returns None if valid, Some(error) if invalid.
fn check_table_vps(vps: &[f64]) -> Option<VpError> {
    let n = vps.len();
    if n < 4 || n > 5 {
        return Some(VpError::InvalidTableSize);
    }
    // Check total: ceil each VP, sum must equal table size
    let total: i64 = vps.iter().map(|&v| v.ceil() as i64).sum();
    if total < n as i64 {
        return Some(VpError::InsufficientTotal);
    }
    if total > n as i64 {
        return Some(VpError::ExcessiveTotal);
    }
    // Oust-order simulation: work with (original_index, accounted_vp) pairs
    let mut seats: Vec<(usize, f64)> = vps.iter().enumerate().map(|(i, &v)| (i, v)).collect();
    // Repeatedly find ousted players (vp <= 0) and transfer to predator
    loop {
        if seats.is_empty() {
            break;
        }
        let mut found_oust = false;
        for j in 0..seats.len() {
            let (idx, vp_count) = seats[j];
            if vp_count <= 0.0 {
                // A negative count with fractional part means impossible sequence
                if vp_count.fract().abs() > 1e-9 && (vp_count.fract().abs() - 1.0).abs() > 1e-9 {
                    return Some(VpError::MissingVp(idx));
                }
                // Transfer: predator (previous seat) gets vp_count - 1
                let pred = if j == 0 { seats.len() - 1 } else { j - 1 };
                seats[pred].1 += vp_count - 1.0;
                seats.remove(j);
                found_oust = true;
                break;
            }
        }
        if !found_oust {
            // All remaining scores are positive
            // If everyone is at 0.5, it's a timeout (valid if more than 1)
            if seats.iter().all(|(_, vp)| (*vp - 0.5).abs() < 1e-9) {
                if seats.len() == 1 {
                    return Some(VpError::MissingHalfVp(vec![seats[0].0]));
                }
                break; // valid timeout
            }
            // Remove 0.5s (withdrawals)
            let remaining: Vec<(usize, f64)> = seats
                .iter()
                .filter(|(_, vp)| (*vp - 0.5).abs() > 1e-9)
                .cloned()
                .collect();
            // At most 1 can remain (the last survivor with 1.0 VP)
            if remaining.len() > 1 {
                return Some(VpError::MissingHalfVp(
                    remaining.iter().map(|(i, _)| *i).collect(),
                ));
            }
            break;
        }
    }
    None
}

/// Compute GW for each player: 1 if vp >= 2.0 AND strictly highest at table, else 0
fn compute_gw(vps: &[f64]) -> Vec<f64> {
    if vps.is_empty() {
        return vec![];
    }
    let max_vp = vps.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let max_count = vps.iter().filter(|&&v| v == max_vp).count();
    vps.iter()
        .map(|&v| {
            if v >= 2.0 && v == max_vp && max_count == 1 {
                1.0
            } else {
                0.0
            }
        })
        .collect()
}

/// Compute TP based on VP rank within table. Ties average their positions.
fn compute_tp(table_size: usize, vps: &[f64]) -> Vec<f64> {
    let base: &[f64] = match table_size {
        5 => &[60.0, 48.0, 36.0, 24.0, 12.0],
        4 => &[60.0, 48.0, 24.0, 12.0],
        3 => &[60.0, 36.0, 12.0],
        _ => return vec![0.0; vps.len()],
    };

    // Create indices sorted by VP descending
    let mut indices: Vec<usize> = (0..vps.len()).collect();
    indices.sort_by(|&a, &b| vps[b].partial_cmp(&vps[a]).unwrap_or(std::cmp::Ordering::Equal));

    let mut result = vec![0.0; vps.len()];
    let mut i = 0;
    while i < indices.len() {
        // Find group of tied players
        let mut j = i + 1;
        while j < indices.len() && vps[indices[j]] == vps[indices[i]] {
            j += 1;
        }
        // Average TP for positions i..j
        let tp_sum: f64 = (i..j).map(|pos| base[pos]).sum();
        let tp_avg = tp_sum / (j - i) as f64;
        for k in i..j {
            result[indices[k]] = tp_avg;
        }
        i = j;
    }
    result
}

impl TournamentEvent {
    pub fn from_json(value: &JsonValue) -> Result<Self, String> {
        let event_type = value["type"]
            .as_str()
            .ok_or("event type required")?;

        match event_type {
            "OpenRegistration" => Ok(Self::OpenRegistration),
            "CloseRegistration" => Ok(Self::CloseRegistration),
            "CancelRegistration" => Ok(Self::CancelRegistration),
            "ReopenRegistration" => Ok(Self::ReopenRegistration),
            "ReopenTournament" => Ok(Self::ReopenTournament),
            "FinishTournament" => Ok(Self::FinishTournament),
            "Register" => Ok(Self::Register {
                user_uid: value["user_uid"]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
            }),
            "Unregister" => Ok(Self::Unregister {
                user_uid: value["user_uid"]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
            }),
            "AddPlayer" => Ok(Self::AddPlayer {
                user_uid: value["user_uid"]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
            }),
            "RemovePlayer" => Ok(Self::RemovePlayer {
                user_uid: value["user_uid"]
                    .as_str()
                    .ok_or("user_uid required")?
                    .to_string(),
            }),
            "DropOut" => Ok(Self::DropOut {
                player_uid: value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
            }),
            "CheckIn" => Ok(Self::CheckIn {
                player_uid: value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
            }),
            "CheckInAll" => Ok(Self::CheckInAll),
            "ResetCheckIn" => Ok(Self::ResetCheckIn),
            "StartRound" => Ok(Self::StartRound),
            "FinishRound" => Ok(Self::FinishRound),
            "CancelRound" => Ok(Self::CancelRound),
            "SwapSeats" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let table1 = value["table1"].as_usize().ok_or("table1 required")?;
                let seat1 = value["seat1"].as_usize().ok_or("seat1 required")?;
                let table2 = value["table2"].as_usize().ok_or("table2 required")?;
                let seat2 = value["seat2"].as_usize().ok_or("seat2 required")?;
                Ok(Self::SwapSeats { round, table1, seat1, table2, seat2 })
            }
            "SeatPlayer" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let table = value["table"].as_usize().ok_or("table required")?;
                let seat = value["seat"].as_usize().ok_or("seat required")?;
                Ok(Self::SeatPlayer { player_uid, table, seat })
            }
            "UnseatPlayer" => Ok(Self::UnseatPlayer {
                player_uid: value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
            }),
            "AddTable" => Ok(Self::AddTable),
            "RemoveTable" => {
                let table = value["table"].as_usize().ok_or("table required")?;
                Ok(Self::RemoveTable { table })
            }
            "SetScore" => {
                let round = value["round"]
                    .as_usize()
                    .ok_or("round required")?;
                let table = value["table"]
                    .as_usize()
                    .ok_or("table required")?;
                let scores: Vec<SeatScore> = value["scores"]
                    .members()
                    .map(|s| {
                        Ok(SeatScore {
                            player_uid: s["player_uid"]
                                .as_str()
                                .ok_or("player_uid required")?
                                .to_string(),
                            vp: s["vp"].as_f64().unwrap_or(0.0),
                        })
                    })
                    .collect::<Result<Vec<_>, String>>()?;
                Ok(Self::SetScore { round, table, scores })
            }
            "Override" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let table = value["table"].as_usize().ok_or("table required")?;
                let comment = value["comment"]
                    .as_str()
                    .ok_or("comment required")?
                    .to_string();
                Ok(Self::Override { round, table, comment })
            }
            "Unoverride" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let table = value["table"].as_usize().ok_or("table required")?;
                Ok(Self::Unoverride { round, table })
            }
            "SetToss" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let toss = value["toss"].as_u32().ok_or("toss required")?;
                Ok(Self::SetToss { player_uid, toss })
            }
            "RandomToss" => Ok(Self::RandomToss),
            "StartFinals" => Ok(Self::StartFinals),
            "FinishFinals" => Ok(Self::FinishFinals),
            _ => Err(format!("Unknown event type: {}", event_type)),
        }
    }
}

// ============================================================================
// ACTOR CONTEXT (who is performing the action)
// ============================================================================

#[derive(Debug, Clone)]
pub struct ActorContext {
    pub uid: String,
    pub roles: Vec<String>,
    pub is_organizer: bool,
}

impl ActorContext {
    pub fn from_json(value: &JsonValue) -> Result<Self, String> {
        let uid = value["uid"]
            .as_str()
            .ok_or("actor uid required")?
            .to_string();
        let roles: Vec<String> = value["roles"]
            .members()
            .filter_map(|r| r.as_str().map(|s| s.to_string()))
            .collect();
        let is_organizer = value["is_organizer"].as_bool().unwrap_or(false);
        Ok(Self { uid, roles, is_organizer })
    }

    pub fn can_manage_tournaments(&self) -> bool {
        self.roles.iter().any(|r| r == "IC" || r == "NC" || r == "Prince")
    }
}

// ============================================================================
// TOURNAMENT ENGINE
// ============================================================================

/// Process a tournament event and return the updated tournament JSON.
///
/// # Arguments
/// * `tournament_json` - Current tournament state as JSON
/// * `event_json` - Event to process
/// * `actor_json` - Actor performing the action
///
/// # Returns
/// * Updated tournament JSON on success
/// * Error message on failure
pub fn process_tournament_event(
    tournament_json: &str,
    event_json: &str,
    actor_json: &str,
) -> Result<String, String> {
    let mut tournament = json::parse(tournament_json).map_err(|e| e.to_string())?;
    let event_value = json::parse(event_json).map_err(|e| e.to_string())?;
    let actor_value = json::parse(actor_json).map_err(|e| e.to_string())?;

    let event = TournamentEvent::from_json(&event_value)?;
    let actor = ActorContext::from_json(&actor_value)?;

    // Process the event
    apply_event(&mut tournament, &event, &actor)?;

    Ok(tournament.dump())
}

/// Player standing: (user_uid, gw, vp, tp, toss, finalist)
struct Standing {
    user_uid: String,
    gw: f64,
    vp: f64,
    tp: f64,
    toss: u32,
    finalist: bool,
}

/// Compute standings from all rounds. Sorted by GW desc, VP desc, TP desc, toss desc.
fn compute_standings(tournament: &JsonValue) -> Vec<Standing> {
    let mut map: std::collections::HashMap<String, (f64, f64, f64)> = std::collections::HashMap::new();

    // Sum results across all rounds
    for round in tournament["rounds"].members() {
        for table in round.members() {
            for seat in table["seating"].members() {
                let uid = seat["player_uid"].as_str().unwrap_or("").to_string();
                if uid.is_empty() { continue; }
                let entry = map.entry(uid).or_insert((0.0, 0.0, 0.0));
                entry.0 += seat["result"]["gw"].as_f64().unwrap_or(0.0);
                entry.1 += seat["result"]["vp"].as_f64().unwrap_or(0.0);
                entry.2 += seat["result"]["tp"].as_f64().unwrap_or(0.0);
            }
        }
    }

    // Build standings with toss and finalist from player records
    let mut standings: Vec<Standing> = map.into_iter().map(|(uid, (gw, vp, tp))| {
        let player = tournament["players"].members()
            .find(|p| p["user_uid"].as_str() == Some(&uid));
        let toss = player.and_then(|p| p["toss"].as_u32()).unwrap_or(0);
        let finalist = player.and_then(|p| p["finalist"].as_bool()).unwrap_or(false);
        Standing { user_uid: uid, gw, vp, tp, toss, finalist }
    }).collect();

    standings.sort_by(|a, b| {
        b.gw.partial_cmp(&a.gw).unwrap()
            .then(b.vp.partial_cmp(&a.vp).unwrap())
            .then(b.tp.partial_cmp(&a.tp).unwrap())
            .then(b.toss.cmp(&a.toss))
    });

    standings
}

/// Compute standings and store them on the tournament JSON object.
/// Guard: does NOT overwrite standings if rounds are empty (preserves VEKN-synced data).
fn update_standings(tournament: &mut JsonValue) {
    if tournament["rounds"].is_empty() {
        return;
    }
    let standings = compute_standings(tournament);
    let arr: Vec<JsonValue> = standings.into_iter().map(|s| {
        json::object! {
            "user_uid" => s.user_uid,
            "gw" => s.gw,
            "vp" => s.vp,
            "tp" => s.tp as f64,
            "toss" => s.toss,
            "finalist" => s.finalist,
        }
    }).collect();
    tournament["standings"] = JsonValue::Array(arr);
}

/// Check if top 5 has unbroken ties (players at the cutoff boundary with same scores and no toss differentiation)
fn top5_has_ties(standings: &[Standing]) -> bool {
    if standings.len() < 5 { return false; }
    // Check all pairs in top 5 for ties not broken by toss
    for i in 0..5 {
        for j in (i+1)..5 {
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

fn apply_event(
    tournament: &mut JsonValue,
    event: &TournamentEvent,
    actor: &ActorContext,
) -> Result<(), String> {
    let state = TournamentState::from_str(
        tournament["state"].as_str().unwrap_or("Planned")
    ).ok_or("Invalid tournament state")?;

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
            // Reset Checked-in players back to Registered
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
            // Reset Finished players back to Checked-in
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Finished") {
                    players[i]["state"] = "Checked-in".into();
                }
            }
            update_standings(tournament);
            Ok(())
        }

        TournamentEvent::Register { user_uid } => {
            require_state(state, TournamentState::Registration)?;

            // Check not already registered
            if player_exists(&tournament["players"], user_uid) {
                return Err("Already registered".to_string());
            }

            // Add player
            let player = json::object! {
                user_uid: user_uid.as_str(),
                state: "Registered",
                payment_status: "Pending",
                toss: 0,
            };
            tournament["players"].push(player).map_err(|e| e.to_string())?;
            Ok(())
        }

        TournamentEvent::Unregister { user_uid } => {
            require_state(state, TournamentState::Registration)?;

            // Self-only: player can only unregister themselves
            if actor.uid != *user_uid {
                return Err("You can only unregister yourself".to_string());
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, user_uid)
                .ok_or("Player not found")?;
            players.array_remove(idx);
            Ok(())
        }

        TournamentEvent::AddPlayer { user_uid } => {
            require_organizer(actor)?;
            if state != TournamentState::Planned && state != TournamentState::Registration && state != TournamentState::Waiting && state != TournamentState::Playing && state != TournamentState::Finished {
                return Err("Cannot add players in this state".to_string());
            }

            if player_exists(&tournament["players"], user_uid) {
                return Err("Player already registered".to_string());
            }

            let player = json::object! {
                user_uid: user_uid.as_str(),
                state: "Registered",
                payment_status: "Pending",
                toss: 0,
            };
            tournament["players"].push(player).map_err(|e| e.to_string())?;
            Ok(())
        }

        TournamentEvent::RemovePlayer { user_uid } => {
            require_organizer(actor)?;
            if state != TournamentState::Planned && state != TournamentState::Registration && state != TournamentState::Waiting && state != TournamentState::Finished {
                return Err("Cannot remove players in this state".to_string());
            }
            if tournament["rounds"].len() > 0 {
                return Err("Use DropOut for players who have played".to_string());
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, user_uid)
                .ok_or("Player not found")?;
            players.array_remove(idx);
            Ok(())
        }

        TournamentEvent::DropOut { player_uid } => {
            if state != TournamentState::Waiting && state != TournamentState::Playing {
                return Err("Cannot drop out in this state".to_string());
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, player_uid)
                .ok_or("Player not found")?;
            let player_state = PlayerState::from_str(
                players[idx]["state"].as_str().unwrap_or("")
            ).ok_or("Invalid player state")?;

            if player_state == PlayerState::Finished {
                return Err("Player already finished".to_string());
            }

            // Permission: self or organizer
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err("Only organizers or the player themselves can drop out".to_string());
            }

            players[idx]["state"] = "Finished".into();
            Ok(())
        }

        TournamentEvent::CheckIn { player_uid } => {
            require_state_or_finished(state, TournamentState::Waiting)?;

            // Permission: organizer or self (player checking themselves in)
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err("Only organizers or the player themselves can check in".to_string());
            }

            // TODO: When sanctions are implemented, disqualified players should be
            // blocked from checking back in (even by organizers).

            let players = &mut tournament["players"];
            let idx = find_player_index(players, player_uid)
                .ok_or("Player not found")?;
            players[idx]["state"] = "Checked-in".into();
            Ok(())
        }

        TournamentEvent::CheckInAll => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Registered")
                    || (state == TournamentState::Finished && players[i]["state"].as_str() == Some("Finished"))
                {
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
                    players[i]["state"] = if state == TournamentState::Finished { "Finished" } else { "Registered" }.into();
                }
            }
            Ok(())
        }

        TournamentEvent::StartRound => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            // Cannot start prelim round after finals
            if !tournament["finals"].is_null() {
                return Err("Cannot start a preliminary round after finals".to_string());
            }

            // Check max rounds
            let max_rounds = tournament["max_rounds"].as_usize().unwrap_or(0);
            let current_rounds = tournament["rounds"].len();
            if max_rounds > 0 && current_rounds >= max_rounds {
                return Err("Maximum rounds reached".to_string());
            }

            // Get checked-in players
            let checked_in: Vec<String> = tournament["players"]
                .members()
                .filter(|p| p["state"].as_str() == Some("Checked-in"))
                .filter_map(|p| p["user_uid"].as_str().map(|s| s.to_string()))
                .collect();

            let n = checked_in.len();
            if n < 4 {
                return Err("Need at least 4 checked-in players".to_string());
            }
            if n == 6 || n == 7 || n == 11 {
                return Err(format!(
                    "Cannot seat {} players (impossible seating configuration)",
                    n
                ));
            }

            // Get previous rounds for seating optimization
            let previous_rounds: Vec<Vec<Vec<String>>> = tournament["rounds"]
                .members()
                .map(|round| {
                    round
                        .members()
                        .map(|table| {
                            table["seating"]
                                .members()
                                .filter_map(|seat| {
                                    seat["player_uid"].as_str().map(|s| s.to_string())
                                })
                                .collect()
                        })
                        .collect()
                })
                .collect();

            // Compute new seating using the seating engine
            let (new_round, _score) = seating::compute_next_round(
                &checked_in,
                &previous_rounds,
            )?;

            // Build tables JSON
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

            tournament["rounds"].push(JsonValue::Array(tables)).map_err(|e| e.to_string())?;
            if state != TournamentState::Finished {
                tournament["state"] = "Playing".into();
            }

            // Mark checked-in players as playing (in Finished state, they were transitioned from Finished→Checked-in earlier)
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Checked-in") {
                    players[i]["state"] = "Playing".into();
                }
            }

            Ok(())
        }

        TournamentEvent::FinishRound => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &tournament["rounds"];
            if rounds.is_empty() {
                return Err("No rounds to finish".to_string());
            }

            let last_round = &rounds[rounds.len() - 1];

            // Check all tables are finished
            let unfinished: Vec<usize> = last_round
                .members()
                .enumerate()
                .filter(|(_, t)| t["state"].as_str() != Some("Finished"))
                .map(|(i, _)| i)
                .collect();

            if !unfinished.is_empty() {
                return Err(format!("Tables {:?} not finished yet", unfinished));
            }

            // Move players back
            let target_state = if state == TournamentState::Finished { "Finished" } else { "Checked-in" };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Playing") {
                    players[i]["state"] = target_state.into();
                }
            }

            if state != TournamentState::Finished {
                tournament["state"] = "Waiting".into();
            }
            update_standings(tournament);
            Ok(())
        }

        TournamentEvent::CancelRound => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err("No rounds to cancel".to_string());
            }

            // Remove last round
            let len = rounds.len();
            rounds.array_remove(len - 1);

            // Move playing players back
            let target_state = if state == TournamentState::Finished { "Finished" } else { "Checked-in" };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Playing") {
                    players[i]["state"] = target_state.into();
                }
            }

            if state != TournamentState::Finished {
                tournament["state"] = "Waiting".into();
            }
            update_standings(tournament);
            Ok(())
        }

        TournamentEvent::SwapSeats { round, table1, seat1, table2, seat2 } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if *round >= rounds.len() {
                return Err("Invalid round number".to_string());
            }
            let round_tables = &mut rounds[*round];
            if *table1 >= round_tables.len() || *table2 >= round_tables.len() {
                return Err("Invalid table number".to_string());
            }
            if *seat1 >= round_tables[*table1]["seating"].len()
                || *seat2 >= round_tables[*table2]["seating"].len()
            {
                return Err("Invalid seat number".to_string());
            }

            // Extract player_uids to swap
            let uid1 = round_tables[*table1]["seating"][*seat1]["player_uid"]
                .as_str()
                .ok_or("Invalid seat")?
                .to_string();
            let uid2 = round_tables[*table2]["seating"][*seat2]["player_uid"]
                .as_str()
                .ok_or("Invalid seat")?
                .to_string();

            // Swap
            round_tables[*table1]["seating"][*seat1]["player_uid"] = uid2.as_str().into();
            round_tables[*table2]["seating"][*seat2]["player_uid"] = uid1.as_str().into();

            Ok(())
        }

        TournamentEvent::SeatPlayer { player_uid, table, seat } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            // Verify player exists and is Registered
            let player_idx = find_player_index(&tournament["players"], player_uid)
                .ok_or("Player not found")?;
            let player_state = tournament["players"][player_idx]["state"]
                .as_str()
                .unwrap_or("");
            if player_state != "Registered" && !(state == TournamentState::Finished && player_state == "Finished") {
                return Err(format!("Player must be Registered (currently {})", player_state));
            }

            // Verify table exists in current round
            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err("No rounds in progress".to_string());
            }
            let last = rounds.len() - 1;
            if *table >= rounds[last].len() {
                return Err("Invalid table number".to_string());
            }

            // Insert seat entry at position
            let seating = &mut rounds[last][*table]["seating"];
            let seating_len = seating.len();
            let insert_pos = if *seat > seating_len { seating_len } else { *seat };

            let seat_entry = json::object! {
                player_uid: player_uid.as_str(),
                result: { gw: 0, vp: 0.0, tp: 0 },
                judge_uid: "",
            };

            // Insert by rebuilding array
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

            // Set player state to Playing
            tournament["players"][player_idx]["state"] = "Playing".into();
            Ok(())
        }

        TournamentEvent::UnseatPlayer { player_uid } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err("No rounds in progress".to_string());
            }
            let last = rounds.len() - 1;

            // Find and remove player from seating
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
                return Err("Player not found in current round seating".to_string());
            }

            // Set player state back to Registered
            if let Some(idx) = find_player_index(&tournament["players"], player_uid) {
                tournament["players"][idx]["state"] = "Registered".into();
            }
            Ok(())
        }

        TournamentEvent::AddTable => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err("No rounds in progress".to_string());
            }
            let last = rounds.len() - 1;

            let empty_table = json::object! {
                seating: [],
                state: "In Progress",
                override: json::Null,
            };
            rounds[last].push(empty_table).map_err(|e| e.to_string())?;
            Ok(())
        }

        TournamentEvent::RemoveTable { table } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let rounds = &mut tournament["rounds"];
            if rounds.is_empty() {
                return Err("No rounds in progress".to_string());
            }
            let last = rounds.len() - 1;
            if *table >= rounds[last].len() {
                return Err("Invalid table number".to_string());
            }
            if rounds[last][*table]["seating"].len() > 0 {
                return Err("Cannot remove a table with players seated".to_string());
            }
            rounds[last].array_remove(*table);
            Ok(())
        }

        TournamentEvent::SetScore { round, table, scores } => {
            require_state_or_finished(state, TournamentState::Playing)?;

            // Require organizer when tournament is Finished
            if state == TournamentState::Finished {
                require_organizer(actor)?;
            }

            // If round == rounds.len() and finals exists, target finals table
            let is_finals = *round == tournament["rounds"].len() && !tournament["finals"].is_null() && *table == 0;

            let t = if is_finals {
                &mut tournament["finals"]
            } else {
                let rounds = &tournament["rounds"];
                if *round >= rounds.len() {
                    return Err("Invalid round number".to_string());
                }
                if *table >= rounds[*round].len() {
                    return Err("Invalid table number".to_string());
                }
                &mut tournament["rounds"][*round][*table]
            };

            // Check permission: organizer or player at this table
            let is_at_table = t["seating"]
                .members()
                .any(|s| s["player_uid"].as_str() == Some(&actor.uid));

            if !actor.is_organizer && !is_at_table {
                return Err("Not authorized to score this table".to_string());
            }

            // If table has override and actor is not organizer, deny
            if !t["override"].is_null() && !actor.is_organizer {
                return Err("Table score is locked by judge".to_string());
            }

            let table_size = t["seating"].len();

            // Basic VP validation per seat
            for score in scores.iter() {
                let vp = score.vp;
                // Must be in [0, table_size] in 0.5 steps
                if vp < 0.0 || vp > table_size as f64 || (vp * 2.0).fract() != 0.0 {
                    if !actor.is_organizer {
                        return Err(format!("Invalid VP value: {}", vp));
                    }
                }
                // table_size - 0.5 is impossible (non-organizer blocked)
                if !actor.is_organizer && vp == table_size as f64 - 0.5 {
                    return Err(format!("VP value {} is impossible", vp));
                }
            }

            // Build a map from player_uid -> vp from the scores
            let vp_map: std::collections::HashMap<&str, f64> = scores
                .iter()
                .map(|s| (s.player_uid.as_str(), s.vp))
                .collect();

            // Gather VPs in seating order (predator-prey order)
            let mut vps: Vec<f64> = Vec::with_capacity(table_size);
            for i in 0..table_size {
                let player_uid = t["seating"][i]["player_uid"].as_str().unwrap_or("");
                let vp = vp_map.get(player_uid).copied().unwrap_or(
                    t["seating"][i]["result"]["vp"].as_f64().unwrap_or(0.0),
                );
                vps.push(vp);
            }

            let gws = compute_gw(&vps);
            let tps = compute_tp(table_size, &vps);

            // Apply scores
            for i in 0..table_size {
                let player_uid = t["seating"][i]["player_uid"].as_str().unwrap_or("").to_string();
                if vp_map.contains_key(player_uid.as_str()) {
                    t["seating"][i]["result"]["vp"] = vps[i].into();
                    t["seating"][i]["result"]["gw"] = gws[i].into();
                    t["seating"][i]["result"]["tp"] = tps[i].into();
                    if actor.is_organizer {
                        t["seating"][i]["judge_uid"] = actor.uid.as_str().into();
                    }
                }
            }

            // Determine table state using oust-order validation
            // Only recompute state if override is not set (override forces Finished)
            if t["override"].is_null() {
                let vp_err = check_table_vps(&vps);
                match vp_err {
                    Some(VpError::InsufficientTotal) => {
                        t["state"] = "In Progress".into();
                    }
                    Some(_) => {
                        // Invalid oust order or other error
                        if !actor.is_organizer {
                            // Non-organizer: reject impossible oust sequences
                            return Err("Invalid score: impossible VP combination for this table".to_string());
                        }
                        t["state"] = "Invalid".into();
                    }
                    None => {
                        t["state"] = "Finished".into();
                    }
                }
            }

            Ok(())
        }

        TournamentEvent::Override { round, table, comment } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let is_finals = *round == tournament["rounds"].len() && !tournament["finals"].is_null() && *table == 0;
            let t = if is_finals {
                &mut tournament["finals"]
            } else {
                let rounds = &tournament["rounds"];
                if *round >= rounds.len() {
                    return Err("Invalid round number".to_string());
                }
                if *table >= rounds[*round].len() {
                    return Err("Invalid table number".to_string());
                }
                &mut tournament["rounds"][*round][*table]
            };
            t["override"] = json::object! {
                judge_uid: actor.uid.as_str(),
                comment: comment.as_str(),
            };
            // Override forces table to Finished
            t["state"] = "Finished".into();

            Ok(())
        }

        TournamentEvent::Unoverride { round, table } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let is_finals = *round == tournament["rounds"].len() && !tournament["finals"].is_null() && *table == 0;
            let t = if is_finals {
                &mut tournament["finals"]
            } else {
                let rounds = &tournament["rounds"];
                if *round >= rounds.len() {
                    return Err("Invalid round number".to_string());
                }
                if *table >= rounds[*round].len() {
                    return Err("Invalid table number".to_string());
                }
                &mut tournament["rounds"][*round][*table]
            };
            t["override"] = json::Null;

            // Recompute table state from current VPs
            let table_size = t["seating"].len();
            let vps: Vec<f64> = (0..table_size)
                .map(|i| t["seating"][i]["result"]["vp"].as_f64().unwrap_or(0.0))
                .collect();
            let vp_err = check_table_vps(&vps);
            match vp_err {
                Some(VpError::InsufficientTotal) => {
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
            if tournament["rounds"].len() < 2 {
                return Err("Need at least 2 rounds before setting toss".to_string());
            }
            let idx = find_player_index(&tournament["players"], player_uid)
                .ok_or("Player not found")?;
            tournament["players"][idx]["toss"] = (*toss).into();
            Ok(())
        }

        TournamentEvent::RandomToss => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if tournament["rounds"].len() < 2 {
                return Err("Need at least 2 rounds before random toss".to_string());
            }

            let standings = compute_standings(tournament);

            // Find tied groups in top-5 cutoff zone that need toss
            // Group players by (gw, vp, tp) where toss == 0
            let cutoff = standings.len().min(5);
            // Include players beyond #5 that tie with #5
            let mut zone_end = cutoff;
            if cutoff > 0 && standings.len() > cutoff {
                let fifth = &standings[cutoff - 1];
                while zone_end < standings.len() {
                    let s = &standings[zone_end];
                    if s.gw == fifth.gw && s.vp == fifth.vp && s.tp == fifth.tp {
                        zone_end += 1;
                    } else {
                        break;
                    }
                }
            }

            // Find groups of tied players with toss == 0
            let mut i = 0;
            let mut toss_counter: u32 = 1;
            // Simple deterministic shuffle using tournament uid as seed
            let seed: u64 = tournament["uid"].as_str().unwrap_or("")
                .bytes().fold(0u64, |acc, b| acc.wrapping_mul(31).wrapping_add(b as u64));

            while i < zone_end {
                let mut j = i + 1;
                while j < zone_end
                    && standings[j].gw == standings[i].gw
                    && standings[j].vp == standings[i].vp
                    && standings[j].tp == standings[i].tp
                {
                    j += 1;
                }
                // i..j is a group of players with same scores
                if j - i > 1 {
                    // Collect those with toss == 0
                    let mut needs_toss: Vec<usize> = (i..j)
                        .filter(|&k| standings[k].toss == 0)
                        .collect();
                    if needs_toss.len() > 1 {
                        // Shuffle using simple Fisher-Yates with deterministic seed
                        let mut rng = seed.wrapping_add(i as u64);
                        for k in (1..needs_toss.len()).rev() {
                            rng = rng.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
                            let swap_idx = (rng >> 33) as usize % (k + 1);
                            needs_toss.swap(k, swap_idx);
                        }
                        // Assign sequential toss values
                        for &idx in &needs_toss {
                            let uid = &standings[idx].user_uid;
                            if let Some(pi) = find_player_index(&tournament["players"], uid) {
                                tournament["players"][pi]["toss"] = toss_counter.into();
                                toss_counter += 1;
                            }
                        }
                    }
                }
                i = j;
            }

            Ok(())
        }

        TournamentEvent::StartFinals => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if tournament["rounds"].len() < 2 {
                return Err("Need at least 2 rounds before finals".to_string());
            }
            if !tournament["finals"].is_null() {
                return Err("Finals already started".to_string());
            }

            let standings = compute_standings(tournament);
            if standings.len() < 5 {
                return Err("Need at least 5 players with results for finals".to_string());
            }
            if top5_has_ties(&standings) {
                return Err("Resolve all ties in top 5 before starting finals".to_string());
            }

            // Top 5 players form the finals table
            let top5: Vec<&Standing> = standings.iter().take(5).collect();
            let seed_order: Vec<JsonValue> = top5.iter()
                .map(|s| s.user_uid.as_str().into())
                .collect();
            let seating: Vec<JsonValue> = top5.iter()
                .map(|s| json::object! {
                    player_uid: s.user_uid.as_str(),
                    result: { gw: 0, vp: 0.0, tp: 0 },
                    judge_uid: "",
                })
                .collect();

            tournament["finals"] = json::object! {
                seating: JsonValue::Array(seating),
                state: "In Progress",
                override: json::Null,
                seed_order: JsonValue::Array(seed_order),
            };

            // Mark top 5 players as Playing
            for s in &top5 {
                if let Some(idx) = find_player_index(&tournament["players"], &s.user_uid) {
                    tournament["players"][idx]["state"] = "Playing".into();
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
                return Err("No finals in progress".to_string());
            }

            let finals_state = tournament["finals"]["state"].as_str().unwrap_or("");
            if finals_state != "Finished" {
                return Err("Finals table must be Finished first".to_string());
            }

            // Determine winner: highest VP in finals, tiebreak by seed order
            let seed_order: Vec<String> = tournament["finals"]["seed_order"]
                .members()
                .filter_map(|s| s.as_str().map(|v| v.to_string()))
                .collect();
            let seating = &tournament["finals"]["seating"];
            let mut best_uid = String::new();
            let mut best_vp = -1.0f64;
            let mut best_seed = usize::MAX;

            for seat in seating.members() {
                let uid = seat["player_uid"].as_str().unwrap_or("").to_string();
                let vp = seat["result"]["vp"].as_f64().unwrap_or(0.0);
                let seed_pos = seed_order.iter().position(|s| s == &uid).unwrap_or(usize::MAX);
                if vp > best_vp || (vp == best_vp && seed_pos < best_seed) {
                    best_vp = vp;
                    best_uid = uid;
                    best_seed = seed_pos;
                }
            }

            tournament["winner"] = best_uid.as_str().into();
            if state != TournamentState::Finished {
                tournament["state"] = "Finished".into();
            }

            // Mark all players as finished
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                players[i]["state"] = "Finished".into();
            }

            Ok(())
        }

        TournamentEvent::FinishTournament => {
            require_organizer(actor)?;
            if state != TournamentState::Waiting && state != TournamentState::Playing && state != TournamentState::Finished {
                return Err("Cannot finish from this state".to_string());
            }

            tournament["state"] = "Finished".into();

            // Mark all players as finished
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                players[i]["state"] = "Finished".into();
            }

            update_standings(tournament);
            Ok(())
        }
    }
}

// ============================================================================
// HELPERS
// ============================================================================

fn require_organizer(actor: &ActorContext) -> Result<(), String> {
    if !actor.is_organizer {
        return Err("Only organizers can perform this action".to_string());
    }
    Ok(())
}

fn require_state(current: TournamentState, expected: TournamentState) -> Result<(), String> {
    if current != expected {
        return Err(format!(
            "Tournament must be in {} state (currently {})",
            expected.as_str(),
            current.as_str()
        ));
    }
    Ok(())
}

fn require_state_or_finished(current: TournamentState, expected: TournamentState) -> Result<(), String> {
    if current != expected && current != TournamentState::Finished {
        return Err(format!(
            "Tournament must be in {} state (currently {})",
            expected.as_str(),
            current.as_str()
        ));
    }
    Ok(())
}

fn player_exists(players: &JsonValue, user_uid: &str) -> bool {
    players
        .members()
        .any(|p| p["user_uid"].as_str() == Some(user_uid))
}

fn find_player_index(players: &JsonValue, user_uid: &str) -> Option<usize> {
    players
        .members()
        .position(|p| p["user_uid"].as_str() == Some(user_uid))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_tournament() -> JsonValue {
        json::object! {
            uid: "test-tournament",
            modified: "2025-01-01T00:00:00Z",
            name: "Test Tournament",
            state: "Planned",
            format: "Standard",
            rank: "",
            max_rounds: 3,
            organizers_uids: ["organizer-1"],
            players: [],
            rounds: [],
        }
    }

    fn make_organizer() -> JsonValue {
        json::object! {
            uid: "organizer-1",
            roles: ["Prince"],
            is_organizer: true,
        }
    }

    fn make_player(uid: &str) -> JsonValue {
        json::object! {
            uid: uid,
            roles: [],
            is_organizer: false,
        }
    }

    #[test]
    fn test_open_registration() {
        let tournament = make_tournament();
        let event = json::object! { type: "OpenRegistration" };
        let actor = make_organizer();

        let result = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
        );

        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["state"].as_str(), Some("Registration"));
    }

    #[test]
    fn test_register_player() {
        let mut tournament = make_tournament();
        tournament["state"] = "Registration".into();

        let event = json::object! {
            type: "Register",
            user_uid: "player-1",
        };
        let actor = make_player("player-1");

        let result = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
        );

        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"].len(), 1);
        assert_eq!(updated["players"][0]["user_uid"].as_str(), Some("player-1"));
    }

    #[test]
    fn test_check_in_all() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Registered", payment_status: "Pending", toss: 0 },
        ];

        let event = json::object! { type: "CheckInAll" };
        let actor = make_organizer();

        let result = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
        );

        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
        assert_eq!(updated["players"][1]["state"].as_str(), Some("Checked-in"));
    }

    #[test]
    fn test_start_round_insufficient_players() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];

        let event = json::object! { type: "StartRound" };
        let actor = make_organizer();

        let result = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
        );

        assert!(result.is_err());
        assert!(result.unwrap_err().contains("at least 4"));
    }

    #[test]
    fn test_non_organizer_cannot_open_registration() {
        let tournament = make_tournament();
        let event = json::object! { type: "OpenRegistration" };
        let actor = make_player("random-player");

        let result = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
        );

        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers"));
    }
}
