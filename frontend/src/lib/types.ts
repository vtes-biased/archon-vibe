/**
 * Shared TypeScript type definitions.
 *
 * Keep synchronized with backend/src/models.py using python-to-typescript-models rule.
 */

export type DataLevel = "public" | "member" | "full";

export type Role =
  | "IC" // Inner Circle (app admins)
  | "NC" // National Coordinator
  | "Prince"
  | "Ethics"
  | "PTC" // Playtest Coordinator
  | "PT" // Playtester
  | "Rulemonger"
  | "Judge"
  | "Judgekin"
  | "DEV"; // Developer (can register OAuth clients)

export type AuthMethodType = "email" | "discord" | "passkey";

export type SanctionLevel = "caution" | "warning" | "standings_adjustment" | "disqualification" | "suspension" | "probation";

export type SanctionCategory =
  | "procedural_error"
  | "tournament_error"
  | "unsportsmanlike_conduct";

export type SanctionSubcategory =
  // Procedural Errors
  | "missed_mandatory_effect"
  | "card_access_error"
  | "game_rule_violation"
  | "failure_to_maintain_game_state"
  // Tournament Errors
  | "illegal_decklist"
  | "illegal_main_deck_legal_decklist"
  | "illegal_main_deck_no_decklist"
  | "outside_assistance"
  | "slow_play"
  | "limited_procedure_violation"
  | "public_info_miscommunication"
  | "obscuring_game_state"
  | "marked_cards"
  | "insufficient_shuffling"
  // Unsportsmanlike Conduct
  | "minor"
  | "major"
  | "aggressive_behaviour"
  | "bribery_and_wagering"
  | "theft_of_tournament_material"
  | "stalling"
  | "cheating"
  | "fraud"
  | "collusion"
  | "health_and_safety_disruption"
  | "rage_quitting"
  | "failure_to_play_to_win";

export const SUBCATEGORIES_BY_CATEGORY: Record<SanctionCategory, SanctionSubcategory[]> = {
  procedural_error: [
    "missed_mandatory_effect",
    "card_access_error",
    "game_rule_violation",
    "failure_to_maintain_game_state",
  ],
  tournament_error: [
    "illegal_decklist",
    "illegal_main_deck_legal_decklist",
    "illegal_main_deck_no_decklist",
    "outside_assistance",
    "slow_play",
    "limited_procedure_violation",
    "public_info_miscommunication",
    "obscuring_game_state",
    "marked_cards",
    "insufficient_shuffling",
  ],
  unsportsmanlike_conduct: [
    "minor",
    "major",
    "aggressive_behaviour",
    "bribery_and_wagering",
    "theft_of_tournament_material",
    "stalling",
    "cheating",
    "fraud",
    "collusion",
    "health_and_safety_disruption",
    "rage_quitting",
    "failure_to_play_to_win",
  ],
};

export const BASELINE_PENALTIES: Record<SanctionSubcategory, SanctionLevel> = {
  // Procedural Errors
  missed_mandatory_effect: "caution",
  card_access_error: "warning",
  game_rule_violation: "warning",
  failure_to_maintain_game_state: "warning",
  // Tournament Errors
  illegal_decklist: "warning",
  illegal_main_deck_legal_decklist: "standings_adjustment",
  illegal_main_deck_no_decklist: "disqualification",
  outside_assistance: "warning",
  slow_play: "caution",
  limited_procedure_violation: "warning",
  public_info_miscommunication: "warning",
  obscuring_game_state: "warning",
  marked_cards: "warning",
  insufficient_shuffling: "caution",
  // Unsportsmanlike Conduct
  minor: "warning",
  major: "standings_adjustment",
  aggressive_behaviour: "disqualification",
  bribery_and_wagering: "disqualification",
  theft_of_tournament_material: "disqualification",
  stalling: "standings_adjustment",
  cheating: "disqualification",
  fraud: "disqualification",
  collusion: "disqualification",
  health_and_safety_disruption: "disqualification",
  rage_quitting: "standings_adjustment",
  failure_to_play_to_win: "standings_adjustment",
};

export const ESCALATION_SEQUENCE: SanctionLevel[] = [
  "caution", "caution", "warning", "warning",
  "standings_adjustment", "standings_adjustment", "disqualification",
];

export interface BaseObject {
  uid: string; // UUID v7
  modified: string; // ISO datetime string
  deleted_at?: string | null; // Soft delete timestamp
}

export interface AuthMethod extends BaseObject {
  user_uid: string;
  method_type: AuthMethodType;
  identifier: string; // email address, discord ID, or passkey credential ID
  credential_hash: string | null; // password hash or passkey public key
  verified: boolean;
  created_at: string | null;
  last_used_at: string | null;
}

export interface User extends BaseObject {
  name: string;
  country: string | null; // ISO 3166-1 alpha-2 country code
  vekn_id?: string | null; // Optional VEKN ID
  city?: string | null;
  state?: string | null; // State/region
  nickname?: string | null;
  roles: Role[];

  // Profile
  avatar_path?: string | null; // Server-stored compressed image path

  // Contact info (visible based on role-based access rules)
  contact_email?: string | null;
  contact_discord?: string | null; // Discord handle
  contact_phone?: string | null; // WhatsApp/phone

  // Cooptation tracking (who granted VEKN membership)
  coopted_by?: string | null; // user_uid of Prince/NC/IC who granted VEKN ID
  coopted_at?: string | null;

  // VEKN sync tracking
  vekn_synced?: boolean;
  vekn_synced_at?: string | null;
  local_modifications?: string[];

  // VEKN prefix (for Prince/NC users, extracted from princeid/coordinatorid)
  vekn_prefix?: string | null;

  // Calendar feed token (private, only visible via /auth/me)
  calendar_token?: string | null;
}

export interface Sanction extends BaseObject {
  user_uid: string; // Who received sanction
  issued_by_uid: string; // Who issued it
  tournament_uid: string | null; // If tournament-related
  level: SanctionLevel;
  category: SanctionCategory;
  subcategory?: SanctionSubcategory | null;
  round_number?: number | null; // Which round the sanction applies to (0-indexed)
  description: string;
  issued_at: string;
  expires_at: string | null; // For suspensions/probation (null = permanent)
  lifted_at: string | null;
  lifted_by_uid: string | null;
}

// League types

export type LeagueKind = "League" | "Meta-League";
export type LeagueStandingsMode = "RTP" | "Score" | "GP";

export interface League extends BaseObject {
  name: string;
  kind: LeagueKind;
  standings_mode: LeagueStandingsMode;
  format: string | null; // TournamentFormat value or null = any
  online: boolean;
  country: string | null; // null = worldwide
  start: string | null;
  finish: string | null; // null = ongoing
  timezone: string;
  description: string;
  organizers_uids: string[];
  parent_uid: string | null; // FK → leagues (child of meta-league)
  allow_no_finals: boolean;
}

// Tournament types

export type TournamentState = "Planned" | "Registration" | "Waiting" | "Playing" | "Finished";
export type TournamentFormat = "Standard" | "V5" | "Limited";
export type TournamentRank = "" | "National Championship" | "Continental Championship";
export type StandingsMode = "Private" | "Cutoff" | "Top 10" | "Public";
export type DeckListsMode = "Winner" | "Finalists" | "All";
export type PlayerState = "Registered" | "Checked-in" | "Playing" | "Finished" | "Disqualified";
export type PaymentStatus = "Pending" | "Paid" | "Refunded" | "Cancelled";
export type TableState = "Finished" | "In Progress" | "Invalid";

export interface Score {
  gw: number;
  vp: number;
  tp: number;
}

export interface Player {
  user_uid: string | null;
  state: PlayerState;
  payment_status: PaymentStatus;
  toss: number;
  result: Score;
  finalist: boolean;
}

export interface Standing {
  user_uid: string;
  gw: number;
  vp: number;
  tp: number;
  toss: number;
  finalist: boolean;
}

export interface Seat {
  player_uid: string;
  result: Score;
  judge_uid: string;
}

export interface ScoreOverride {
  judge_uid: string;
  comment: string;
}

export interface Table {
  seating: Seat[];
  state: TableState;
  override: ScoreOverride | null;
}

export interface FinalsTable extends Table {
  seed_order: string[];
}

export interface Deck {
  round: number | null;
  name: string;
  author: string;
  comments: string;
  cards: Record<string, number>;
  attribution?: string | null; // null = anonymous, vekn_id = attributed to member
}

/**
 * Unified Tournament type. Fields are optional based on the data level
 * received from the backend:
 * - public: uid, modified, name, format, rank, online, start, finish, timezone, country, state
 * - member: adds config fields, players, standings, my_tables, decks (filtered)
 * - full: everything including rounds, finals, checkin_code
 */
export interface Tournament extends BaseObject {
  name: string;
  format: TournamentFormat;
  rank: TournamentRank;
  online: boolean;
  start: string | null;
  finish: string | null;
  timezone: string;
  country: string | null;
  league_uid?: string | null;
  state: TournamentState;

  // Config fields (member+)
  organizers_uids?: string[];
  venue?: string;
  venue_url?: string;
  address?: string;
  map_url?: string;
  proxies?: boolean;
  multideck?: boolean;
  decklist_required?: boolean;
  description?: string;
  standings_mode?: StandingsMode;
  decklists_mode?: DeckListsMode;
  max_rounds?: number;

  // Full data (varies by level)
  external_ids?: Record<string, string>;
  checkin_code?: string;
  players?: Player[];
  decks?: Record<string, Deck[]>;
  rounds?: Table[][];
  finals?: FinalsTable | null;
  winner?: string;
  standings?: Standing[];
  my_tables?: Table[]; // Per-viewer: tables where the viewer sat (NOT stored in DB)

  // Offline mode
  offline_mode?: boolean;
  offline_device_id?: string;
  offline_user_uid?: string;
  offline_since?: string | null;
}

/** Player added during offline mode, pending reconciliation with server. */
export interface OfflinePlayer {
  temp_uid: string;   // Client-generated UUID
  name: string;
  vekn_id?: string;
  email?: string;
}

/**
 * TournamentConfig — used as payload type for create/update API calls only.
 * NOT stored in IndexedDB.
 */
export interface TournamentConfig {
  name: string;
  format: TournamentFormat;
  rank: TournamentRank;
  online: boolean;
  start: string | null;
  finish: string | null;
  timezone: string;
  country: string | null;
  league_uid: string | null;
  state: TournamentState;
  organizers_uids: string[];
  venue: string;
  venue_url: string;
  address: string;
  map_url: string;
  proxies: boolean;
  multideck: boolean;
  decklist_required: boolean;
  description: string;
  standings_mode: StandingsMode;
  decklists_mode: DeckListsMode;
  max_rounds: number;
}

// Rating types

export type RatingCategory = "constructed_online" | "constructed_offline" | "limited_online" | "limited_offline";

export interface TournamentRatingEntry {
  tournament_uid: string;
  tournament_name: string;
  date: string; // ISO date
  player_count: number;
  rank: TournamentRank;
  vp: number;
  gw: number;
  finalist_position: number; // 0=none, 1=winner, 2=runner-up
  points: number;
}

export interface CategoryRating {
  total: number;
  tournaments: TournamentRatingEntry[];
}

export interface Rating extends BaseObject {
  user_uid: string;
  country: string | null;
  constructed_online: CategoryRating | null;
  constructed_offline: CategoryRating | null;
  limited_online: CategoryRating | null;
  limited_offline: CategoryRating | null;
  wins: string[]; // All-time tournament UIDs won
}

// Card types (VTES card database)
export interface VtesCard {
  id: number;
  name: string;
  printed_name: string;
  kind: 'crypt' | 'library';
  types: string[];
  disciplines: string[];
  clan: string;
  group: string;
  capacity: number;
  adv: boolean;
  banned: string;
  sets: string[];
  name_variants: string[];
}

// GeoNames types
export type Continent = "AF" | "AN" | "AS" | "EU" | "NA" | "OC" | "SA";

export interface Country {
  iso_code: string;    // ISO-3166 2-letter code
  iso3: string;        // ISO-3166 3-letter code
  name: string;
  capital: string;
  continent: string;   // Continent code
}

export interface City {
  geoname_id: number;
  name: string;
  ascii_name: string;
  country_code: string;
  latitude: number;
  longitude: number;
  population: number;
}
