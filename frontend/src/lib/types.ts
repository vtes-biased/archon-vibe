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

export type SanctionLevel = "caution" | "warning" | "disqualification" | "suspension" | "probation" | "score_adjustment";

export type SanctionCategory =
  | "deck_problem"
  | "procedural"
  | "cheating"
  | "unsporting"
  | "other";

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
}

export interface Sanction extends BaseObject {
  user_uid: string; // Who received sanction
  issued_by_uid: string; // Who issued it
  tournament_uid: string | null; // If tournament-related
  level: SanctionLevel;
  category: SanctionCategory;
  description: string;
  issued_at: string;
  expires_at: string | null; // For suspensions/probation (null = permanent)
  lifted_at: string | null;
  lifted_by_uid: string | null;
}

// Tournament types

export type TournamentState = "Planned" | "Registration" | "Waiting" | "Playing" | "Finished";
export type TournamentFormat = "Standard" | "V5" | "Limited";
export type TournamentRank = "" | "National Championship" | "Continental Championship";
export type StandingsMode = "Private" | "Cutoff" | "Top 10" | "Public";
export type DeckListsMode = "Winner" | "Finalists" | "All";
export type PlayerState = "Registered" | "Checked-in" | "Playing" | "Finished";
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
