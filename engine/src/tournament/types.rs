//! Type definitions for tournament engine.

use json::JsonValue;

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
        vekn_id: Option<String>,
    },
    Unregister {
        user_uid: String,
    },
    AddPlayer {
        user_uid: String,
        vekn_id: Option<String>,
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

    // Tournament creation
    CreateTournament {
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
pub enum VpError {
    InvalidTableSize,
    InsufficientTotal,
    ExcessiveTotal,
    MissingVp(usize),          // seat index (0-based)
    MissingHalfVp(Vec<usize>), // seat indices
}

#[derive(Debug, Clone)]
pub struct ActorContext {
    pub uid: String,
    pub roles: Vec<String>,
    pub is_organizer: bool,
    pub can_organize_league_uids: Vec<String>,
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
        let can_organize_league_uids: Vec<String> = value["can_organize_league_uids"]
            .members()
            .filter_map(|v| v.as_str().map(|s| s.to_string()))
            .collect();
        Ok(Self {
            uid,
            roles,
            is_organizer,
            can_organize_league_uids,
        })
    }

    pub fn can_manage_tournaments(&self) -> bool {
        self.roles
            .iter()
            .any(|r| r == "IC" || r == "NC" || r == "Prince")
    }
}
