//! Structured engine errors: the single greppable taxonomy.
//!
//! Every fallible core function returns `Result<T, EngineError>`. The enum is the
//! contract with the frontend: `code()` strings map 1:1 to paraglide `err_*` keys
//! (dots → underscores), `params()` feed `{param}` interpolation, and `Display`
//! renders the canonical English — kept byte-identical to `frontend/messages/en.json`
//! so the Discord bot, server logs, and any non-i18n client read the same text.
//!
//! Domain rejections (a user can act on them) get their own variant. Anything the
//! user can't act on — JSON parse/serialize failures, event-schema violations,
//! enum drift between stacks — collapses to `Internal { detail }`: the frontend
//! shows a generic message and logs the detail. Validation of *already-parsed*
//! JSON must construct an explicit variant; the `From` impls below exist only for
//! genuine deserialization failures and `?`-converted internal notes.

use std::fmt;

#[derive(Debug, Clone, PartialEq)]
pub enum EngineError {
    // Authorization
    NotOrganizer,
    CreateForbidden,
    UnregisterOnlySelf,
    DropOutForbidden,
    CheckInForbidden,
    DeckUploadForbidden,
    DeckDeleteForbidden,
    ScoreForbidden,
    ScoreLocked,
    ScoreSetByOrganizer,
    LeagueLinkForbidden,
    // Registration / eligibility
    VeknIdRequired,
    AlreadyRegistered,
    NotRegistered,
    PlayerDisqualified,
    PlayerSuspended,
    PlayerNotFound,
    PlayerNotCheckedIn,
    PlayerAlreadyFinished,
    PlayerWrongState { current: String },
    // State machine
    WrongState { expected: String, current: String },
    CannotAddPlayers,
    CannotRemovePlayers,
    UseDropOut,
    CannotDropOut,
    CannotFinish,
    CannotAlterSeating,
    CannotSetNonCompeting,
    // Rounds / seating
    NoRoundInProgress,
    NoRoundToFinish,
    NoRoundToCancel,
    OnlyLastRoundCancellable,
    TablesNotFinished { tables: String },
    PrelimAfterFinals,
    PlayerReachedMaxRounds,
    NotEnoughPlayers,
    InvalidTableSize { size: usize },
    PlayerNotInSubset { player: String },
    DuplicatePlayer,
    SeatingIncomplete,
    InvalidRound,
    InvalidTable,
    InvalidSeat,
    FinalsOneTable,
    FinalsPlayerCount,
    FinalsPlayerSet,
    TableCountMismatch,
    PlayerCountMismatch,
    SeatingViolatesR1,
    PlayerNotInRound { player: String },
    TableFull,
    TableNotEmpty,
    // Scoring / finals / toss
    InvalidScore,
    FinalsMinRounds,
    FinalsAlreadyStarted,
    FinalsNotEnoughPlayers,
    FinalsUnresolvedTies,
    NoFinalsInProgress,
    FinalsTableUnfinished,
    TossMinRounds,
    // Decks / raffle / config
    DeckLockedFinished,
    DeckLockedPlaying,
    DeckLockedRound,
    RaffleCountMin,
    RaffleNoPlayers,
    RaffleNoDraws,
    RaffleNonePlayed,
    RaffleWrongState,
    NameRequired,
    MaxRoundsBelowCompleted { max: usize, completed: usize },
    DeckNoCards,
    SeatingMinPlayers,
    SeatingMinRounds,
    // Self-organized rounds (player-initiated open-rounds pods)
    SelfOrganizeDisabled,
    SelfOrganizeNotOpenRounds,
    SelfOrganizeRequiresOnline,
    SelfOrganizeNotSeated,
    SelfOrganizeIneligible { player: String },
    // Not user-actionable
    Internal { detail: String },
}

impl EngineError {
    pub fn internal(detail: impl fmt::Display) -> Self {
        EngineError::Internal {
            detail: detail.to_string(),
        }
    }

    /// Stable code: the i18n contract with the frontend (`err_*` paraglide keys).
    pub fn code(&self) -> &'static str {
        use EngineError::*;
        match self {
            NotOrganizer => "tournament.not_organizer",
            CreateForbidden => "tournament.create_forbidden",
            UnregisterOnlySelf => "tournament.unregister_only_self",
            DropOutForbidden => "tournament.drop_out_forbidden",
            CheckInForbidden => "tournament.check_in_forbidden",
            DeckUploadForbidden => "tournament.deck_upload_forbidden",
            DeckDeleteForbidden => "tournament.deck_delete_forbidden",
            ScoreForbidden => "tournament.score_forbidden",
            ScoreLocked => "tournament.score_locked",
            ScoreSetByOrganizer => "tournament.score_set_by_organizer",
            LeagueLinkForbidden => "tournament.league_link_forbidden",
            VeknIdRequired => "tournament.vekn_id_required",
            AlreadyRegistered => "tournament.already_registered",
            NotRegistered => "tournament.not_registered",
            PlayerDisqualified => "tournament.player_disqualified",
            PlayerSuspended => "tournament.player_suspended",
            PlayerNotFound => "tournament.player_not_found",
            PlayerNotCheckedIn => "tournament.player_not_checked_in",
            PlayerAlreadyFinished => "tournament.player_already_finished",
            PlayerWrongState { .. } => "tournament.player_wrong_state",
            WrongState { .. } => "tournament.wrong_state",
            CannotAddPlayers => "tournament.cannot_add_players",
            CannotRemovePlayers => "tournament.cannot_remove_players",
            UseDropOut => "tournament.use_drop_out",
            CannotDropOut => "tournament.cannot_drop_out",
            CannotFinish => "tournament.cannot_finish",
            CannotAlterSeating => "tournament.cannot_alter_seating",
            CannotSetNonCompeting => "tournament.cannot_set_non_competing",
            NoRoundInProgress => "tournament.no_round_in_progress",
            NoRoundToFinish => "tournament.no_round_to_finish",
            NoRoundToCancel => "tournament.no_round_to_cancel",
            OnlyLastRoundCancellable => "tournament.only_last_round_cancellable",
            TablesNotFinished { .. } => "tournament.tables_not_finished",
            PrelimAfterFinals => "tournament.prelim_after_finals",
            PlayerReachedMaxRounds => "tournament.player_reached_max_rounds",
            NotEnoughPlayers => "tournament.not_enough_players",
            InvalidTableSize { .. } => "tournament.invalid_table_size",
            PlayerNotInSubset { .. } => "tournament.player_not_in_subset",
            DuplicatePlayer => "tournament.duplicate_player",
            SeatingIncomplete => "tournament.seating_incomplete",
            InvalidRound => "tournament.invalid_round",
            InvalidTable => "tournament.invalid_table",
            InvalidSeat => "tournament.invalid_seat",
            FinalsOneTable => "tournament.finals_one_table",
            FinalsPlayerCount => "tournament.finals_player_count",
            FinalsPlayerSet => "tournament.finals_player_set",
            TableCountMismatch => "tournament.table_count_mismatch",
            PlayerCountMismatch => "tournament.player_count_mismatch",
            SeatingViolatesR1 => "tournament.seating_violates_r1",
            PlayerNotInRound { .. } => "tournament.player_not_in_round",
            TableFull => "tournament.table_full",
            TableNotEmpty => "tournament.table_not_empty",
            InvalidScore => "tournament.invalid_score",
            FinalsMinRounds => "tournament.finals_min_rounds",
            FinalsAlreadyStarted => "tournament.finals_already_started",
            FinalsNotEnoughPlayers => "tournament.finals_not_enough_players",
            FinalsUnresolvedTies => "tournament.finals_unresolved_ties",
            NoFinalsInProgress => "tournament.no_finals_in_progress",
            FinalsTableUnfinished => "tournament.finals_table_unfinished",
            TossMinRounds => "tournament.toss_min_rounds",
            DeckLockedFinished => "tournament.deck_locked_finished",
            DeckLockedPlaying => "tournament.deck_locked_playing",
            DeckLockedRound => "tournament.deck_locked_round",
            RaffleCountMin => "tournament.raffle_count_min",
            RaffleNoPlayers => "tournament.raffle_no_players",
            RaffleNoDraws => "tournament.raffle_no_draws",
            RaffleNonePlayed => "tournament.raffle_none_played",
            RaffleWrongState => "tournament.raffle_wrong_state",
            NameRequired => "tournament.name_required",
            MaxRoundsBelowCompleted { .. } => "tournament.max_rounds_below_completed",
            DeckNoCards => "deck.no_cards",
            SeatingMinPlayers => "seating.min_players",
            SeatingMinRounds => "seating.min_rounds",
            SelfOrganizeDisabled => "tournament.self_organize_disabled",
            SelfOrganizeNotOpenRounds => "tournament.self_organize_not_open_rounds",
            SelfOrganizeRequiresOnline => "tournament.self_organize_requires_online",
            SelfOrganizeNotSeated => "tournament.self_organize_not_seated",
            SelfOrganizeIneligible { .. } => "tournament.self_organize_ineligible",
            Internal { .. } => "internal",
        }
    }

    /// Interpolation params, stringly-typed end-to-end (WASM, HTTP, paraglide).
    pub fn params(&self) -> Vec<(&'static str, String)> {
        use EngineError::*;
        match self {
            PlayerWrongState { current } => vec![("current", current.clone())],
            WrongState { expected, current } => {
                vec![("expected", expected.clone()), ("current", current.clone())]
            }
            TablesNotFinished { tables } => vec![("tables", tables.clone())],
            InvalidTableSize { size } => vec![("size", size.to_string())],
            PlayerNotInSubset { player } => vec![("player", player.clone())],
            PlayerNotInRound { player } => vec![("player", player.clone())],
            SelfOrganizeIneligible { player } => vec![("player", player.clone())],
            MaxRoundsBelowCompleted { max, completed } => vec![
                ("max", max.to_string()),
                ("completed", completed.to_string()),
            ],
            Internal { detail } => vec![("detail", detail.clone())],
            _ => vec![],
        }
    }

    /// Err-arm wire format for both bindings:
    /// `{"code": "...", "params": {...}, "message": "<canonical English>"}`.
    pub fn to_json(&self) -> String {
        let mut params = json::JsonValue::new_object();
        for (k, v) in self.params() {
            params[k] = v.into();
        }
        json::object! { code: self.code(), params: params, message: self.to_string() }.dump()
    }
}

impl fmt::Display for EngineError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        use EngineError::*;
        match self {
            NotOrganizer => write!(f, "Only organizers can perform this action"),
            CreateForbidden => write!(f, "Only IC, NC, or Prince can create tournaments"),
            UnregisterOnlySelf => write!(f, "You can only unregister yourself"),
            DropOutForbidden => {
                write!(f, "Only organizers or the player themselves can drop out")
            }
            CheckInForbidden => {
                write!(f, "Only organizers or the player themselves can check in")
            }
            DeckUploadForbidden => write!(f, "Only organizers or the player can upload a deck"),
            DeckDeleteForbidden => write!(f, "Only organizers or the player can delete a deck"),
            ScoreForbidden => write!(f, "Not authorized to score this table"),
            ScoreLocked => write!(f, "Table score is locked by judge"),
            ScoreSetByOrganizer => write!(f, "Score has been set by organiser"),
            LeagueLinkForbidden => {
                write!(
                    f,
                    "Only league organizers can link tournaments to this league"
                )
            }
            VeknIdRequired => write!(f, "Player must have a VEKN ID"),
            AlreadyRegistered => write!(f, "Already registered"),
            NotRegistered => write!(f, "Player is not registered in this tournament"),
            PlayerDisqualified => write!(f, "Player is disqualified and cannot participate"),
            PlayerSuspended => write!(f, "Player is suspended and cannot participate"),
            PlayerNotFound => write!(f, "Player not found"),
            PlayerNotCheckedIn => write!(f, "Player is not checked in"),
            PlayerAlreadyFinished => write!(f, "Player already finished"),
            PlayerWrongState { current } => {
                write!(f, "Player must be Registered (currently {})", current)
            }
            WrongState { expected, current } => write!(
                f,
                "Tournament must be in {} state (currently {})",
                expected, current
            ),
            CannotAddPlayers => write!(f, "Cannot add players in this state"),
            CannotRemovePlayers => write!(f, "Cannot remove players in this state"),
            UseDropOut => write!(f, "Use DropOut for players who have played"),
            CannotDropOut => write!(f, "Cannot drop out in this state"),
            CannotFinish => write!(f, "Cannot finish from this state"),
            CannotAlterSeating => write!(f, "Cannot alter seating in this state"),
            CannotSetNonCompeting => {
                write!(
                    f,
                    "Cannot change proxy status after finals or once the tournament is finished"
                )
            }
            NoRoundInProgress => write!(f, "No rounds in progress"),
            NoRoundToFinish => write!(f, "No rounds to finish"),
            NoRoundToCancel => write!(f, "No rounds to cancel"),
            OnlyLastRoundCancellable => write!(f, "Can only cancel the last round"),
            TablesNotFinished { tables } => write!(f, "Tables {} not finished yet", tables),
            PrelimAfterFinals => write!(f, "Cannot start a preliminary round after finals"),
            PlayerReachedMaxRounds => write!(f, "Player has reached their round cap"),
            NotEnoughPlayers => write!(f, "Need at least 4 checked-in players"),
            InvalidTableSize { size } => write!(f, "Invalid table size: {}", size),
            PlayerNotInSubset { player } => {
                write!(f, "Player {} not in selected subset", player)
            }
            DuplicatePlayer => write!(f, "Duplicate player in seating"),
            SeatingIncomplete => {
                write!(f, "Submitted seating does not include all selected players")
            }
            InvalidRound => write!(f, "Invalid round number"),
            InvalidTable => write!(f, "Invalid table number"),
            InvalidSeat => write!(f, "Invalid seat number"),
            FinalsOneTable => write!(f, "Finals expects exactly one table"),
            FinalsPlayerCount => write!(f, "Finals player count mismatch"),
            FinalsPlayerSet => write!(f, "Finals player set mismatch"),
            TableCountMismatch => write!(f, "Table count mismatch"),
            PlayerCountMismatch => write!(f, "Player count mismatch"),
            SeatingViolatesR1 => write!(f, "Seating violates R1 (predator-prey repeat)"),
            PlayerNotInRound { player } => {
                write!(f, "Player {} not found in current round seating", player)
            }
            TableFull => write!(f, "Table already has 5 players"),
            TableNotEmpty => write!(f, "Cannot remove a table with players seated"),
            InvalidScore => {
                write!(f, "Invalid score: impossible VP combination for this table")
            }
            FinalsMinRounds => write!(f, "Need at least 2 rounds before finals"),
            FinalsAlreadyStarted => write!(f, "Finals already started"),
            FinalsNotEnoughPlayers => {
                write!(
                    f,
                    "Need at least 5 eligible players with results for finals"
                )
            }
            FinalsUnresolvedTies => write!(f, "Resolve all ties in top 5 before starting finals"),
            NoFinalsInProgress => write!(f, "No finals in progress"),
            FinalsTableUnfinished => write!(f, "Finals table must be Finished first"),
            TossMinRounds => write!(f, "Need at least 2 rounds before setting toss"),
            DeckLockedFinished => write!(f, "Cannot modify deck after tournament is finished"),
            DeckLockedPlaying => {
                write!(f, "Cannot modify deck while tournament is in progress")
            }
            DeckLockedRound => {
                write!(
                    f,
                    "Cannot modify a deck for a round that has already started"
                )
            }
            RaffleCountMin => write!(f, "Raffle count must be at least 1"),
            RaffleNoPlayers => write!(f, "No eligible players in pool"),
            RaffleNoDraws => write!(f, "No raffle draws to undo"),
            RaffleNonePlayed => write!(f, "No players available to raffle yet"),
            RaffleWrongState => write!(
                f,
                "Raffle requires tournament in Waiting, Playing, or Finished state"
            ),
            NameRequired => write!(f, "Tournament name cannot be empty"),
            MaxRoundsBelowCompleted { max, completed } => write!(
                f,
                "max_rounds ({}) cannot be less than completed rounds ({})",
                max, completed
            ),
            DeckNoCards => write!(f, "No cards found in deck list"),
            SeatingMinPlayers => write!(f, "At least 4 players required"),
            SeatingMinRounds => write!(f, "At least 1 round required"),
            SelfOrganizeDisabled => {
                write!(
                    f,
                    "Self-organized rounds are not enabled for this tournament"
                )
            }
            SelfOrganizeNotOpenRounds => {
                write!(f, "Self-organized rounds require an open-rounds tournament")
            }
            SelfOrganizeRequiresOnline => {
                write!(f, "Self-organized rounds require an online tournament")
            }
            SelfOrganizeNotSeated => write!(f, "You must seat yourself in a round you organize"),
            SelfOrganizeIneligible { player } => write!(
                f,
                "Player {} is already playing or done and cannot be seated",
                player
            ),
            Internal { detail } => write!(f, "Internal error: {}", detail),
        }
    }
}

impl std::error::Error for EngineError {}

impl From<json::Error> for EngineError {
    fn from(e: json::Error) -> Self {
        EngineError::internal(e)
    }
}

// `?`-ergonomics for internal notes like `.ok_or("user_uid required")?`.
// Domain rejections must NOT use these — construct an explicit variant.
impl From<&str> for EngineError {
    fn from(s: &str) -> Self {
        EngineError::internal(s)
    }
}

impl From<String> for EngineError {
    fn from(s: String) -> Self {
        EngineError::internal(s)
    }
}
