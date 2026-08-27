use crate::error::EngineError;
use crate::model::arg;
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
    /// Reached the per-player round cap: done with prelims, still finals-eligible
    /// (distinct from `Finished`, which means withdrew/dropped/tournament-over).
    Completed,
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
            "Completed" => Some(Self::Completed),
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
            Self::Completed => "Completed",
            Self::Finished => "Finished",
            Self::Disqualified => "Disqualified",
        }
    }
}

#[derive(Debug, Clone)]
pub enum TournamentEvent {
    OpenRegistration,
    CloseRegistration,
    CancelRegistration,
    ReopenRegistration,
    ReopenTournament,
    FinishTournament,

    Register {
        user_uid: String,
        vekn_id: Option<String>,
        display_name: Option<String>,
    },
    Unregister {
        user_uid: String,
    },
    AddPlayer {
        user_uid: String,
        vekn_id: Option<String>,
        display_name: Option<String>,
        /// Set by the bulk import, whose rows are registrations the players made
        /// themselves; an organizer adding a player never waitlists.
        waitlist_past_cap: bool,
    },
    RemovePlayer {
        user_uid: String,
    },
    DropOut {
        player_uid: String,
    },
    CheckIn {
        player_uid: String,
        vekn_id: Option<String>,
        display_name: Option<String>,
    },
    CheckOut {
        player_uid: String,
    },
    CheckInAll,
    ResetCheckIn,

    SetPaymentStatus {
        player_uid: String,
        status: String,
    },
    MarkAllPaid,

    /// UI label is "Proxy" — the field name avoids colliding with `Tournament.proxies`.
    SetNonCompeting {
        player_uid: String,
        non_competing: bool,
    },
    SetWaitlisted {
        player_uid: String,
        waitlisted: bool,
    },

    StartRound {
        seating: Option<Vec<Vec<String>>>,
    },
    FinishRound {
        round: Option<usize>,
    },
    CancelRound {
        round: Option<usize>,
    },
    RestoreRound {
        round: Option<usize>,
    },
    // Player-authorized: a registered player seats one pod (open-rounds, opt-in flag).
    SelfOrganizeRound {
        player_uids: Vec<String>,
    },
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
        /// Target round; None = last round. An earlier round must be live.
        round: Option<usize>,
    },
    UnseatPlayer {
        player_uid: String,
        /// Target round; None = last round. An earlier round must be live.
        round: Option<usize>,
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

    SetToss {
        player_uid: String,
        toss: u32,
    },
    RandomToss,
    StartFinals,
    FinishFinals,
    CancelFinals,

    AlterSeating {
        round: usize,
        seating: Vec<Vec<String>>, // table -> player UIDs in order
    },

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

    RaffleDraw {
        label: String,
        pool: String,
        exclude_drawn: bool,
        count: usize,
        seed: u64,
        // Optional promo-catalog prize; display-only (never auto-writes the
        // distribution report — no double count)
        prize_promo_uid: Option<String>,
    },
    RaffleUndo,
    RaffleClear,

    /// Replace-the-whole-list; no state gate — post-finish corrections are
    /// first-class.
    ReportPromos {
        promos: JsonValue,
        stock_source_uid: Option<String>,
    },

    UpdateConfig {
        config: JsonValue,
    },

    /// IC correction of an event we hold no play data for: replaces roster and
    /// winner wholesale. No `standings` payload — they are prelim-only by
    /// contract, and an archival record has no prelim, so the rows stay zeroed.
    SetArchivalResults {
        winner: String,
        players: Vec<String>,
        reported_player_count: usize,
    },
}

#[derive(Debug, Clone)]
pub struct SeatScore {
    pub player_uid: String,
    pub vp: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub enum VpError {
    InvalidTableSize,
    /// Below the lowest total any complete table can reach — seats are still
    /// being entered. Not an error the user should be shown.
    IncompleteTotal,
    ExcessiveTotal,
    /// A valid total, but a VP sits with a Methuselah who did not make the
    /// oust — only a judge can close this table.
    RedirectedVp,
    MissingVp(usize), // seat index (0-based)
    /// A seat's half VP disagrees with how the game ended — half too many or
    /// half too few; the seat is at fault either way.
    HalfVpMismatch(Vec<usize>), // seat indices
}

impl VpError {
    /// Stable code plus seats at fault, for the UI. `Debug` stays log text —
    /// callers branch on this instead.
    pub fn to_json(&self) -> JsonValue {
        let (code, seats): (&str, Vec<usize>) = match self {
            VpError::InvalidTableSize => ("invalid_table_size", vec![]),
            VpError::IncompleteTotal => ("incomplete", vec![]),
            VpError::ExcessiveTotal => ("excessive_total", vec![]),
            VpError::RedirectedVp => ("redirected_vp", vec![]),
            VpError::MissingVp(i) => ("impossible_oust_order", vec![*i]),
            VpError::HalfVpMismatch(idx) => ("half_vp_mismatch", idx.clone()),
        };
        json::object! { arg::CODE => code, arg::SEATS => seats }
    }
}

#[derive(Debug, Clone)]
pub struct ActorContext {
    pub uid: String,
    pub roles: Vec<String>,
    pub is_organizer: bool,
    pub can_organize_league_uids: Vec<String>,
    /// Request timestamp (ISO-8601 UTC), used to resolve time-derived sanction
    /// state (suspension expiry). Empty when the caller supplies no clock.
    pub now: String,
}

impl ActorContext {
    pub fn from_json(value: &JsonValue) -> Result<Self, EngineError> {
        let uid = value[arg::UID]
            .as_str()
            .ok_or("actor uid required")?
            .to_string();
        let roles: Vec<String> = value[arg::ROLES]
            .members()
            .filter_map(|r| r.as_str().map(|s| s.to_string()))
            .collect();
        let is_organizer = value[arg::IS_ORGANIZER].as_bool().unwrap_or(false);
        let can_organize_league_uids: Vec<String> = value[arg::CAN_ORGANIZE_LEAGUE_UIDS]
            .members()
            .filter_map(|v| v.as_str().map(|s| s.to_string()))
            .collect();
        let now = value[arg::NOW].as_str().unwrap_or("").to_string();
        Ok(Self {
            uid,
            roles,
            is_organizer,
            can_organize_league_uids,
            now,
        })
    }

    /// The permission-table view of this actor. Roles arrive as strings and
    /// unrecognised ones drop. **No country** — a tournament event carries none,
    /// so any `same_country` capability checked through this fails closed.
    pub fn user_context(&self) -> crate::permissions::UserContext {
        crate::permissions::UserContext {
            roles: self
                .roles
                .iter()
                .filter_map(|r| crate::permissions::Role::from_str(r))
                .collect(),
            country: None,
            vekn_id: None,
            has_nda: false,
        }
    }

    pub fn can_manage_tournaments(&self) -> bool {
        // Same official-roles list permissions::is_official gates on — the
        // shared const keeps create (here) and manage (permissions.rs) aligned.
        self.roles.iter().any(|r| {
            crate::permissions::Role::from_str(r)
                .is_some_and(|role| crate::permissions::OFFICIAL_ROLES.contains(&role))
        })
    }
}
