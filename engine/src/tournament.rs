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
    #[allow(clippy::should_implement_trait)]
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
    Disqualified,
}

impl PlayerState {
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "Registered" => Some(Self::Registered),
            "Checked-in" => Some(Self::CheckedIn),
            "Playing" => Some(Self::Playing),
            "Finished" => Some(Self::Finished),
            "Disqualified" => Some(Self::Disqualified),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Registered => "Registered",
            Self::CheckedIn => "Checked-in",
            Self::Playing => "Playing",
            Self::Finished => "Finished",
            Self::Disqualified => "Disqualified",
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
    #[allow(clippy::should_implement_trait)]
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
    Register {
        user_uid: String,
    },
    Unregister {
        user_uid: String,
    },
    AddPlayer {
        user_uid: String,
    },
    RemovePlayer {
        user_uid: String,
    },
    DropOut {
        player_uid: String,
    },
    CheckIn {
        player_uid: String,
    },
    CheckOut {
        player_uid: String,
    },
    CheckInAll,
    ResetCheckIn,

    // Payment
    SetPaymentStatus {
        player_uid: String,
        status: String,
    },
    MarkAllPaid,

    // Round management
    StartRound {
        seating: Option<Vec<Vec<String>>>,
    },
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
    RemoveTable {
        table: usize,
    },
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

    // Seating alteration (batch)
    AlterSeating {
        round: usize,
        seating: Vec<Vec<String>>, // table -> player UIDs in order
    },

    // Deck management
    UpsertDeck {
        player_uid: String,
        deck: JsonValue,
        multideck: bool,
    },
    DeleteDeck {
        player_uid: String,
        deck_index: Option<usize>,
        multideck: bool,
    },

    // Raffle
    RaffleDraw {
        label: String,
        pool: String,
        exclude_drawn: bool,
        count: usize,
        seed: u64,
    },
    RaffleUndo,
    RaffleClear,

    // Config update (partial fields)
    UpdateConfig {
        config: JsonValue,
    },
}

#[derive(Debug, Clone)]
pub struct SeatScore {
    pub player_uid: String,
    pub vp: f64,
}

/// VP validation error types
#[derive(Debug, Clone, PartialEq)]
pub(crate) enum VpError {
    InvalidTableSize,
    InsufficientTotal,
    ExcessiveTotal,
    MissingVp(usize),          // seat index (0-based)
    MissingHalfVp(Vec<usize>), // seat indices
}

/// Check VP validity on a table, replicating archon's oust-order validation.
/// VPs are in seating (predator-prey) order around the table.
/// Returns None if valid, Some(error) if invalid.
pub(crate) fn check_table_vps(vps: &[f64]) -> Option<VpError> {
    let n = vps.len();
    if !(4..=5).contains(&n) {
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

// ============================================================================
// SANCTIONS HELPERS
// ============================================================================

/// Check if a sanction is active (not lifted, not deleted).
fn is_sanction_active(s: &JsonValue) -> bool {
    s["lifted_at"].is_null() && s["deleted_at"].is_null()
}

/// Get active SA (standings_adjustment) sanctions: returns (user_uid, round_number) pairs.
fn get_sa_sanctions(sanctions: &JsonValue) -> Vec<(String, usize)> {
    let mut result = Vec::new();
    for s in sanctions.members() {
        if !is_sanction_active(s) {
            continue;
        }
        if s["level"].as_str() != Some("standings_adjustment") {
            continue;
        }
        let uid = s["user_uid"].as_str().unwrap_or("").to_string();
        let round = s["round_number"].as_usize().unwrap_or(0);
        if !uid.is_empty() {
            result.push((uid, round));
        }
    }
    result
}

/// Check if a player has an active DQ sanction (in-tournament).
fn has_dq_sanction(sanctions: &JsonValue, player_uid: &str) -> bool {
    sanctions.members().any(|s| {
        is_sanction_active(s)
            && s["level"].as_str() == Some("disqualification")
            && s["user_uid"].as_str() == Some(player_uid)
    })
}

/// Check if a player has an active suspension.
fn has_active_suspension(sanctions: &JsonValue, player_uid: &str) -> bool {
    sanctions.members().any(|s| {
        is_sanction_active(s)
            && s["level"].as_str() == Some("suspension")
            && s["user_uid"].as_str() == Some(player_uid)
    })
}

/// Compute GW for each player: 1 if adjusted_vp >= 2.0 AND strictly highest adjusted VP, else 0.
/// `adjustments` is same length as `vps` with negative values for SA penalties.
pub(crate) fn compute_gw(vps: &[f64], adjustments: &[f64]) -> Vec<f64> {
    if vps.is_empty() {
        return vec![];
    }
    let adjusted: Vec<f64> = vps
        .iter()
        .zip(adjustments.iter())
        .map(|(v, a)| v + a)
        .collect();
    let max_adj = adjusted.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let max_count = adjusted.iter().filter(|&&v| v == max_adj).count();
    adjusted
        .iter()
        .map(|&v| {
            if v >= 2.0 && v == max_adj && max_count == 1 {
                1.0
            } else {
                0.0
            }
        })
        .collect()
}

/// Compute GW for finals: always awards 1 GW to the winner (highest adjusted VP,
/// tiebroken by seed order). No 2VP threshold — finals always produce a winner.
pub(crate) fn compute_gw_finals(
    vps: &[f64],
    adjustments: &[f64],
    seating_uids: &[&str],
    seed_order: &[String],
) -> Vec<f64> {
    if vps.is_empty() {
        return vec![];
    }
    let adjusted: Vec<f64> = vps
        .iter()
        .zip(adjustments.iter())
        .map(|(v, a)| v + a)
        .collect();
    let mut best_idx = 0;
    let mut best_adj = adjusted[0];
    let mut best_seed = seed_order
        .iter()
        .position(|s| s == seating_uids[0])
        .unwrap_or(usize::MAX);
    for i in 1..adjusted.len() {
        let adj = adjusted[i];
        let seed_pos = seed_order
            .iter()
            .position(|s| s == seating_uids[i])
            .unwrap_or(usize::MAX);
        if adj > best_adj || (adj == best_adj && seed_pos < best_seed) {
            best_adj = adj;
            best_idx = i;
            best_seed = seed_pos;
        }
    }
    let mut gws = vec![0.0; vps.len()];
    gws[best_idx] = 1.0;
    gws
}

/// Compute TP based on VP rank within table. Ties average their positions.
pub(crate) fn compute_tp(table_size: usize, vps: &[f64]) -> Vec<f64> {
    let base: &[f64] = match table_size {
        5 => &[60.0, 48.0, 36.0, 24.0, 12.0],
        4 => &[60.0, 48.0, 24.0, 12.0],
        3 => &[60.0, 36.0, 12.0],
        _ => return vec![0.0; vps.len()],
    };

    // Create indices sorted by VP descending
    let mut indices: Vec<usize> = (0..vps.len()).collect();
    indices.sort_by(|&a, &b| {
        vps[b]
            .partial_cmp(&vps[a])
            .unwrap_or(std::cmp::Ordering::Equal)
    });

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
        let event_type = value["type"].as_str().ok_or("event type required")?;

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
            "CheckOut" => Ok(Self::CheckOut {
                player_uid: value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string(),
            }),
            "CheckInAll" => Ok(Self::CheckInAll),
            "ResetCheckIn" => Ok(Self::ResetCheckIn),
            "SetPaymentStatus" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let status = value["status"]
                    .as_str()
                    .ok_or("status required")?
                    .to_string();
                Ok(Self::SetPaymentStatus { player_uid, status })
            }
            "MarkAllPaid" => Ok(Self::MarkAllPaid),
            "StartRound" => {
                let seating = if value["seating"].is_null() || !value["seating"].is_array() {
                    None
                } else {
                    Some(
                        value["seating"]
                            .members()
                            .map(|t| {
                                t.members()
                                    .filter_map(|p| p.as_str().map(|s| s.to_string()))
                                    .collect()
                            })
                            .collect(),
                    )
                };
                Ok(Self::StartRound { seating })
            }
            "FinishRound" => Ok(Self::FinishRound),
            "CancelRound" => Ok(Self::CancelRound),
            "SwapSeats" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let table1 = value["table1"].as_usize().ok_or("table1 required")?;
                let seat1 = value["seat1"].as_usize().ok_or("seat1 required")?;
                let table2 = value["table2"].as_usize().ok_or("table2 required")?;
                let seat2 = value["seat2"].as_usize().ok_or("seat2 required")?;
                Ok(Self::SwapSeats {
                    round,
                    table1,
                    seat1,
                    table2,
                    seat2,
                })
            }
            "SeatPlayer" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let table = value["table"].as_usize().ok_or("table required")?;
                let seat = value["seat"].as_usize().ok_or("seat required")?;
                Ok(Self::SeatPlayer {
                    player_uid,
                    table,
                    seat,
                })
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
                let round = value["round"].as_usize().ok_or("round required")?;
                let table = value["table"].as_usize().ok_or("table required")?;
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
                Ok(Self::SetScore {
                    round,
                    table,
                    scores,
                })
            }
            "Override" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let table = value["table"].as_usize().ok_or("table required")?;
                let comment = value["comment"]
                    .as_str()
                    .ok_or("comment required")?
                    .to_string();
                Ok(Self::Override {
                    round,
                    table,
                    comment,
                })
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
            "AlterSeating" => {
                let round = value["round"].as_usize().ok_or("round required")?;
                let seating: Vec<Vec<String>> = value["seating"]
                    .members()
                    .map(|t| {
                        t.members()
                            .filter_map(|p| p.as_str().map(|s| s.to_string()))
                            .collect()
                    })
                    .collect();
                Ok(Self::AlterSeating { round, seating })
            }
            "UpsertDeck" | "UploadDeck" | "UpdateDeck" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let deck = value["deck"].clone();
                if deck.is_null() {
                    return Err("deck required".to_string());
                }
                let multideck = value["multideck"].as_bool().unwrap_or(false);
                Ok(Self::UpsertDeck {
                    player_uid,
                    deck,
                    multideck,
                })
            }
            "DeleteDeck" => {
                let player_uid = value["player_uid"]
                    .as_str()
                    .ok_or("player_uid required")?
                    .to_string();
                let deck_index = value["deck_index"].as_usize();
                let multideck = value["multideck"].as_bool().unwrap_or(false);
                Ok(Self::DeleteDeck {
                    player_uid,
                    deck_index,
                    multideck,
                })
            }
            "RaffleDraw" => {
                let label = value["label"].as_str().ok_or("label required")?.to_string();
                let pool = value["pool"].as_str().ok_or("pool required")?.to_string();
                let exclude_drawn = value["exclude_drawn"].as_bool().unwrap_or(true);
                let count = value["count"].as_usize().ok_or("count required")?;
                let seed = value["seed"].as_u64().ok_or("seed required")?;
                Ok(Self::RaffleDraw {
                    label,
                    pool,
                    exclude_drawn,
                    count,
                    seed,
                })
            }
            "RaffleUndo" => Ok(Self::RaffleUndo),
            "RaffleClear" => Ok(Self::RaffleClear),
            "UpdateConfig" => {
                let config = value["config"].clone();
                if config.is_null() || !config.is_object() {
                    return Err("config object required".to_string());
                }
                Ok(Self::UpdateConfig { config })
            }
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
        Ok(Self {
            uid,
            roles,
            is_organizer,
        })
    }

    pub fn can_manage_tournaments(&self) -> bool {
        self.roles
            .iter()
            .any(|r| r == "IC" || r == "NC" || r == "Prince")
    }
}

// ============================================================================
// TOURNAMENT ENGINE
// ============================================================================

/// Process a tournament event and return updated tournament + deck side-effects.
///
/// # Arguments
/// * `tournament_json` - Current tournament state as JSON
/// * `event_json` - Event to process
/// * `actor_json` - Actor performing the action
/// * `sanctions_json` - Array of sanctions: [{user_uid, level, round_number, lifted_at, deleted_at}]
/// * `decks_json` - Array of existing deck metadata: [{user_uid, round, uid}]
///
/// # Returns
/// * JSON: `{"tournament": {...}, "deck_ops": [...]}`
/// * Error message on failure
pub fn process_tournament_event(
    tournament_json: &str,
    event_json: &str,
    actor_json: &str,
    sanctions_json: &str,
    decks_json: &str,
) -> Result<String, String> {
    let mut tournament = json::parse(tournament_json).map_err(|e| e.to_string())?;
    let event_value = json::parse(event_json).map_err(|e| e.to_string())?;
    let actor_value = json::parse(actor_json).map_err(|e| e.to_string())?;
    let sanctions = json::parse(sanctions_json).map_err(|e| e.to_string())?;
    let decks = json::parse(decks_json).map_err(|e| e.to_string())?;

    let event = TournamentEvent::from_json(&event_value)?;
    let actor = ActorContext::from_json(&actor_value)?;

    // Process the event
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
/// Applies SA overflow: if a player has an SA sanction for a round where their raw VP < 1.0,
/// the overflow (1.0 - raw_vp) is subtracted from their total VP.
fn compute_standings(tournament: &JsonValue, sanctions: &JsonValue) -> Vec<Standing> {
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

    standings.sort_by(|a, b| {
        b.gw.partial_cmp(&a.gw)
            .unwrap()
            .then(b.vp.partial_cmp(&a.vp).unwrap())
            .then(b.tp.partial_cmp(&a.tp).unwrap())
            .then(b.toss.cmp(&a.toss))
    });

    standings
}

/// Compute standings and store them on the tournament JSON object.
/// Guard: does NOT overwrite standings if rounds are empty (preserves VEKN-synced data).
fn update_standings(tournament: &mut JsonValue, sanctions: &JsonValue) {
    if tournament["rounds"].is_empty() {
        return;
    }
    let standings = compute_standings(tournament, sanctions);
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

/// Check if top 5 has unbroken ties (players at the cutoff boundary with same scores and no toss differentiation)
fn top5_has_ties(standings: &[Standing]) -> bool {
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

/// Get the set of player UIDs who appeared in any round seating.
/// Get the set of player UIDs who appeared in any round seating (sorted for determinism).
fn get_played_uids(tournament: &JsonValue) -> Vec<String> {
    let mut played = std::collections::HashSet::new();
    for round in tournament["rounds"].members() {
        for table in round.members() {
            for seat in table["seating"].members() {
                if let Some(uid) = seat["player_uid"].as_str() {
                    if !uid.is_empty() {
                        played.insert(uid.to_string());
                    }
                }
            }
        }
    }
    let mut result: Vec<String> = played.into_iter().collect();
    result.sort();
    result
}

/// Filter raffle pool based on pool type and exclude_drawn flag.
/// NOTE: Pool filtering logic duplicated in frontend RaffleSection.svelte eligibleForPool()
fn get_raffle_pool(
    tournament: &JsonValue,
    pool: &str,
    exclude_drawn: bool,
) -> Result<Vec<String>, String> {
    let played = get_played_uids(tournament);
    if played.is_empty() {
        return Err("No players have played yet".to_string());
    }

    // Build standings map: uid -> (gw, vp)
    let mut standings_map: std::collections::HashMap<String, (f64, f64)> =
        std::collections::HashMap::new();
    for s in tournament["standings"].members() {
        if let Some(uid) = s["user_uid"].as_str() {
            let gw = s["gw"].as_f64().unwrap_or(0.0);
            let vp = s["vp"].as_f64().unwrap_or(0.0);
            standings_map.insert(uid.to_string(), (gw, vp));
        }
    }

    // Finalists set
    let finalists: std::collections::HashSet<String> = if !tournament["finals"].is_null() {
        tournament["finals"]["seating"]
            .members()
            .filter_map(|s| s["player_uid"].as_str().map(|u| u.to_string()))
            .collect()
    } else {
        std::collections::HashSet::new()
    };

    let mut eligible: Vec<String> = match pool {
        "AllPlayers" => played.clone(),
        "NonFinalists" => played
            .iter()
            .filter(|uid| !finalists.contains(*uid))
            .cloned()
            .collect(),
        "GameWinners" => played
            .iter()
            .filter(|uid| standings_map.get(*uid).is_some_and(|(gw, _)| *gw > 0.0))
            .cloned()
            .collect(),
        "NoGameWin" => played
            .iter()
            .filter(|uid| standings_map.get(*uid).is_none_or(|(gw, _)| *gw == 0.0))
            .cloned()
            .collect(),
        "NoVictoryPoint" => played
            .iter()
            .filter(|uid| standings_map.get(*uid).is_none_or(|(_, vp)| *vp == 0.0))
            .cloned()
            .collect(),
        _ => return Err(format!("Unknown pool: {}", pool)),
    };

    if exclude_drawn {
        let drawn: std::collections::HashSet<String> = tournament["raffles"]
            .members()
            .flat_map(|d| d["winners"].members())
            .filter_map(|w| w.as_str().map(|s| s.to_string()))
            .collect();
        eligible.retain(|uid| !drawn.contains(uid));
    }

    Ok(eligible)
}

/// Compute whether a deck should be public based on tournament state and decklists_mode.
fn compute_deck_public(tournament: &JsonValue, player_uid: &str) -> bool {
    let state = tournament["state"].as_str().unwrap_or("");
    if state != "Finished" {
        return false;
    }
    let mode = tournament["decklists_mode"].as_str().unwrap_or("Winner");
    match mode {
        "All" => true,
        "Finalists" => {
            // Check if player is a finalist or winner
            tournament["winner"].as_str() == Some(player_uid)
                || tournament["players"].members().any(|p| {
                    p["user_uid"].as_str() == Some(player_uid)
                        && p["finalist"].as_bool().unwrap_or(false)
                })
        }
        _ => tournament["winner"].as_str() == Some(player_uid),
    }
}

fn apply_event(
    tournament: &mut JsonValue,
    event: &TournamentEvent,
    actor: &ActorContext,
    sanctions: &JsonValue,
    decks: &JsonValue,
    deck_ops: &mut JsonValue,
) -> Result<(), String> {
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
            // Clear finals and winner so organizer can redo finals
            tournament["finals"] = json::Null;
            tournament["winner"] = json::Null;
            // Reset Finished players back to Checked-in (DQ'd stay DQ'd)
            // Also clear finalist flag so new finals can be started cleanly
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Finished") {
                    players[i]["state"] = "Checked-in".into();
                }
                players[i]["finalist"] = false.into();
                // Disqualified players stay Disqualified (no reset)
            }
            update_standings(tournament, sanctions);
            // Reset all deck public flags since tournament is no longer finished
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

        TournamentEvent::Register { user_uid } => {
            require_state(state, TournamentState::Registration)?;

            // Check not already registered
            if player_exists(&tournament["players"], user_uid) {
                return Err("Already registered".to_string());
            }

            // Block players with DQ or suspension sanctions
            if has_dq_sanction(sanctions, user_uid) {
                return Err(
                    "Player has a disqualification sanction and cannot register".to_string(),
                );
            }
            if has_active_suspension(sanctions, user_uid) {
                return Err("Player is suspended and cannot register".to_string());
            }

            // Add player
            let player = json::object! {
                user_uid: user_uid.as_str(),
                state: "Registered",
                payment_status: "Pending",
                toss: 0,
                result: { gw: 0, vp: 0.0, tp: 0 },
                finalist: false,
            };
            tournament["players"]
                .push(player)
                .map_err(|e| e.to_string())?;
            Ok(())
        }

        TournamentEvent::Unregister { user_uid } => {
            require_state(state, TournamentState::Registration)?;

            // Self-only: player can only unregister themselves
            if actor.uid != *user_uid {
                return Err("You can only unregister yourself".to_string());
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, user_uid).ok_or("Player not found")?;
            players.array_remove(idx);
            Ok(())
        }

        TournamentEvent::AddPlayer { user_uid } => {
            require_organizer(actor)?;
            if state != TournamentState::Planned
                && state != TournamentState::Registration
                && state != TournamentState::Waiting
                && state != TournamentState::Playing
                && state != TournamentState::Finished
            {
                return Err("Cannot add players in this state".to_string());
            }

            if player_exists(&tournament["players"], user_uid) {
                return Err("Player already registered".to_string());
            }

            // Block players with DQ or suspension sanctions
            if has_dq_sanction(sanctions, user_uid) {
                return Err(
                    "Player has a disqualification sanction and cannot register".to_string(),
                );
            }
            if has_active_suspension(sanctions, user_uid) {
                return Err("Player is suspended and cannot register".to_string());
            }

            let player = json::object! {
                user_uid: user_uid.as_str(),
                state: "Registered",
                payment_status: "Pending",
                toss: 0,
                result: { gw: 0, vp: 0.0, tp: 0 },
                finalist: false,
            };
            tournament["players"]
                .push(player)
                .map_err(|e| e.to_string())?;
            Ok(())
        }

        TournamentEvent::RemovePlayer { user_uid } => {
            require_organizer(actor)?;
            if state != TournamentState::Planned
                && state != TournamentState::Registration
                && state != TournamentState::Waiting
                && state != TournamentState::Finished
            {
                return Err("Cannot remove players in this state".to_string());
            }
            if !tournament["rounds"].is_empty() {
                return Err("Use DropOut for players who have played".to_string());
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, user_uid).ok_or("Player not found")?;
            players.array_remove(idx);
            Ok(())
        }

        TournamentEvent::DropOut { player_uid } => {
            if state != TournamentState::Waiting && state != TournamentState::Playing {
                return Err("Cannot drop out in this state".to_string());
            }

            let players = &mut tournament["players"];
            let idx = find_player_index(players, player_uid).ok_or("Player not found")?;
            let player_state = PlayerState::from_str(players[idx]["state"].as_str().unwrap_or(""))
                .ok_or("Invalid player state")?;

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

            let idx = match find_player_index(&tournament["players"], player_uid) {
                Some(idx) => idx,
                None => {
                    if state != TournamentState::Waiting {
                        return Err("Player not found".to_string());
                    }
                    if has_dq_sanction(sanctions, player_uid) {
                        return Err(
                            "Player has a disqualification sanction and cannot check in".to_string()
                        );
                    }
                    if has_active_suspension(sanctions, player_uid) {
                        return Err("Player is suspended and cannot check in".to_string());
                    }
                    let player = json::object! {
                        user_uid: player_uid.as_str(),
                        state: "Registered",
                        payment_status: "Pending",
                        toss: 0,
                        result: { gw: 0, vp: 0.0, tp: 0 },
                        finalist: false,
                    };
                    tournament["players"].push(player).map_err(|e| e.to_string())?;
                    tournament["players"].len() - 1
                }
            };

            // Block disqualified players from checking in
            if tournament["players"][idx]["state"].as_str() == Some("Disqualified") {
                return Err("Disqualified players cannot check in".to_string());
            }

            // Block players with DQ or suspension sanctions
            if has_dq_sanction(sanctions, player_uid) {
                return Err(
                    "Player has a disqualification sanction and cannot check in".to_string()
                );
            }
            if has_active_suspension(sanctions, player_uid) {
                return Err("Player is suspended and cannot check in".to_string());
            }

            // Check for missing decklist when required (uses decks parameter)
            let missing_decklist = tournament["decklist_required"].as_bool().unwrap_or(false) && {
                let pk = player_uid.as_str();
                !decks.members().any(|d| d["user_uid"].as_str() == Some(pk))
            };

            tournament["players"][idx]["state"] = "Checked-in".into();
            if missing_decklist {
                tournament["players"][idx]["missing_decklist"] = true.into();
            }

            Ok(())
        }

        TournamentEvent::CheckOut { player_uid } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;

            let idx =
                find_player_index(&tournament["players"], player_uid).ok_or("Player not found")?;

            if tournament["players"][idx]["state"].as_str() != Some("Checked-in") {
                return Err("Player is not checked in".to_string());
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

            let players = &mut tournament["players"];
            for i in 0..players.len() {
                let ps = players[i]["state"].as_str().unwrap_or("");
                if ps == "Disqualified" {
                    continue;
                }
                let uid = players[i]["user_uid"].as_str().unwrap_or("");
                if has_dq_sanction(sanctions, uid) || has_active_suspension(sanctions, uid) {
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
                _ => return Err(format!("Invalid payment status: {}", status)),
            }
            let idx =
                find_player_index(&tournament["players"], player_uid).ok_or("Player not found")?;
            tournament["players"][idx]["payment_status"] = status.as_str().into();
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

            // Select which players to seat (handles awkward counts like 6, 7, 11)
            let players_to_seat =
                seating::select_players_for_round(&checked_in, &previous_rounds);

            // Use submitted seating if provided, otherwise compute
            let new_round: Vec<Vec<String>> = if let Some(submitted) = submitted_seating {
                // Validate submitted seating against the selected subset
                let seat_set: std::collections::HashSet<&str> =
                    players_to_seat.iter().map(|s| s.as_str()).collect();
                let mut seen: std::collections::HashSet<&str> = std::collections::HashSet::new();
                for table in submitted.iter() {
                    if table.len() < 4 || table.len() > 5 {
                        return Err(format!("Invalid table size: {}", table.len()));
                    }
                    for uid in table {
                        if !seat_set.contains(uid.as_str()) {
                            return Err(format!("Player {} not in selected subset", uid));
                        }
                        if !seen.insert(uid.as_str()) {
                            return Err(format!("Duplicate player {}", uid));
                        }
                    }
                }
                if seen.len() != players_to_seat.len() {
                    return Err(
                        "Submitted seating does not include all selected players".to_string()
                    );
                }
                submitted.clone()
            } else {
                let (computed, _score) =
                    seating::compute_next_round(&players_to_seat, &previous_rounds)?;
                computed
            };

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

            tournament["rounds"]
                .push(JsonValue::Array(tables))
                .map_err(|e| e.to_string())?;
            if state != TournamentState::Finished {
                tournament["state"] = "Playing".into();
            }

            // Build set of seated player UIDs
            let seated_uids: std::collections::HashSet<String> = new_round
                .iter()
                .flat_map(|table| table.iter().cloned())
                .collect();

            // Mark seated players as Playing, drop registered-but-not-checked-in players
            // Checked-in players not seated (stagger sit-outs) stay Checked-in
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                match players[i]["state"].as_str() {
                    Some("Checked-in") => {
                        if let Some(uid) = players[i]["user_uid"].as_str() {
                            if seated_uids.contains(uid) {
                                players[i]["state"] = "Playing".into();
                            }
                            // else: sitting out, stay Checked-in
                        }
                    }
                    Some("Registered") => players[i]["state"] = "Finished".into(),
                    _ => {}
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
            let target_state = if state == TournamentState::Finished {
                "Finished"
            } else {
                "Checked-in"
            };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Playing") {
                    players[i]["state"] = target_state.into();
                }
            }

            if state != TournamentState::Finished {
                tournament["state"] = "Waiting".into();
            }
            update_standings(tournament, sanctions);
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
            let target_state = if state == TournamentState::Finished {
                "Finished"
            } else {
                "Checked-in"
            };
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() == Some("Playing") {
                    players[i]["state"] = target_state.into();
                }
            }

            if state != TournamentState::Finished {
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
                    return Err("Invalid seat number".to_string());
                }
                let uid1 = seating[*seat1]["player_uid"]
                    .as_str()
                    .ok_or("Invalid seat")?
                    .to_string();
                let uid2 = seating[*seat2]["player_uid"]
                    .as_str()
                    .ok_or("Invalid seat")?
                    .to_string();
                seating[*seat1]["player_uid"] = uid2.as_str().into();
                seating[*seat2]["player_uid"] = uid1.as_str().into();
            } else {
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
                let uid1 = round_tables[*table1]["seating"][*seat1]["player_uid"]
                    .as_str()
                    .ok_or("Invalid seat")?
                    .to_string();
                let uid2 = round_tables[*table2]["seating"][*seat2]["player_uid"]
                    .as_str()
                    .ok_or("Invalid seat")?
                    .to_string();
                round_tables[*table1]["seating"][*seat1]["player_uid"] = uid2.as_str().into();
                round_tables[*table2]["seating"][*seat2]["player_uid"] = uid1.as_str().into();
            }

            Ok(())
        }

        TournamentEvent::AlterSeating { round, seating } => {
            require_organizer(actor)?;
            if state != TournamentState::Playing
                && state != TournamentState::Finished
                && state != TournamentState::Waiting
            {
                return Err("Cannot alter seating in this state".to_string());
            }

            let rounds_len = tournament["rounds"].len();
            let is_finals = *round == rounds_len && !tournament["finals"].is_null();

            // Validate no duplicate players in new seating
            {
                let all_uids: Vec<&String> = seating.iter().flat_map(|t| t.iter()).collect();
                let unique: std::collections::HashSet<&String> = all_uids.iter().copied().collect();
                if all_uids.len() != unique.len() {
                    return Err("Duplicate player in seating".to_string());
                }
            }

            if is_finals {
                // Replace finals seating player UIDs
                let finals = &mut tournament["finals"]["seating"];
                if seating.len() != 1 {
                    return Err("Finals expects exactly one table".to_string());
                }
                let new_players = &seating[0];
                if new_players.len() != finals.len() {
                    return Err("Finals player count mismatch".to_string());
                }
                // Verify same set of players
                let old_set: std::collections::HashSet<String> = (0..finals.len())
                    .map(|i| finals[i]["player_uid"].as_str().unwrap_or("").to_string())
                    .collect();
                let new_set: std::collections::HashSet<&String> = new_players.iter().collect();
                if old_set.len() != new_set.len()
                    || !new_players.iter().all(|uid| old_set.contains(uid))
                {
                    return Err("Finals player set mismatch".to_string());
                }
                for (i, uid) in new_players.iter().enumerate() {
                    finals[i]["player_uid"] = uid.as_str().into();
                }
            } else {
                // Round seating
                if *round >= rounds_len {
                    return Err("Invalid round number".to_string());
                }

                // Validation phase (immutable borrows)
                let table_count = tournament["rounds"][*round].len();
                if seating.len() != table_count {
                    return Err("Table count mismatch".to_string());
                }

                // Build map: player_uid -> (old_table, old_result, judge_uid) from current state
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

                // Validate new seating has exact same player set
                let new_total: usize = seating.iter().map(|t| t.len()).sum();
                if new_total != old_results.len() {
                    return Err("Player count mismatch".to_string());
                }

                // R1 check: reject predator-prey repeats
                {
                    let mut check_rounds: Vec<Vec<Vec<String>>> = Vec::new();
                    for r in 0..rounds_len {
                        if r == *round {
                            check_rounds.push(seating.clone());
                        } else {
                            let rd = &tournament["rounds"][r];
                            let mut tables = Vec::new();
                            for t in 0..rd.len() {
                                let mut tbl = Vec::new();
                                for s in 0..rd[t]["seating"].len() {
                                    tbl.push(
                                        rd[t]["seating"][s]["player_uid"]
                                            .as_str()
                                            .unwrap_or("")
                                            .to_string(),
                                    );
                                }
                                tables.push(tbl);
                            }
                            check_rounds.push(tables);
                        }
                    }
                    let issues = seating::compute_player_issues(&check_rounds);
                    if issues.iter().any(|i| i.rule == 0) {
                        return Err("Seating violates R1 (predator-prey repeat)".to_string());
                    }
                }

                // Mutation phase (mutable borrow)
                let round_data = &mut tournament["rounds"][*round];

                // Rebuild each table's seating
                for t in 0..seating.len() {
                    let new_players = &seating[t];
                    let mut new_seating = Vec::new();
                    for uid in new_players {
                        let (old_table, old_result, old_judge) =
                            old_results.get(uid).ok_or_else(|| {
                                format!("Player {} not found in current round seating", uid)
                            })?;
                        // Preserve result and judge_uid if player stays in same table, reset otherwise
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

                    // Recompute table state: if all VPs are 0, it's "In Progress"
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
                        // If not all zero, keep existing state (scores were preserved for same-table)
                    }
                }
            }

            Ok(())
        }

        TournamentEvent::SeatPlayer {
            player_uid,
            table,
            seat,
        } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            // Verify player exists and is Registered
            let player_idx =
                find_player_index(&tournament["players"], player_uid).ok_or("Player not found")?;
            let player_state = tournament["players"][player_idx]["state"]
                .as_str()
                .unwrap_or("");
            if player_state != "Registered"
                && !(state == TournamentState::Finished && player_state == "Finished")
            {
                return Err(format!(
                    "Player must be Registered (currently {})",
                    player_state
                ));
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

            // Verify table is not already full (max 5 players)
            let seating = &mut rounds[last][*table]["seating"];
            let seating_len = seating.len();
            if seating_len >= 5 {
                return Err("Table already has 5 players".to_string());
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
            if !rounds[last][*table]["seating"].is_empty() {
                return Err("Cannot remove a table with players seated".to_string());
            }
            rounds[last].array_remove(*table);
            Ok(())
        }

        TournamentEvent::SetScore {
            round,
            table,
            scores,
        } => {
            require_state_or_finished(state, TournamentState::Playing)?;

            // Require organizer when tournament is Finished
            if state == TournamentState::Finished {
                require_organizer(actor)?;
            }

            // If round == rounds.len() and finals exists, target finals table
            let rounds_len = tournament["rounds"].len();
            let is_finals = *round == rounds_len && !tournament["finals"].is_null() && *table == 0;

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
                if (vp < 0.0 || vp > table_size as f64 || (vp * 2.0).fract() != 0.0)
                    && !actor.is_organizer
                {
                    return Err(format!("Invalid VP value: {}", vp));
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
                let vp = vp_map
                    .get(player_uid)
                    .copied()
                    .unwrap_or(t["seating"][i]["result"]["vp"].as_f64().unwrap_or(0.0));
                vps.push(vp);
            }

            // Build per-seat SA adjustments: -1.0 VP for each SA sanction on this round
            let sa_sanctions = get_sa_sanctions(sanctions);
            let current_round = if is_finals { rounds_len } else { *round };
            let mut adjustments = vec![0.0f64; table_size];
            for i in 0..table_size {
                let player_uid = t["seating"][i]["player_uid"].as_str().unwrap_or("");
                for (sa_uid, sa_round) in &sa_sanctions {
                    if sa_uid == player_uid && *sa_round == current_round {
                        adjustments[i] -= 1.0;
                    }
                }
            }

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
            let tps = compute_tp(table_size, &vps);

            // Apply scores
            for i in 0..table_size {
                let player_uid = t["seating"][i]["player_uid"]
                    .as_str()
                    .unwrap_or("")
                    .to_string();
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
                            return Err("Invalid score: impossible VP combination for this table"
                                .to_string());
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

        TournamentEvent::Override {
            round,
            table,
            comment,
        } => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Playing)?;

            let is_finals = *round == tournament["rounds"].len()
                && !tournament["finals"].is_null()
                && *table == 0;
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

            let is_finals = *round == tournament["rounds"].len()
                && !tournament["finals"].is_null()
                && *table == 0;
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
            let idx =
                find_player_index(&tournament["players"], player_uid).ok_or("Player not found")?;
            tournament["players"][idx]["toss"] = (*toss).into();
            Ok(())
        }

        TournamentEvent::RandomToss => {
            require_organizer(actor)?;
            require_state_or_finished(state, TournamentState::Waiting)?;
            if tournament["rounds"].len() < 2 {
                return Err("Need at least 2 rounds before random toss".to_string());
            }

            let standings = compute_standings(tournament, sanctions);

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
            let seed: u64 = tournament["uid"]
                .as_str()
                .unwrap_or("")
                .bytes()
                .fold(0u64, |acc, b| acc.wrapping_mul(31).wrapping_add(b as u64));

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
                    let mut needs_toss: Vec<usize> =
                        (i..j).filter(|&k| standings[k].toss == 0).collect();
                    if needs_toss.len() > 1 {
                        // Shuffle using simple Fisher-Yates with deterministic seed
                        let mut rng = seed.wrapping_add(i as u64);
                        for k in (1..needs_toss.len()).rev() {
                            rng = rng
                                .wrapping_mul(6364136223846793005)
                                .wrapping_add(1442695040888963407);
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

            let standings = compute_standings(tournament, sanctions);

            // Filter out DQ'd players from finals consideration
            let eligible: Vec<&Standing> = standings
                .iter()
                .filter(|s| {
                    let player = tournament["players"]
                        .members()
                        .find(|p| p["user_uid"].as_str() == Some(&s.user_uid));
                    let ps = player.and_then(|p| p["state"].as_str()).unwrap_or("");
                    ps != "Disqualified"
                })
                .collect();

            if eligible.len() < 5 {
                return Err("Need at least 5 eligible players with results for finals".to_string());
            }
            if top5_has_ties(&standings) {
                return Err("Resolve all ties in top 5 before starting finals".to_string());
            }

            // Top 5 eligible players form the finals table
            let top5: Vec<&Standing> = eligible.into_iter().take(5).collect();
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

            // Mark top 5 players as Playing and finalist
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
                let seed_pos = seed_order
                    .iter()
                    .position(|s| s == &uid)
                    .unwrap_or(usize::MAX);
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

            // Mark all players as finished (except DQ'd)
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() != Some("Disqualified") {
                    players[i]["state"] = "Finished".into();
                }
            }

            // Recompute standings so finalist flags are up-to-date
            update_standings(tournament, sanctions);

            Ok(())
        }

        TournamentEvent::FinishTournament => {
            require_organizer(actor)?;
            if state != TournamentState::Waiting
                && state != TournamentState::Playing
                && state != TournamentState::Finished
            {
                return Err("Cannot finish from this state".to_string());
            }

            tournament["state"] = "Finished".into();

            // Mark all players as finished (except DQ'd)
            let players = &mut tournament["players"];
            for i in 0..players.len() {
                if players[i]["state"].as_str() != Some("Disqualified") {
                    players[i]["state"] = "Finished".into();
                }
            }

            update_standings(tournament, sanctions);

            // Emit deck_ops to flip public on qualifying decks
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
            // Auth: organizer or self
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err("Only organizers or the player can upload a deck".to_string());
            }
            // Verify player is registered
            let is_registered = tournament["players"]
                .members()
                .any(|p| p["user_uid"].as_str() == Some(player_uid.as_str()));
            if !is_registered {
                return Err("Player is not registered in this tournament".to_string());
            }
            // Lifecycle: non-organizers restricted by tournament state
            if !actor.is_organizer {
                let existing_count = decks
                    .members()
                    .filter(|d| d["user_uid"].as_str() == Some(player_uid.as_str()))
                    .count();
                match state {
                    TournamentState::Playing => {
                        if *multideck {
                            // Multideck: new deck goes at index == existing_count
                            // Block if that round has already been played
                            if is_deck_locked(tournament, existing_count) {
                                return Err(
                                    "Cannot upload deck for a round that has already started"
                                        .to_string(),
                                );
                            }
                        } else if existing_count > 0 {
                            return Err(
                                "Cannot modify deck while tournament is in progress".to_string()
                            );
                        }
                    }
                    TournamentState::Finished => {
                        if existing_count > 0 {
                            return Err(
                                "Cannot modify deck after tournament is finished".to_string()
                            );
                        }
                    }
                    _ => {} // Planned, Registration, Waiting: always allowed
                }
            }
            // Compute public flag
            let is_public = compute_deck_public(tournament, player_uid);
            // Build deck data with public flag
            let mut deck_data = deck.clone();
            deck_data["public"] = is_public.into();
            // Emit deck_ops upsert (tournament unchanged for deck events)
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
            // Auth: organizer or self
            if !actor.is_organizer && actor.uid != *player_uid {
                return Err("Only organizers or the player can delete a deck".to_string());
            }
            // Lifecycle: non-organizers restricted
            if !actor.is_organizer {
                match state {
                    TournamentState::Playing => {
                        if *multideck {
                            if let Some(idx) = deck_index {
                                if is_deck_locked(tournament, *idx) {
                                    return Err(
                                        "Cannot delete a deck whose round has already started"
                                            .to_string(),
                                    );
                                }
                            } else {
                                return Err("deck_index required for multideck delete".to_string());
                            }
                        } else {
                            return Err(
                                "Cannot delete deck while tournament is in progress".to_string()
                            );
                        }
                    }
                    TournamentState::Finished => {
                        return Err("Cannot delete deck after tournament is finished".to_string());
                    }
                    _ => {} // Planned, Registration, Waiting: always allowed
                }
            }
            // Emit deck_ops delete
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
        } => {
            require_organizer(actor)?;
            if state != TournamentState::Waiting
                && state != TournamentState::Playing
                && state != TournamentState::Finished
            {
                return Err(
                    "Raffle requires tournament in Waiting, Playing, or Finished state".to_string(),
                );
            }
            if *count == 0 {
                return Err("count must be at least 1".to_string());
            }
            let mut eligible = get_raffle_pool(tournament, pool, *exclude_drawn)?;
            if eligible.is_empty() {
                return Err("No eligible players in pool".to_string());
            }
            // Fisher-Yates shuffle with caller-provided seed (same LCG as RandomToss)
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
            let draw = json::object! {
                "label" => label.as_str(),
                "pool" => pool.as_str(),
                "winners" => JsonValue::Array(winners),
            };
            if tournament["raffles"].is_null() {
                tournament["raffles"] = JsonValue::new_array();
            }
            tournament["raffles"]
                .push(draw)
                .map_err(|e| e.to_string())?;
            Ok(())
        }

        TournamentEvent::RaffleUndo => {
            require_organizer(actor)?;
            if tournament["raffles"].is_null() || tournament["raffles"].is_empty() {
                return Err("No raffle draws to undo".to_string());
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

        TournamentEvent::UpdateConfig { config } => {
            require_organizer(actor)?;

            // Validate before applying
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
                        return Err("name cannot be empty".to_string());
                    }
                }
            }
            if let Some(mr) = config["max_rounds"].as_usize() {
                if mr != 0 {
                    let completed = count_completed_rounds(tournament);
                    if mr < completed {
                        return Err(format!(
                            "max_rounds ({}) cannot be less than completed rounds ({})",
                            mr, completed
                        ));
                    }
                }
            }
            if let Some(p) = config["time_extension_policy"].as_str() {
                validate_enum(
                    p,
                    &["additions", "clock_stop", "both"],
                    "time_extension_policy",
                )?;
            }

            // Check if decklists_mode is changing on a Finished tournament
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
                "table_rooms",
                "league_uid",
                "round_time",
                "finals_time",
                "time_extension_policy",
            ];
            for field in config_fields {
                if config.has_key(field) {
                    tournament[field] = config[field].clone();
                }
            }

            // Recompute deck public flags if decklists_mode changed on Finished tournament
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
    }
}

// ============================================================================
// HELPERS
// ============================================================================

/// Returns true if a deck at the given index is locked (its round has already started).
fn is_deck_locked(tournament: &JsonValue, deck_index: usize) -> bool {
    let rounds_played = tournament["rounds"].len();
    deck_index < rounds_played
}

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

fn require_state_or_finished(
    current: TournamentState,
    expected: TournamentState,
) -> Result<(), String> {
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

fn validate_enum(value: &str, valid: &[&str], field: &str) -> Result<(), String> {
    if !valid.contains(&value) {
        return Err(format!("Invalid {}: {}", field, value));
    }
    Ok(())
}

fn count_completed_rounds(tournament: &JsonValue) -> usize {
    let total = tournament["rounds"].len();
    if total == 0 {
        return 0;
    }
    // Check if the last round is still in progress (has "In Progress" tables)
    let last_round = &tournament["rounds"][total - 1];
    let has_in_progress = last_round
        .members()
        .any(|table| table["state"].as_str() == Some("In Progress"));
    if has_in_progress {
        total - 1
    } else {
        total
    }
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

    fn no_sanctions() -> String {
        "[]".to_string()
    }

    fn no_decks() -> String {
        "[]".to_string()
    }

    /// Helper to run a tournament event with empty sanctions and no decks
    fn run_event(
        tournament: &JsonValue,
        event: &JsonValue,
        actor: &JsonValue,
    ) -> Result<String, String> {
        let raw = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            &no_sanctions(),
            &no_decks(),
        )?;
        let parsed = json::parse(&raw).unwrap();
        Ok(parsed["tournament"].dump())
    }

    /// Helper to run a tournament event with existing decks metadata
    fn run_event_with_decks(
        tournament: &JsonValue,
        event: &JsonValue,
        actor: &JsonValue,
        decks_json: &str,
    ) -> Result<(String, JsonValue), String> {
        let raw = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            &no_sanctions(),
            decks_json,
        )?;
        let parsed = json::parse(&raw).unwrap();
        Ok((parsed["tournament"].dump(), parsed["deck_ops"].clone()))
    }

    #[test]
    fn test_open_registration() {
        let tournament = make_tournament();
        let event = json::object! { type: "OpenRegistration" };
        let actor = make_organizer();

        let result = run_event(&tournament, &event, &actor);

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

        let result = run_event(&tournament, &event, &actor);

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

        let result = run_event(&tournament, &event, &actor);

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

        let result = run_event(&tournament, &event, &actor);

        assert!(result.is_err());
        assert!(result.unwrap_err().contains("at least 4"));
    }

    #[test]
    fn test_start_round_with_submitted_seating() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p0", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p4", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p5", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p6", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p7", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];

        // Use json::parse to build the event (same path as real JSON input)
        let event = json::parse(
            r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"],["p4","p5","p6","p7"]]}"#,
        )
        .unwrap();
        let actor = make_organizer();

        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok(), "StartRound failed: {:?}", result.err());
        let updated = json::parse(&result.unwrap()).unwrap();
        let round = &updated["rounds"][0];
        let t0: Vec<&str> = (0..round[0]["seating"].len())
            .map(|i| round[0]["seating"][i]["player_uid"].as_str().unwrap())
            .collect();
        let t1: Vec<&str> = (0..round[1]["seating"].len())
            .map(|i| round[1]["seating"][i]["player_uid"].as_str().unwrap())
            .collect();
        assert_eq!(t0, vec!["p0", "p1", "p2", "p3"]);
        assert_eq!(t1, vec!["p4", "p5", "p6", "p7"]);
    }

    #[test]
    fn test_start_round_drops_registered_players() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p0", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p4", state: "Registered", payment_status: "Pending", toss: 0 },
            { user_uid: "p5", state: "Registered", payment_status: "Pending", toss: 0 },
        ];

        let event = json::parse(
            r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"]]}"#,
        )
        .unwrap();
        let actor = make_organizer();

        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok(), "StartRound failed: {:?}", result.err());
        let updated = json::parse(&result.unwrap()).unwrap();

        // Checked-in players should now be Playing
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Playing"));
        assert_eq!(updated["players"][3]["state"].as_str(), Some("Playing"));
        // Registered players should be dropped to Finished
        assert_eq!(updated["players"][4]["state"].as_str(), Some("Finished"));
        assert_eq!(updated["players"][5]["state"].as_str(), Some("Finished"));
    }

    #[test]
    fn test_non_organizer_cannot_open_registration() {
        let tournament = make_tournament();
        let event = json::object! { type: "OpenRegistration" };
        let actor = make_player("random-player");

        let result = run_event(&tournament, &event, &actor);

        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers"));
    }

    // --- Deck lifecycle tests ---

    fn tournament_with_player(state: &str) -> JsonValue {
        let mut t = make_tournament();
        t["state"] = state.into();
        t["players"] = json::array![
            { user_uid: "player-1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        t
    }

    #[test]
    fn test_player_upsert_deck_before_playing() {
        let tournament = tournament_with_player("Waiting");
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "Test", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("upsert"));
        assert_eq!(deck_ops[0]["deck"]["public"].as_bool(), Some(false));
    }

    #[test]
    fn test_player_blocked_during_playing_with_existing_deck() {
        let tournament = tournament_with_player("Playing");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "New", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("in progress"));
    }

    #[test]
    fn test_organizer_can_upsert_during_playing() {
        let tournament = tournament_with_player("Playing");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "New", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_organizer();
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("upsert"));
    }

    #[test]
    fn test_player_can_upload_missing_deck_after_finish() {
        let tournament = tournament_with_player("Finished");
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "Recovery", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
        assert_eq!(deck_ops.len(), 1);
    }

    #[test]
    fn test_player_cannot_replace_deck_after_finish() {
        let tournament = tournament_with_player("Finished");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "New", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("finished"));
    }

    #[test]
    fn test_player_blocked_upsert_during_playing() {
        let tournament = tournament_with_player("Playing");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "New", author: "", comments: "", cards: {} },
            multideck: false,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("in progress"));
    }

    #[test]
    fn test_checkin_missing_decklist_warning() {
        let mut tournament = tournament_with_player("Waiting");
        tournament["decklist_required"] = true.into();
        tournament["players"][0]["state"] = "Registered".into();

        let event = json::object! { type: "CheckIn", player_uid: "player-1" };
        let actor = make_organizer();
        // No decks passed — should flag missing_decklist
        let (raw, _) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
        let updated = json::parse(&raw).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
        assert_eq!(
            updated["players"][0]["missing_decklist"].as_bool(),
            Some(true)
        );
    }

    #[test]
    fn test_checkin_with_decklist_no_warning() {
        let mut tournament = tournament_with_player("Waiting");
        tournament["decklist_required"] = true.into();
        tournament["players"][0]["state"] = "Registered".into();

        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! { type: "CheckIn", player_uid: "player-1" };
        let actor = make_organizer();
        let (raw, _) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        let updated = json::parse(&raw).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
        assert!(updated["players"][0]["missing_decklist"].is_null());
    }

    // --- Payment tracking tests ---

    #[test]
    fn test_set_payment_status() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "SetPaymentStatus", player_uid: "p1", status: "Paid" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(
            updated["players"][0]["payment_status"].as_str(),
            Some("Paid")
        );
    }

    #[test]
    fn test_set_payment_status_invalid() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "SetPaymentStatus", player_uid: "p1", status: "Invalid" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Invalid payment status"));
    }

    #[test]
    fn test_mark_all_paid() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Checked-in", payment_status: "Paid", toss: 0 },
            { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "MarkAllPaid" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(
            updated["players"][0]["payment_status"].as_str(),
            Some("Paid")
        );
        assert_eq!(
            updated["players"][1]["payment_status"].as_str(),
            Some("Paid")
        );
        assert_eq!(
            updated["players"][2]["payment_status"].as_str(),
            Some("Paid")
        );
    }

    #[test]
    fn test_non_organizer_cannot_set_payment() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "SetPaymentStatus", player_uid: "p1", status: "Paid" };
        let actor = make_player("p1");
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers"));
    }

    // ================================================================
    // Sanctions tests
    // ================================================================

    #[test]
    fn test_gw_with_sa_adjustment() {
        // Player with 2.5 VP normally gets GW, but with -1.0 SA adjustment (1.5 VP adjusted) loses it
        let vps = vec![2.5, 1.0, 0.5, 0.5, 0.5];
        let no_adj = vec![0.0; 5];
        let gw_normal = compute_gw(&vps, &no_adj);
        assert_eq!(gw_normal[0], 1.0); // normally gets GW

        let adj = vec![-1.0, 0.0, 0.0, 0.0, 0.0];
        let gw_adjusted = compute_gw(&vps, &adj);
        assert_eq!(gw_adjusted[0], 0.0); // loses GW: adjusted VP 1.5 < 2.0
    }

    #[test]
    fn test_gw_with_sa_still_above_threshold() {
        // Player with 3.0 VP and -1.0 SA → adjusted 2.0 VP, still >= 2.0 AND still highest → keeps GW
        let vps = vec![3.0, 1.0, 0.5, 0.5, 0.0];
        let adj = vec![-1.0, 0.0, 0.0, 0.0, 0.0];
        let gw = compute_gw(&vps, &adj);
        assert_eq!(gw[0], 1.0); // keeps GW: adjusted 2.0, still highest
    }

    #[test]
    fn test_gw_finals_clear_winner() {
        // Clear winner with highest VP — gets the GW regardless of seed
        let vps = vec![3.0, 1.0, 0.5, 0.5, 0.0];
        let adj = vec![0.0; 5];
        let seats = vec!["p1", "p2", "p3", "p4", "p5"];
        let seed = vec!["p5", "p4", "p3", "p2", "p1"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        assert_eq!(gw, vec![1.0, 0.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_gw_finals_all_zero_vp_uses_seed() {
        // All at 0 VP — top seed wins the tiebreak
        let vps = vec![0.0, 0.0, 0.0, 0.0, 0.0];
        let adj = vec![0.0; 5];
        let seats = vec!["p3", "p1", "p5", "p2", "p4"];
        let seed = vec!["p1", "p2", "p3", "p4", "p5"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        // p1 is top seed (index 0 in seed_order), seated at position 1
        assert_eq!(gw, vec![0.0, 1.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_gw_finals_tied_vp_seed_tiebreak() {
        // Two players tied at 2 VP — lower seed position wins
        let vps = vec![2.0, 0.0, 2.0, 1.0, 0.0];
        let adj = vec![0.0; 5];
        let seats = vec!["p1", "p2", "p3", "p4", "p5"];
        // p3 has better seed (position 1) than p1 (position 2)
        let seed = vec!["p5", "p3", "p1", "p2", "p4"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        // p3 wins: same VP but better seed
        assert_eq!(gw, vec![0.0, 0.0, 1.0, 0.0, 0.0]);
    }

    #[test]
    fn test_gw_finals_no_2vp_threshold() {
        // Unlike prelim compute_gw, finals doesn't require 2 VP
        // Winner at 1.5 VP still gets GW
        let vps = vec![1.5, 1.0, 0.5, 0.5, 0.5];
        let adj = vec![0.0; 5];
        let seats = vec!["p1", "p2", "p3", "p4", "p5"];
        let seed = vec!["p1", "p2", "p3", "p4", "p5"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        assert_eq!(gw, vec![1.0, 0.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_gw_finals_adjustment_changes_winner() {
        // p1 has most raw VP but SA penalty drops them below p2
        let vps = vec![3.0, 2.5, 0.5, 0.0, 0.0];
        let adj = vec![-1.0, 0.0, 0.0, 0.0, 0.0];
        let seats = vec!["p1", "p2", "p3", "p4", "p5"];
        let seed = vec!["p1", "p2", "p3", "p4", "p5"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        // p2 wins: p1 adjusted to 2.0, p2 at 2.5
        assert_eq!(gw, vec![0.0, 1.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_gw_finals_empty() {
        let gw = compute_gw_finals(&[], &[], &[], &[]);
        assert!(gw.is_empty());
    }

    #[test]
    fn test_gw_finals_4_player_table() {
        // Finals can also be 4 players
        let vps = vec![2.0, 1.0, 1.0, 1.0];
        let adj = vec![0.0; 4];
        let seats = vec!["p1", "p2", "p3", "p4"];
        let seed = vec!["p1", "p2", "p3", "p4"]
            .into_iter()
            .map(String::from)
            .collect::<Vec<_>>();
        let gw = compute_gw_finals(&vps, &adj, &seats, &seed);
        assert_eq!(gw, vec![1.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn test_dq_player_cannot_checkin() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Disqualified", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "CheckIn", player_uid: "p1" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Disqualified"));
    }

    #[test]
    fn test_dq_sanction_blocks_checkin() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "CheckIn", player_uid: "p1" };
        let actor = make_organizer();
        let sanctions = json::array![
            { user_uid: "p1", level: "disqualification", round_number: json::Null, lifted_at: json::Null, deleted_at: json::Null }
        ];
        let result = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            &sanctions.dump(),
            &no_decks(),
        );
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("disqualification"));
    }

    #[test]
    fn test_suspension_blocks_checkin() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "CheckIn", player_uid: "p1" };
        let actor = make_organizer();
        let sanctions = json::array![
            { user_uid: "p1", level: "suspension", round_number: json::Null, lifted_at: json::Null, deleted_at: json::Null }
        ];
        let result = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            &sanctions.dump(),
            &no_decks(),
        );
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("suspended"));
    }

    #[test]
    fn test_checkinall_skips_dq_players() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Registered", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Disqualified", payment_status: "Pending", toss: 0 },
            { user_uid: "p3", state: "Registered", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "CheckInAll" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
        assert_eq!(
            updated["players"][1]["state"].as_str(),
            Some("Disqualified")
        ); // stays DQ'd
        assert_eq!(updated["players"][2]["state"].as_str(), Some("Checked-in"));
    }

    #[test]
    fn test_finish_tournament_preserves_dq() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Disqualified", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "FinishTournament" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Finished"));
        assert_eq!(
            updated["players"][1]["state"].as_str(),
            Some("Disqualified")
        ); // preserved
    }

    #[test]
    fn test_reopen_tournament_preserves_dq() {
        let mut tournament = make_tournament();
        tournament["state"] = "Finished".into();
        tournament["players"] = json::array![
            { user_uid: "p1", state: "Finished", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Disqualified", payment_status: "Pending", toss: 0 },
        ];
        let event = json::object! { type: "ReopenTournament" };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"][0]["state"].as_str(), Some("Checked-in"));
        assert_eq!(
            updated["players"][1]["state"].as_str(),
            Some("Disqualified")
        ); // preserved
    }

    // --- AlterSeating tests ---

    /// Build a tournament in Playing state with one round of 2 tables of 4
    fn tournament_with_round() -> JsonValue {
        let mut t = make_tournament();
        t["state"] = "Playing".into();
        t["players"] = json::array![
            { user_uid: "p1", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p3", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p4", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p5", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p6", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p7", state: "Playing", payment_status: "Pending", toss: 0 },
            { user_uid: "p8", state: "Playing", payment_status: "Pending", toss: 0 },
        ];
        t["rounds"] = json::array![
            [
                {
                    seating: [
                        { player_uid: "p1", result: { gw: 1, vp: 2.0, tp: 48 }, judge_uid: "" },
                        { player_uid: "p2", result: { gw: 0, vp: 1.0, tp: 24 }, judge_uid: "" },
                        { player_uid: "p3", result: { gw: 0, vp: 0.5, tp: 12 }, judge_uid: "" },
                        { player_uid: "p4", result: { gw: 0, vp: 0.5, tp: 12 }, judge_uid: "" },
                    ],
                    state: "Finished",
                    override: json::Null,
                },
                {
                    seating: [
                        { player_uid: "p5", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                        { player_uid: "p6", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                        { player_uid: "p7", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                        { player_uid: "p8", result: { gw: 0, vp: 0.0, tp: 0 }, judge_uid: "" },
                    ],
                    state: "In Progress",
                    override: json::Null,
                },
            ]
        ];
        t
    }

    #[test]
    fn test_alter_seating_swap_within_same_table_preserves_results() {
        let tournament = tournament_with_round();
        // Swap p1 and p2 within table 0, keep table 1 unchanged
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p2", "p1", "p3", "p4"], ["p5", "p6", "p7", "p8"]],
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();

        // p2 stays in table 0 -> result preserved
        assert_eq!(
            updated["rounds"][0][0]["seating"][0]["player_uid"].as_str(),
            Some("p2")
        );
        assert_eq!(
            updated["rounds"][0][0]["seating"][0]["result"]["vp"].as_f64(),
            Some(1.0)
        );
        // p1 stays in table 0 -> result preserved
        assert_eq!(
            updated["rounds"][0][0]["seating"][1]["result"]["vp"].as_f64(),
            Some(2.0)
        );
    }

    #[test]
    fn test_alter_seating_cross_table_swap_resets_results() {
        let tournament = tournament_with_round();
        // Move p1 (table 0, has results) to table 1, move p5 (table 1) to table 0
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p5", "p2", "p3", "p4"], ["p1", "p6", "p7", "p8"]],
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();

        // p5 moved from table 1 to table 0 -> result reset
        assert_eq!(
            updated["rounds"][0][0]["seating"][0]["result"]["vp"].as_f64(),
            Some(0.0)
        );
        // p2 stayed in table 0 -> result preserved
        assert_eq!(
            updated["rounds"][0][0]["seating"][1]["result"]["vp"].as_f64(),
            Some(1.0)
        );
        // p1 moved from table 0 to table 1 -> result reset
        assert_eq!(
            updated["rounds"][0][1]["seating"][0]["result"]["vp"].as_f64(),
            Some(0.0)
        );
        // Table 0 now has mixed zero/non-zero results; table 1 has all zeros -> "In Progress"
        assert_eq!(
            updated["rounds"][0][1]["state"].as_str(),
            Some("In Progress")
        );
    }

    #[test]
    fn test_alter_seating_wrong_table_count_fails() {
        let tournament = tournament_with_round();
        // Provide 3 tables instead of 2
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p1", "p2", "p3", "p4"], ["p5", "p6"], ["p7", "p8"]],
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Table count mismatch"));
    }

    #[test]
    fn test_alter_seating_unknown_player_fails() {
        let tournament = tournament_with_round();
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p1", "p2", "p3", "UNKNOWN"], ["p5", "p6", "p7", "p8"]],
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("not found"));
    }

    #[test]
    fn test_alter_seating_requires_organizer() {
        let tournament = tournament_with_round();
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p1", "p2", "p3", "p4"], ["p5", "p6", "p7", "p8"]],
        };
        let actor = make_player("p1");
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers"));
    }

    #[test]
    fn test_alter_seating_invalid_state_fails() {
        let mut tournament = tournament_with_round();
        tournament["state"] = "Registration".into();
        let event = json::object! {
            type: "AlterSeating",
            round: 0,
            seating: [["p1", "p2", "p3", "p4"], ["p5", "p6", "p7", "p8"]],
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Cannot alter seating"));
    }

    #[test]
    fn test_update_config_basic() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: {
                name: "New Name",
                format: "V5",
                max_rounds: 4,
            },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["name"].as_str(), Some("New Name"));
        assert_eq!(updated["format"].as_str(), Some("V5"));
        assert_eq!(updated["max_rounds"].as_usize(), Some(4));
    }

    #[test]
    fn test_update_config_null_country() {
        let mut tournament = make_tournament();
        tournament["country"] = "France".into();
        let event = json::object! {
            type: "UpdateConfig",
            config: {
                country: json::Null,
            },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert!(updated["country"].is_null());
    }

    #[test]
    fn test_update_config_invalid_format() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { format: "Invalid" },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("Invalid format"));
    }

    #[test]
    fn test_update_config_max_rounds_too_low() {
        let mut tournament = tournament_with_round();
        // Finish the round so it counts as completed
        tournament["rounds"][0][0]["state"] = "Finished".into();
        tournament["rounds"][0][1]["state"] = "Finished".into();
        let event = json::object! {
            type: "UpdateConfig",
            config: { max_rounds: 0 },
        };
        let actor = make_organizer();
        // max_rounds=0 means unlimited, should succeed
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
    }

    #[test]
    fn test_update_config_non_organizer_fails() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { name: "Hacked" },
        };
        let actor = make_player("player-1");
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers"));
    }

    #[test]
    fn test_update_config_empty_name_fails() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { name: "" },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("name cannot be empty"));
    }

    #[test]
    fn test_update_config_timer_fields() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: {
                round_time: 7200,
                finals_time: 9000,
                time_extension_policy: "clock_stop",
            },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["round_time"].as_i64(), Some(7200));
        assert_eq!(updated["finals_time"].as_i64(), Some(9000));
        assert_eq!(
            updated["time_extension_policy"].as_str(),
            Some("clock_stop")
        );
    }

    #[test]
    fn test_update_config_invalid_extension_policy() {
        let tournament = make_tournament();
        let event = json::object! {
            type: "UpdateConfig",
            config: { time_extension_policy: "invalid" },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_err());
        assert!(result
            .unwrap_err()
            .contains("Invalid time_extension_policy"));
    }

    #[test]
    fn test_update_config_partial_update() {
        let mut tournament = make_tournament();
        tournament["venue"] = "Old Venue".into();
        let event = json::object! {
            type: "UpdateConfig",
            config: { description: "New desc" },
        };
        let actor = make_organizer();
        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["description"].as_str(), Some("New desc"));
        // venue should remain unchanged
        assert_eq!(updated["venue"].as_str(), Some("Old Venue"));
    }

    #[test]
    fn test_checkin_auto_registers_unregistered_player() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![];

        let event = json::object! { type: "CheckIn", player_uid: "player-1" };
        let actor = make_player("player-1");

        let result = run_event(&tournament, &event, &actor);
        assert!(result.is_ok());
        let updated = json::parse(&result.unwrap()).unwrap();
        assert_eq!(updated["players"].len(), 1);
        assert_eq!(
            updated["players"][0]["user_uid"].as_str(),
            Some("player-1")
        );
        assert_eq!(
            updated["players"][0]["state"].as_str(),
            Some("Checked-in")
        );
    }

    #[test]
    fn test_checkin_auto_register_blocked_by_dq() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![];

        let event = json::object! { type: "CheckIn", player_uid: "player-1" };
        let actor = make_player("player-1");
        let sanctions = r#"[{"user_uid":"player-1","level":"disqualification","lifted_at":null,"deleted_at":null}]"#;

        let raw = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            sanctions,
            &no_decks(),
        );
        assert!(raw.is_err());
        assert!(raw.unwrap_err().contains("disqualification"));
    }

    #[test]
    fn test_checkin_auto_register_blocked_by_suspension() {
        let mut tournament = make_tournament();
        tournament["state"] = "Waiting".into();
        tournament["players"] = json::array![];

        let event = json::object! { type: "CheckIn", player_uid: "player-1" };
        let actor = make_player("player-1");
        let sanctions = r#"[{"user_uid":"player-1","level":"suspension","lifted_at":null,"deleted_at":null}]"#;

        let raw = process_tournament_event(
            &tournament.dump(),
            &event.dump(),
            &actor.dump(),
            sanctions,
            &no_decks(),
        );
        assert!(raw.is_err());
        assert!(raw.unwrap_err().contains("suspended"));
    }

    // ================================================================
    // DeleteDeck tests
    // ================================================================

    #[test]
    fn test_delete_deck_success() {
        let tournament = tournament_with_player("Waiting");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: false,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("delete"));
    }

    #[test]
    fn test_delete_deck_auth_failure() {
        let tournament = tournament_with_player("Waiting");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: false,
        };
        let actor = make_player("other-player");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("organizers or the player"));
    }

    #[test]
    fn test_delete_deck_playing_blocked() {
        let tournament = tournament_with_player("Playing");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: false,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("in progress"));
    }

    #[test]
    fn test_delete_deck_finished_blocked() {
        let tournament = tournament_with_player("Finished");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: false,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("finished"));
    }

    #[test]
    fn test_delete_deck_organizer_always() {
        let tournament = tournament_with_player("Playing");
        let decks = r#"[{"user_uid": "player-1", "round": null, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: false,
        };
        let actor = make_organizer();
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("delete"));
    }

    // ================================================================
    // Multideck tests
    // ================================================================

    fn multideck_tournament(state: &str, rounds_played: usize) -> JsonValue {
        let mut t = make_tournament();
        t["state"] = state.into();
        t["multideck"] = true.into();
        t["players"] = json::array![
            { user_uid: "player-1", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];
        // Add dummy rounds to simulate played rounds
        let mut rounds = json::JsonValue::new_array();
        for _ in 0..rounds_played {
            let table = json::object! {
                seating: [{ player_uid: "player-1", result: { vp: 0 } }],
                state: "Finished",
            };
            let mut round = json::JsonValue::new_array();
            let _ = round.push(table);
            let _ = rounds.push(round);
        }
        t["rounds"] = rounds;
        t
    }

    #[test]
    fn test_multideck_upsert_round_0() {
        let tournament = multideck_tournament("Waiting", 0);
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "Round 1 Deck", author: "", comments: "", cards: {} },
            multideck: true,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("upsert"));
        assert_eq!(deck_ops[0]["multideck"].as_bool(), Some(true));
    }

    #[test]
    fn test_multideck_upsert_round_1_playing() {
        // 1 round played, player has 1 deck → new deck goes at index 1 (unlocked)
        let tournament = multideck_tournament("Playing", 1);
        let decks = r#"[{"user_uid": "player-1", "round": 0, "uid": "d0"}]"#;
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "Round 2 Deck", author: "", comments: "", cards: {} },
            multideck: true,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("upsert"));
    }

    #[test]
    fn test_multideck_upsert_locked_round_blocked() {
        // 1 round played, player has 0 decks → new deck at index 0 (locked, round 0 already played)
        let tournament = multideck_tournament("Playing", 1);
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "player-1",
            deck: { name: "Late Deck", author: "", comments: "", cards: {} },
            multideck: true,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, "[]");
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("already started"));
    }

    #[test]
    fn test_multideck_delete_unlocked() {
        // 1 round played, player has 2 decks → delete index 1 (unlocked)
        let tournament = multideck_tournament("Playing", 1);
        let decks = r#"[{"user_uid": "player-1", "round": 0, "uid": "d0"}, {"user_uid": "player-1", "round": 1, "uid": "d1"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: 1,
            multideck: true,
        };
        let actor = make_player("player-1");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, decks).unwrap();
        assert_eq!(deck_ops.len(), 1);
        assert_eq!(deck_ops[0]["op"].as_str(), Some("delete"));
    }

    #[test]
    fn test_multideck_delete_locked_blocked() {
        // 1 round played, delete index 0 (locked) → blocked
        let tournament = multideck_tournament("Playing", 1);
        let decks = r#"[{"user_uid": "player-1", "round": 0, "uid": "d0"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: 0,
            multideck: true,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("already started"));
    }

    #[test]
    fn test_multideck_delete_requires_index() {
        // Multideck delete without deck_index during Playing → error
        let tournament = multideck_tournament("Playing", 1);
        let decks = r#"[{"user_uid": "player-1", "round": 0, "uid": "d0"}]"#;
        let event = json::object! {
            type: "DeleteDeck",
            player_uid: "player-1",
            deck_index: json::Null,
            multideck: true,
        };
        let actor = make_player("player-1");
        let result = run_event_with_decks(&tournament, &event, &actor, decks);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("deck_index required"));
    }

    #[test]
    fn test_multideck_lifecycle() {
        // Upload deck at round 0, start round → round 0 deck locked
        let mut tournament = multideck_tournament("Waiting", 0);
        // Add enough players for StartRound
        tournament["players"] = json::array![
            { user_uid: "p0", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p1", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p2", state: "Checked-in", payment_status: "Pending", toss: 0 },
            { user_uid: "p3", state: "Checked-in", payment_status: "Pending", toss: 0 },
        ];

        // Upload deck for p0 at round 0
        let event = json::object! {
            type: "UpsertDeck",
            player_uid: "p0",
            deck: { name: "Round 1 Deck", author: "", comments: "", cards: {} },
            multideck: true,
        };
        let actor = make_player("p0");
        let (_, deck_ops) = run_event_with_decks(&tournament, &event, &actor, "[]").unwrap();
        assert_eq!(deck_ops.len(), 1);

        // Start round
        let start_event = json::parse(
            r#"{"type": "StartRound", "seating": [["p0","p1","p2","p3"]]}"#,
        ).unwrap();
        let org = make_organizer();
        let result = run_event(&tournament, &start_event, &org).unwrap();
        let updated = json::parse(&result).unwrap();
        assert_eq!(updated["state"].as_str(), Some("Playing"));
        assert_eq!(updated["rounds"].len(), 1);

        // Now try to delete p0's round 0 deck → should be locked
        let delete_event = json::object! {
            type: "DeleteDeck",
            player_uid: "p0",
            deck_index: 0,
            multideck: true,
        };
        let actor_p0 = make_player("p0");
        let decks = r#"[{"user_uid": "p0", "round": 0, "uid": "d0"}]"#;
        let delete_result = run_event_with_decks(&updated, &delete_event, &actor_p0, decks);
        assert!(delete_result.is_err());
        assert!(delete_result.unwrap_err().contains("already started"));
    }
}
