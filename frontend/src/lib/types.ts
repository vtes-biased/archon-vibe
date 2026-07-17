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


export type CommunityLinkType = "discord" | "telegram" | "whatsapp" | "forum" | "facebook" | "website" | "twitch" | "youtube" | "reddit" | "instagram" | "blog" | "other";

export interface LinkModeration {
  status: "hidden" | "promoted";
  by: string; // moderator user_uid
  at: string; // ISO datetime
  scope?: "global" | "national" | null; // promoted only: IC | NC pin level
}

export interface CommunityLink {
  type: CommunityLinkType;
  url: string;
  label: string;
  languages?: string[]; // ISO 639-1 codes; empty/absent = shows under every filter
  moderation?: LinkModeration | null;
}

export type SanctionLevel = "caution" | "warning" | "standings_adjustment" | "disqualification" | "suspension" | "probation";

export type SanctionCategory =
  | "procedural_error"
  | "tournament_error"
  | "unsportsmanlike_conduct";

// Category/subcategory vocabulary mirrors engine/src/sanctions.rs, which owns
// the Judges-Guide tables (grouping, baselines, escalation) — read them at
// runtime via getSanctionReference() in $lib/engine.
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

export interface BaseObject {
  uid: string; // UUID v7
  modified: string; // ISO datetime string
  deleted_at?: string | null; // Soft delete timestamp
}

export interface User extends BaseObject {
  name: string;
  country: string | null; // ISO 3166-1 alpha-2 country code
  vekn_id?: string | null; // Optional VEKN ID
  city?: string | null;
  city_geoname_id?: number | null;
  state?: string | null; // State/region
  nickname?: string | null;
  roles: Role[];

  // Profile
  avatar_path?: string | null; // Server-stored compressed image path

  // Contact info (visible based on role-based access rules)
  contact_email?: string | null;
  contact_discord?: string | null; // Discord handle
  discord_id?: string | null; // Discord numeric user ID (from linked account)
  contact_phone?: string | null;
  phone_is_whatsapp?: boolean;

  // Linked GitHub account (full projection only) — attributes feedback issues.
  github_login?: string | null; // GitHub @handle
  github_id?: string | null; // GitHub numeric user id

  // Community links (officials only)
  community_links?: CommunityLink[];

  // Cooptation tracking (who granted VEKN membership)
  coopted_by?: string | null; // user_uid of Prince/NC/IC who granted VEKN ID
  coopted_at?: string | null;

  // Deceased status (set/cleared by IC or same-country NC). Not a soft-delete:
  // history/ratings preserved. Member projection carries deceased_at only.
  deceased_at?: string | null;
  deceased_by_uid?: string | null; // full projection only

  // VEKN sync tracking
  vekn_synced?: boolean;
  vekn_synced_at?: string | null;
  local_modifications?: string[];

  // VEKN prefix (for Prince/NC users, extracted from princeid/coordinatorid)
  vekn_prefix?: string | null;

  // Calendar feed token (private, only visible via /auth/me)
  calendar_token?: string | null;

  // Embedded rating data (merged from separate Rating objects)
  constructed_online?: CategoryRating | null;
  constructed_offline?: CategoryRating | null;
  limited_online?: CategoryRating | null;
  limited_offline?: CategoryRating | null;
  wins?: string[]; // All-time IRL tournament UIDs won (HoF convention: online excluded)
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
  country: string | null; // null = worldwide
  start: string | null;
  finish: string | null; // null = ongoing
  description: string;
  organizers_uids: string[];
  parent_uid: string | null; // FK → leagues (child of meta-league)
  // Same-country Princes may attach their own tournaments (attach-only).
  // Optional: rows synced before the field existed lack it (treat as false).
  open_to_country_princes?: boolean;
}

// Promotional items (BCP promo cards/packs)

export type PromoKind = "card" | "pack" | "other";

/** Server-computed inventory aggregate for one holder (promo ledger). */
export interface PromoHolding {
  assigned: number;
  remaining: number;
}

export interface Promo extends BaseObject {
  name: string;
  kind: PromoKind;
  description: string;
  release_date: string | null;
  // Retirement flag — retired promos stay synced so historical rows resolve; UI filters.
  active: boolean;
  // Distribution gating (UX-only, organizer picker filter): empty = unrestricted.
  allowed_ranks: TournamentRank[];
  league_uids: string[];
  image_path: string | null;
  // holder_uid → aggregate; present only in the full projection (officials).
  holdings?: Record<string, PromoHolding>;
}

// Tournament types

export type TournamentState = "Planned" | "Registration" | "Waiting" | "Playing" | "Finished";
export type TournamentFormat = "Standard" | "V5" | "Limited";
export type TournamentRank = "" | "National Championship" | "Continental Championship";
export type StandingsMode = "Private" | "Cutoff" | "Top 10" | "Public";
export type DeckListsMode = "Winner" | "Finalists" | "All";

export interface TimerState {
  started_at: string | null;     // ISO datetime
  elapsed_before_pause: number;  // seconds
  paused: boolean;
}
export interface Announcement {
  id: string;            // uuid7 hex — dedup/dismissal key
  body: string;
  created_at: string;    // ISO datetime
  author_uid: string;
  author_name: string;
}
export type PlayerState = "Registered" | "Checked-in" | "Playing" | "Completed" | "Finished" | "Disqualified";
export type PaymentStatus = "Pending" | "Paid" | "Refunded" | "Cancelled";
export type TableState = "Finished" | "In Progress" | "Invalid" | "Cancelled";

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
  display_name?: string | null; // Discord guild nickname (per-tournament)
  non_competing?: boolean; // proxy: non-competing official stood in; excluded from rank/RTP/finals
}

export interface Standing {
  user_uid: string;
  gw: number;
  vp: number;
  tp: number;
  toss: number;
  finalist: boolean;
  disqualified?: boolean;
  non_competing?: boolean;
}

export type RafflePool = "AllPlayers" | "NonFinalists" | "GameWinners" | "NoGameWin" | "NoVictoryPoint";

export interface RaffleDraw {
  label: string;
  pool: RafflePool;
  winners: string[];
  // Optional promo-catalog prize; display-only
  prize_promo_uid?: string | null;
}

export interface PromoDistribution {
  promo_uid: string;
  qty: number;
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
  organized_by?: string; // user_uid of the player who self-organized this round (#274)
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
 * Unified Tournament type. Fields are optional based on the data level:
 * - public: uid, modified, name, format, rank, online, start, finish, timezone, country, state
 * - member: everything except checkin_code and VEKN push bookkeeping
 * - full: everything
 * Decks are now separate DeckObject entities (not embedded in tournament).
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
  banner_path?: string | null;  // versioned hero / og:image URL (public)

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
  max_players?: number; // soft registration cap (0 = none): warn-only, never blocks
  open_rounds?: boolean; // non-VEKN house format: per-player cap, not pushed to VEKN, not ranked
  self_organized_rounds?: boolean; // open-rounds: let registered players seat their own pod (#274)
  table_rooms?: { name: string; count: number }[];

  // Full data (varies by level)
  external_ids?: Record<string, string>;
  vekn_pushed_at?: string | null;
  vekn_results_stale?: boolean; // results diverged after the write-once VEKN push
  // Last TWDA auto-submission outcome (organizer projection only)
  twda_status?: {
    outcome: "submitted" | "skipped" | "failed";
    reason: string; // skip reason code → twda_reason_* i18n keys
    pr_url: string;
    at: string | null;
  } | null;
  checkin_code?: string;
  players?: Player[];
  rounds?: Table[][];
  finals?: FinalsTable | null;
  winner?: string;
  standings?: Standing[];
  raffles?: RaffleDraw[];
  // Promo distribution report (organizer-entered, replace-whole-list, member-visible)
  promos_distributed?: PromoDistribution[];
  promo_stock_source_uid?: string;
  // Offline mode
  offline_mode?: boolean;
  offline_device_id?: string;
  offline_user_uid?: string;
  offline_since?: string | null;

  // Timer (online-only)
  round_time?: number;
  finals_time?: number;
  timer?: TimerState;
  table_extra_time?: Record<string, number>;  // table_idx → extra seconds
  announcements?: Announcement[];  // live organizer broadcasts (online-only)
}

/** Player added during offline mode, pending reconciliation with server. */
export interface OfflinePlayer {
  temp_uid: string;   // Client-generated UUID
  name: string;
  vekn_id?: string;
  email?: string;
}

// Standalone deck object (synced separately from tournament)
export interface DeckObject extends BaseObject {
  tournament_uid: string;
  user_uid: string;
  round: number | null;
  name: string;
  author: string;
  comments: string;
  cards: Record<string, number>;
  attribution?: string | null;
  public: boolean;
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

// Card types (VTES card database)
export interface VtesCard {
  id: number;
  /** Bare name, for display (group/advanced shown as separate badges). */
  printed_name: string;
  /** Minimal disambiguator (bare for most; later groups/advanced suffixed); text export. */
  unique_name: string;
  /** Always group/advanced suffixed. */
  full_name: string;
  img: string;
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
