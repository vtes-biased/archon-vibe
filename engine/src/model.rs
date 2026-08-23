//! Every stored field name the engine reads, named once. `just model-drift`
//! checks each module against the model it is named for.

/// Keys on argument envelopes the caller builds for one call — not stored
/// objects, so nothing checks them against a model.
pub mod arg {
    pub const ACTOR: &str = "actor";
    pub const ACTOR_UID: &str = "actor_uid";
    pub const ADV: &str = "adv";
    pub const ALLOWED: &str = "allowed";
    pub const AUTHOR: &str = "author";
    pub const BANNED: &str = "banned";
    pub const BASELINE: &str = "baseline";
    pub const CAN_ORGANIZE_LEAGUE_UIDS: &str = "can_organize_league_uids";
    pub const CAPACITY: &str = "capacity";
    pub const CARDS: &str = "cards";
    pub const CATEGORIES: &str = "categories";
    pub const CLAN: &str = "clan";
    pub const CODE: &str = "code";
    pub const COMMENT: &str = "comment";
    pub const COMMENTS: &str = "comments";
    pub const CONFIG: &str = "config";
    pub const COUNT: &str = "count";
    pub const COUNTRY: &str = "country";
    pub const DECK: &str = "deck";
    pub const DECK_INDEX: &str = "deck_index";
    pub const DECK_OPS: &str = "deck_ops";
    pub const DECK_UID: &str = "deck_uid";
    pub const DISCIPLINES: &str = "disciplines";
    pub const DISPLAY_NAME: &str = "display_name";
    pub const DISQUALIFIED: &str = "disqualified";
    pub const ENOUGH_ROUNDS: &str = "enough_rounds";
    pub const ESCALATION: &str = "escalation";
    pub const EXCLUDE_DRAWN: &str = "exclude_drawn";
    pub const FINALIST: &str = "finalist";
    pub const FINALS: &str = "finals";
    pub const FULL_NAME: &str = "full_name";
    pub const GROUP: &str = "group";
    pub const GW: &str = "gw";
    pub const HAS_TIES: &str = "has_ties";
    pub const IS_ORGANIZER: &str = "is_organizer";
    pub const KEY: &str = "key";
    pub const KIND: &str = "kind";
    pub const LABEL: &str = "label";
    pub const LEAGUE_ORGANIZERS_UIDS: &str = "league_organizers_uids";
    pub const LEVEL: &str = "level";
    pub const LEVELS: &str = "levels";
    pub const MEAN_TRANSFERS: &str = "mean_transfers";
    pub const MEAN_VPS: &str = "mean_vps";
    pub const MEDIA: &str = "media";
    pub const MEDIA_KINDS: &str = "media_kinds";
    pub const MESSAGE: &str = "message";
    pub const MINIMUMS: &str = "minimums";
    pub const MULTIDECK: &str = "multideck";
    pub const NAME: &str = "name";
    pub const NAME_VARIANTS: &str = "name_variants";
    pub const NON_COMPETING: &str = "non_competing";
    pub const NOW: &str = "now";
    pub const OP: &str = "op";
    pub const OPEN_TO_COUNTRY_PRINCES: &str = "open_to_country_princes";
    pub const ORGANIZERS_UIDS: &str = "organizers_uids";
    pub const PARAMS: &str = "params";
    pub const PLACEMENT: &str = "placement";
    pub const PLAYER_COUNT: &str = "player_count";
    pub const PLAYER_UID: &str = "player_uid";
    pub const PLAYER_UIDS: &str = "player_uids";
    pub const PLAYERS: &str = "players";
    pub const POINTS: &str = "points";
    pub const POOL: &str = "pool";
    pub const POSSIBLE: &str = "possible";
    pub const PRINTED_NAME: &str = "printed_name";
    pub const PRIZE_PROMO_UID: &str = "prize_promo_uid";
    pub const PROMO_UID: &str = "promo_uid";
    pub const PROMOS: &str = "promos";
    pub const PUBLIC: &str = "public";
    pub const QTY: &str = "qty";
    pub const RANK: &str = "rank";
    pub const REASON: &str = "reason";
    pub const REPORTED_PLAYER_COUNT: &str = "reported_player_count";
    pub const RESOURCE: &str = "resource";
    pub const ROLES: &str = "roles";
    pub const ROUND: &str = "round";
    pub const ROUNDS: &str = "rounds";
    pub const RULE: &str = "rule";
    pub const RULES: &str = "rules";
    pub const SANCTIONS: &str = "sanctions";
    pub const SCORES: &str = "scores";
    pub const SEAT: &str = "seat";
    pub const SEAT1: &str = "seat1";
    pub const SEAT2: &str = "seat2";
    pub const SEATING: &str = "seating";
    pub const SEATS: &str = "seats";
    pub const SEED: &str = "seed";
    pub const SETS: &str = "sets";
    pub const SEVERITY: &str = "severity";
    pub const STANDINGS: &str = "standings";
    pub const STATUS: &str = "status";
    pub const STOCK_SOURCE_UID: &str = "stock_source_uid";
    pub const SUBCATEGORIES: &str = "subcategories";
    pub const TABLE: &str = "table";
    pub const TABLE1: &str = "table1";
    pub const TABLE2: &str = "table2";
    pub const TARGET_COUNTRY: &str = "target_country";
    pub const TARGET_UID: &str = "target_uid";
    pub const TIED_UIDS: &str = "tied_uids";
    pub const TOSS: &str = "toss";
    pub const TOURNAMENT: &str = "tournament";
    pub const TOURNAMENT_COUNTRY: &str = "tournament_country";
    pub const TOURNAMENT_ORGANIZERS_UIDS: &str = "tournament_organizers_uids";
    pub const TOURNAMENT_STATE: &str = "tournament_state";
    pub const TOURNAMENTS: &str = "tournaments";
    pub const TOURNAMENTS_COUNT: &str = "tournaments_count";
    pub const TP: &str = "tp";
    pub const TYPE: &str = "type";
    pub const TYPES: &str = "types";
    pub const UID: &str = "uid";
    pub const UNIQUE_NAME: &str = "unique_name";
    pub const UNRECOGNIZED_LINES: &str = "unrecognized_lines";
    pub const USER_UID: &str = "user_uid";
    pub const V5: &str = "v5";
    pub const VEKN: &str = "vekn";
    pub const VEKN_ID: &str = "vekn_id";
    pub const VP: &str = "vp";
    pub const VPS: &str = "vps";
    pub const WINNER: &str = "winner";
}

pub mod deck_object {
    pub const AUTHOR: &str = "author";
    pub const CARDS: &str = "cards";
    pub const COMMENTS: &str = "comments";
    pub const NAME: &str = "name";
    pub const PUBLIC: &str = "public";
    pub const UID: &str = "uid";
    pub const USER_UID: &str = "user_uid";
}

pub mod finals_table {
    pub const OVERRIDE: &str = "override";
    pub const SEATING: &str = "seating";
    pub const SEED_ORDER: &str = "seed_order";
    pub const STATE: &str = "state";
}

pub mod player {
    pub const DISPLAY_NAME: &str = "display_name";
    pub const FINALIST: &str = "finalist";
    pub const MISSING_DECKLIST: &str = "missing_decklist";
    pub const NON_COMPETING: &str = "non_competing";
    pub const PAYMENT_STATUS: &str = "payment_status";
    pub const RESULT: &str = "result";
    pub const STATE: &str = "state";
    pub const TOSS: &str = "toss";
    pub const USER_UID: &str = "user_uid";
}

pub mod promo_distribution {
    pub const PROMO_UID: &str = "promo_uid";
    pub const QTY: &str = "qty";
}

pub mod raffle_draw {
    pub const LABEL: &str = "label";
    pub const POOL: &str = "pool";
    pub const PRIZE_PROMO_UID: &str = "prize_promo_uid";
    pub const WINNERS: &str = "winners";
}

pub mod room {
    pub const COUNT: &str = "count";
    pub const NAME: &str = "name";
}

pub mod sanction {
    pub const DELETED_AT: &str = "deleted_at";
    pub const EXPIRES_AT: &str = "expires_at";
    pub const LEVEL: &str = "level";
    pub const LIFTED_AT: &str = "lifted_at";
    pub const ROUND_NUMBER: &str = "round_number";
    pub const USER_UID: &str = "user_uid";
}

pub mod score {
    pub const GW: &str = "gw";
    pub const TP: &str = "tp";
    pub const VP: &str = "vp";
}

pub mod score_override {
    pub const COMMENT: &str = "comment";
    pub const JUDGE_UID: &str = "judge_uid";
}

pub mod seat {
    pub const JUDGE_UID: &str = "judge_uid";
    pub const PLAYER_UID: &str = "player_uid";
    pub const RESULT: &str = "result";
}

pub mod standing {
    pub const DISQUALIFIED: &str = "disqualified";
    pub const FINALIST: &str = "finalist";
    pub const GW: &str = "gw";
    pub const NON_COMPETING: &str = "non_competing";
    /// Stored only by an importer told a player held no placement, and stamped
    /// over by `compute_final_standings` for the rows it derives the class for.
    pub const NO_SHOW: &str = "no_show";
    pub const TOSS: &str = "toss";
    pub const TP: &str = "tp";
    pub const USER_UID: &str = "user_uid";
    pub const VP: &str = "vp";
}

/// The display projection `compute_final_standings` stamps: derived, never
/// stored on a `Standing`.
pub mod standing_row {
    pub const FINALIST_POSITION: &str = "finalist_position";
}

pub mod table {
    pub const ORGANIZED_BY: &str = "organized_by";
    pub const OVERRIDE: &str = "override";
    pub const SEATING: &str = "seating";
    pub const STATE: &str = "state";
}

pub mod tournament {
    pub const ADDRESS: &str = "address";
    pub const COUNTRY: &str = "country";
    pub const DECKLIST_REQUIRED: &str = "decklist_required";
    pub const DECKLISTS_MODE: &str = "decklists_mode";
    pub const DESCRIPTION: &str = "description";
    pub const EXTERNAL_IDS: &str = "external_ids";
    pub const FINALS: &str = "finals";
    pub const FINALS_TIME: &str = "finals_time";
    pub const FINISH: &str = "finish";
    pub const FORMAT: &str = "format";
    pub const LEAGUE_UID: &str = "league_uid";
    pub const MAP_URL: &str = "map_url";
    pub const MAX_PLAYERS: &str = "max_players";
    pub const MAX_ROUNDS: &str = "max_rounds";
    pub const MODIFIED: &str = "modified";
    pub const MULTIDECK: &str = "multideck";
    pub const NAME: &str = "name";
    pub const ONLINE: &str = "online";
    pub const OPEN_ROUNDS: &str = "open_rounds";
    pub const ORGANIZERS_UIDS: &str = "organizers_uids";
    pub const PLAYERS: &str = "players";
    pub const PROMO_STOCK_SOURCE_UID: &str = "promo_stock_source_uid";
    pub const PROMOS_DISTRIBUTED: &str = "promos_distributed";
    pub const PROXIES: &str = "proxies";
    pub const RAFFLES: &str = "raffles";
    pub const RANK: &str = "rank";
    pub const REPORTED_PLAYER_COUNT: &str = "reported_player_count";
    pub const ROUND_TIME: &str = "round_time";
    pub const ROUNDS: &str = "rounds";
    pub const SELF_ORGANIZED_ROUNDS: &str = "self_organized_rounds";
    pub const STANDINGS: &str = "standings";
    pub const STANDINGS_MODE: &str = "standings_mode";
    pub const START: &str = "start";
    pub const STATE: &str = "state";
    pub const TABLE_ROOMS: &str = "table_rooms";
    pub const TIMEZONE: &str = "timezone";
    pub const UID: &str = "uid";
    pub const VENUE: &str = "venue";
    pub const VENUE_URL: &str = "venue_url";
    pub const WINNER: &str = "winner";
}

pub mod tournament_config {
    pub const ADDRESS: &str = "address";
    pub const COUNTRY: &str = "country";
    pub const DECKLIST_REQUIRED: &str = "decklist_required";
    pub const DECKLISTS_MODE: &str = "decklists_mode";
    pub const DESCRIPTION: &str = "description";
    pub const FINALS_TIME: &str = "finals_time";
    pub const FINISH: &str = "finish";
    pub const FORMAT: &str = "format";
    pub const LEAGUE_UID: &str = "league_uid";
    pub const MAP_URL: &str = "map_url";
    pub const MAX_PLAYERS: &str = "max_players";
    pub const MAX_ROUNDS: &str = "max_rounds";
    pub const MULTIDECK: &str = "multideck";
    pub const NAME: &str = "name";
    pub const ONLINE: &str = "online";
    pub const OPEN_ROUNDS: &str = "open_rounds";
    pub const PROXIES: &str = "proxies";
    pub const RANK: &str = "rank";
    pub const ROUND_TIME: &str = "round_time";
    pub const SELF_ORGANIZED_ROUNDS: &str = "self_organized_rounds";
    pub const STANDINGS_MODE: &str = "standings_mode";
    pub const START: &str = "start";
    pub const TABLE_ROOMS: &str = "table_rooms";
    pub const TIMEZONE: &str = "timezone";
    pub const UID: &str = "uid";
    pub const VENUE: &str = "venue";
    pub const VENUE_URL: &str = "venue_url";
}
