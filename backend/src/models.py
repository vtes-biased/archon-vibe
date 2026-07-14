"""Data models using msgspec.

WARNING: When modifying msgspec.Struct classes in this file,
always run the python-to-typescript-models rule to keep TypeScript
definitions in frontend/src/lib/types.ts synchronized.
"""

import json
import secrets
from datetime import datetime
from enum import StrEnum

import msgspec
from archon_engine import PyEngine


class ObjectType(StrEnum):
    """Sync object types stored in the unified objects table."""

    USER = "user"
    SANCTION = "sanction"
    TOURNAMENT = "tournament"
    DECK = "deck"
    LEAGUE = "league"


class DataLevel(StrEnum):
    """Data filtering level for SSE streaming."""

    PUBLIC = "public"  # Unauthenticated or non-member
    MEMBER = "member"  # Has vekn_id
    FULL = "full"  # IC, NC/Prince (same country), organizer


class Role(StrEnum):
    """Official VEKN roles."""

    IC = "IC"  # Inner Circle
    NC = "NC"  # National Coordinator
    PRINCE = "Prince"
    ETHICS = "Ethics"
    PTC = "PTC"  # Playtest Coordinator
    PT = "PT"  # Playtester
    RULEMONGER = "Rulemonger"
    JUDGE = "Judge"
    JUDGEKIN = "Judgekin"
    DEV = "DEV"  # Developer (can register OAuth clients)


class AuthMethodType(StrEnum):
    """Authentication method types."""

    EMAIL = "email"
    DISCORD = "discord"
    PASSKEY = "passkey"


class SanctionLevel(StrEnum):
    """Sanction severity levels."""

    CAUTION = "caution"
    WARNING = "warning"
    STANDINGS_ADJUSTMENT = "standings_adjustment"
    DISQUALIFICATION = "disqualification"
    SUSPENSION = "suspension"
    PROBATION = "probation"


class SanctionCategory(StrEnum):
    """Sanction categories aligned with VEKN Judges Guide v2."""

    PROCEDURAL_ERROR = "procedural_error"
    TOURNAMENT_ERROR = "tournament_error"
    UNSPORTSMANLIKE_CONDUCT = "unsportsmanlike_conduct"


class SanctionSubcategory(StrEnum):
    """Sanction subcategories from VEKN Judges Guide v2 Appendix I."""

    # Procedural Errors
    MISSED_MANDATORY_EFFECT = "missed_mandatory_effect"
    CARD_ACCESS_ERROR = "card_access_error"
    GAME_RULE_VIOLATION = "game_rule_violation"
    FAILURE_TO_MAINTAIN_GAME_STATE = "failure_to_maintain_game_state"
    # Tournament Errors
    ILLEGAL_DECKLIST = "illegal_decklist"
    ILLEGAL_MAIN_DECK_LEGAL_DECKLIST = "illegal_main_deck_legal_decklist"
    ILLEGAL_MAIN_DECK_NO_DECKLIST = "illegal_main_deck_no_decklist"
    OUTSIDE_ASSISTANCE = "outside_assistance"
    SLOW_PLAY = "slow_play"
    LIMITED_PROCEDURE_VIOLATION = "limited_procedure_violation"
    PUBLIC_INFO_MISCOMMUNICATION = "public_info_miscommunication"
    OBSCURING_GAME_STATE = "obscuring_game_state"
    MARKED_CARDS = "marked_cards"
    INSUFFICIENT_SHUFFLING = "insufficient_shuffling"
    # Unsportsmanlike Conduct
    MINOR = "minor"
    MAJOR = "major"
    AGGRESSIVE_BEHAVIOUR = "aggressive_behaviour"
    BRIBERY_AND_WAGERING = "bribery_and_wagering"
    THEFT_OF_TOURNAMENT_MATERIAL = "theft_of_tournament_material"
    STALLING = "stalling"
    CHEATING = "cheating"
    FRAUD = "fraud"
    COLLUSION = "collusion"
    HEALTH_AND_SAFETY_DISRUPTION = "health_and_safety_disruption"
    RAGE_QUITTING = "rage_quitting"
    FAILURE_TO_PLAY_TO_WIN = "failure_to_play_to_win"


# Judges-Guide tables come from the Rust engine (engine/src/sanctions.rs, the
# single source shared with the frontend WASM build and the bot's reference
# endpoint). The enum constructors raise at import if the engine data and the
# enums above drift, so a Judges-Guide revision missed here fails loudly.
_SANCTION_REFERENCE = json.loads(PyEngine().sanction_reference())

# Mapping: category → subcategories
SUBCATEGORIES_BY_CATEGORY: dict[SanctionCategory, list[SanctionSubcategory]] = {
    SanctionCategory(c["key"]): [
        SanctionSubcategory(s["key"]) for s in c["subcategories"]
    ]
    for c in _SANCTION_REFERENCE["categories"]
}

# Baseline penalties from Judges Guide v2
BASELINE_PENALTIES: dict[SanctionSubcategory, SanctionLevel] = {
    SanctionSubcategory(s["key"]): SanctionLevel(s["baseline"])
    for c in _SANCTION_REFERENCE["categories"]
    for s in c["subcategories"]
}


class CommunityLinkType(StrEnum):
    """Types of community links officials can share."""

    DISCORD = "discord"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    FORUM = "forum"
    FACEBOOK = "facebook"
    WEBSITE = "website"
    TWITCH = "twitch"
    YOUTUBE = "youtube"
    REDDIT = "reddit"
    INSTAGRAM = "instagram"
    BLOG = "blog"
    OTHER = "other"


class LinkModeration(msgspec.Struct, kw_only=True, frozen=True):
    """Moderation state for a community link, set by NC/Prince/IC."""

    status: str  # "hidden" | "promoted"
    by: str  # moderator user_uid
    at: datetime
    scope: str | None = None  # promoted only: "global" (IC) | "national" (NC)


class CommunityLink(msgspec.Struct, kw_only=True, frozen=True):
    """A community resource link shared by a member."""

    type: CommunityLinkType
    url: str
    label: str = ""
    # ISO 639-1 codes (e.g., ["en", "fr"]). Empty = shows under every filter.
    # The selectable list lives frontend-side (lib/data/languages.ts).
    languages: list[str] = msgspec.field(default_factory=list)
    moderation: LinkModeration | None = None


class TimerState(msgspec.Struct, kw_only=True):
    """Global round timer state. Clients compute countdown locally."""

    started_at: datetime | None = None  # When timer was started/resumed (UTC)
    elapsed_before_pause: float = 0.0  # Seconds accumulated in prior running periods
    paused: bool = True  # True = not running


class Announcement(msgspec.Struct, kw_only=True):
    """Organizer broadcast shown live to participants (online-only, member-projected)."""

    id: str  # uuid7 hex — client dedup/dismissal key (not a BaseObject uid)
    body: str
    created_at: datetime
    author_uid: str
    author_name: str = ""  # denormalized for display without a user lookup


class RatingCategory(StrEnum):
    CONSTRUCTED_ONLINE = "constructed_online"
    CONSTRUCTED_OFFLINE = "constructed_offline"
    LIMITED_ONLINE = "limited_online"
    LIMITED_OFFLINE = "limited_offline"


class TournamentRatingEntry(msgspec.Struct, kw_only=True, frozen=True):
    tournament_uid: str
    tournament_name: str
    date: str  # ISO date
    player_count: int
    rank: str  # TournamentRank value
    vp: float
    gw: int
    finalist_position: int  # 0=none, 1=winner, 2=runner-up
    points: int  # computed rating points


class CategoryRating(msgspec.Struct, kw_only=True):
    total: int = 0
    tournaments: list[TournamentRatingEntry] = msgspec.field(default_factory=list)


class BaseObject(msgspec.Struct, kw_only=True):
    """Base object structure for all domain objects."""

    uid: str  # UUID v7
    modified: datetime
    deleted_at: datetime | None = None  # Soft delete timestamp


class AuthMethod(msgspec.Struct, kw_only=True):
    """Authentication method linked to a user account.

    Supports multiple auth methods per user: email/password, Discord OAuth, Passkeys.
    """

    uid: str  # UUID v7
    modified: datetime
    user_uid: str  # FK → users
    method_type: AuthMethodType
    identifier: str  # email address, discord ID, or passkey credential ID
    credential_hash: str | None = None  # password hash or passkey public key
    verified: bool = False
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    sign_count: int = 0  # WebAuthn signature counter for passkeys


class User(BaseObject, kw_only=True):
    """User model representing a VEKN member or participant."""

    name: str
    country: str | None = None
    vekn_id: str | None = None  # Optional VEKN ID (non-members don't have one)
    city: str | None = None
    city_geoname_id: int | None = None
    state: str | None = None  # State/region
    nickname: str | None = None
    roles: list[Role] = msgspec.field(default_factory=list)

    # Profile
    avatar_path: str | None = None  # Server-stored compressed image path

    # Contact info (visible based on role-based access rules)
    contact_email: str | None = None
    contact_discord: str | None = None  # Discord handle
    discord_id: str | None = None  # Discord numeric user ID (from linked account)
    contact_phone: str | None = None
    phone_is_whatsapp: bool = False

    # Linked GitHub account (full projection only); attributes feedback issues.
    # github_login can go stale on rename/recycle — github_id is the stable anchor.
    github_login: str | None = None
    github_id: str | None = None

    # Community links (officials only: NC/Prince/IC)
    community_links: list[CommunityLink] = msgspec.field(default_factory=list)

    # Cooptation tracking (who granted VEKN membership)
    coopted_by: str | None = None  # user_uid of Prince/NC/IC who granted VEKN ID
    coopted_at: datetime | None = None

    # Deceased status (set/cleared by IC or same-country NC). NOT a soft-delete:
    # history and ratings are preserved. deceased_at presence is the flag.
    deceased_at: datetime | None = None
    deceased_by_uid: str | None = None  # who marked it (audit; full projection only)

    # VEKN sync tracking
    vekn_synced: bool = False  # True if user data came from VEKN API
    vekn_synced_at: datetime | None = None  # Last sync timestamp
    local_modifications: set[str] = msgspec.field(
        default_factory=set
    )  # Fields modified locally (won't be overwritten by sync)

    # VEKN prefix (for Prince/NC users, extracted from princeid/coordinatorid)
    vekn_prefix: str | None = None  # Used to infer coopted_by during sync

    # Calendar feed: URL-safe token for iCal subscription authentication
    calendar_token: str | None = None

    # Embedded rating data (merged from separate Rating objects)
    constructed_online: CategoryRating | None = None
    constructed_offline: CategoryRating | None = None
    limited_online: CategoryRating | None = None
    limited_offline: CategoryRating | None = None
    wins: list[str] = msgspec.field(
        default_factory=list
    )  # All-time IRL tournament UIDs won (HoF convention: online excluded)


class Score(msgspec.Struct, kw_only=True, frozen=True):
    gw: int = 0
    vp: float = 0.0
    tp: int = 0


class Sanction(BaseObject, kw_only=True):
    """Sanction issued to a user.

    Levels: caution, warning, standings_adjustment, disqualification (organizers/judges)
            suspension, probation (Ethics/IC only, optional expiry)

    Categories align with VEKN Judges Guide v2.
    Soft delete: deleted_at is set when expired or manually deleted.
    Hard delete happens 30 days after soft delete.
    """

    user_uid: str  # FK → users (who received sanction)
    issued_by_uid: str  # FK → users (who issued it)
    tournament_uid: str | None = None  # FK → tournaments (if tournament-related)
    level: SanctionLevel
    category: SanctionCategory
    subcategory: SanctionSubcategory | None = None
    round_number: int | None = None  # Which round the sanction applies to (0-indexed)
    description: str
    issued_at: datetime
    expires_at: datetime | None = None  # For suspensions/probation (None = permanent)
    lifted_at: datetime | None = None
    lifted_by_uid: str | None = None


class LeagueKind(StrEnum):
    LEAGUE = "League"
    META = "Meta-League"


class LeagueStandingsMode(StrEnum):
    RTP = "RTP"  # Rating points (VEKN formula)
    SCORE = "Score"  # GW/VP/TP from prelims only (finals subtracted)
    GP = "GP"  # Grand Prix position-based points


class League(BaseObject, kw_only=True):
    """League grouping multiple tournaments with aggregated standings."""

    name: str
    kind: LeagueKind = LeagueKind.LEAGUE
    standings_mode: LeagueStandingsMode = LeagueStandingsMode.RTP
    format: str | None = None  # TournamentFormat value or None = any
    country: str | None = None  # None = worldwide
    start: datetime | None = None
    finish: datetime | None = None  # None = ongoing
    description: str = ""
    organizers_uids: list[str] = msgspec.field(default_factory=list)
    parent_uid: str | None = None  # FK → leagues (child of meta-league)


class TournamentState(StrEnum):
    PLANNED = "Planned"
    REGISTRATION = "Registration"
    WAITING = "Waiting"
    PLAYING = "Playing"
    FINISHED = "Finished"


class TournamentFormat(StrEnum):
    Standard = "Standard"
    V5 = "V5"
    Limited = "Limited"


class TournamentRank(StrEnum):
    BASIC = ""
    NC = "National Championship"
    CC = "Continental Championship"


class TournamentMinimal(BaseObject, kw_only=True):
    name: str
    format: TournamentFormat = TournamentFormat.Standard
    rank: TournamentRank = TournamentRank.BASIC
    online: bool = False
    start: datetime | None = None
    finish: datetime | None = None
    timezone: str = "UTC"
    country: str | None = None
    league_uid: str | None = None  # FK → leagues
    state: TournamentState = TournamentState.PLANNED


class StandingsMode(StrEnum):
    PRIVATE = "Private"  # Default
    CUTOFF = "Cutoff"  # Cutoff to make top 5
    TOP_10 = "Top 10"  # Top 10 players
    PUBLIC = "Public"  # All players


class DeckListsMode(StrEnum):
    WINNER = "Winner"  # Default
    FINALISTS = "Finalists"
    ALL = "All"


class Room(msgspec.Struct, kw_only=True):
    name: str
    count: int


class TournamentConfig(TournamentMinimal, kw_only=True):
    organizers_uids: list[str] = msgspec.field(default_factory=list)  # FK → users
    venue: str = ""
    venue_url: str = ""
    address: str = ""
    map_url: str = ""
    proxies: bool = False
    multideck: bool = False
    decklist_required: bool = False
    description: str = ""
    standings_mode: StandingsMode = StandingsMode.PRIVATE
    decklists_mode: DeckListsMode = DeckListsMode.WINNER
    max_rounds: int = 0
    # Soft registration cap (0 = none): the UI warns past it and shows N/cap.
    # Never blocks — no hard cap, no waitlist (venue seat limits are advisory).
    max_players: int = 0
    # House (non-VEKN) open-rounds event: per-player cap from a shared pool. Never
    # pushed to VEKN, never counted toward ratings/RTP. Decoupled from max_rounds
    # because the VEKN-push build forces max_rounds 2-4 on every (standard) tournament.
    open_rounds: bool = False
    self_organized_rounds: bool = (
        False  # open rounds: registered players may seat their own pod
    )
    table_rooms: list[Room] = msgspec.field(default_factory=list)
    # Timer config
    round_time: int = 0  # Round duration in seconds (0 = no timer)
    finals_time: int = 0  # Finals duration in seconds (0 = use round_time)


class PlayerState(StrEnum):
    REGISTERED = "Registered"
    CHECKED_IN = "Checked-in"
    PLAYING = "Playing"
    COMPLETED = "Completed"  # open rounds: reached per-player cap; done with prelims, finals-eligible
    FINISHED = "Finished"
    DISQUALIFIED = "Disqualified"


class PaymentStatus(StrEnum):
    PENDING = "Pending"
    PAID = "Paid"
    REFUNDED = "Refunded"
    CANCELLED = "Cancelled"


class Player(msgspec.Struct, kw_only=True):
    user_uid: str | None = None  # FK → users
    state: PlayerState = PlayerState.REGISTERED
    payment_status: PaymentStatus = PaymentStatus.PENDING
    toss: int = 0  # non-zero when draws for seeding finals
    result: Score = (
        Score()
    )  # aggregated score (used when no round detail, e.g. VEKN sync)
    finalist: bool = False  # true if player reached the finals table
    display_name: str | None = None  # Discord guild nickname (per-tournament)
    non_competing: bool = (
        False  # proxy: non-competing official stood in; excluded from rank/RTP/finals
    )


class Seat(msgspec.Struct, kw_only=True):
    player_uid: str  # FK → users
    result: Score = Score()
    judge_uid: str = ""  # FK → users (if a judge sets the score, players cannot modify)


class TableState(StrEnum):
    FINISHED = "Finished"
    IN_PROGRESS = "In Progress"
    INVALID = "Invalid"
    CANCELLED = "Cancelled"  # soft-cancelled round (slot preserved; excluded from cap/standings)


class ScoreOverride(msgspec.Struct, kw_only=True):
    judge_uid: str  # FK → users
    comment: str = ""


class Table(msgspec.Struct, kw_only=True):
    seating: list[Seat]
    state: TableState = TableState.IN_PROGRESS
    override: ScoreOverride | None = None
    organized_by: str | None = (
        None  # user_uid of the player who self-organized this round (#274)
    )


class FinalsTable(Table, kw_only=True):
    seating: list[Seat]
    seed_order: list[str]


class DeckObject(BaseObject, kw_only=True):
    """Standalone deck object extracted from Tournament.decks for separate sync."""

    tournament_uid: str
    user_uid: str
    round: int | None = None
    name: str = ""
    author: str = ""
    comments: str = ""
    cards: dict[str, int] = msgspec.field(default_factory=dict)
    attribution: str | None = None
    public: bool = (
        False  # Visible to non-owner members (set by engine based on decklists_mode)
    )


class Standing(msgspec.Struct, kw_only=True, frozen=True):
    """Aggregated standings entry. Computed by Rust engine on FinishRound/FinishTournament.
    Also populated directly by VEKN sync (no rounds data in that case)."""

    user_uid: str
    gw: float = 0.0
    vp: float = 0.0
    tp: int = 0
    toss: int = 0
    finalist: bool = False
    disqualified: bool = False  # forfeited score (zeroed), sorted last, no RTP
    non_competing: bool = (
        False  # proxy: excluded from rank/RTP/finals, score NOT zeroed
    )


class RafflePool(StrEnum):
    ALL_PLAYERS = "AllPlayers"
    NON_FINALISTS = "NonFinalists"
    GAME_WINNERS = "GameWinners"
    NO_GAME_WIN = "NoGameWin"
    NO_VICTORY_POINT = "NoVictoryPoint"


class RaffleDraw(msgspec.Struct, kw_only=True):
    label: str
    pool: RafflePool
    winners: list[str] = msgspec.field(default_factory=list)


class Tournament(TournamentConfig, kw_only=True):
    # Hero / social-share image. Versioned URL (?v=<epoch-ms>) so a re-upload
    # produces a new URL — SSE carries it and every client refetches at once,
    # while each version stays browser-cacheable. Bytes live in the banners
    # table; this is just the path. See routes/tournaments.py banner endpoints.
    banner_path: str | None = None
    external_ids: dict[str, str] = msgspec.field(default_factory=dict)  # platform: id
    checkin_code: str = msgspec.field(default_factory=lambda: secrets.token_urlsafe(16))
    players: list[Player] = msgspec.field(default_factory=list)
    rounds: list[list[Table]] = msgspec.field(default_factory=list)
    finals: FinalsTable | None = None
    winner: str = ""
    # Aggregated standings — computed by engine on FinishRound/FinishTournament,
    # or populated by VEKN sync. NOT cleared if rounds are empty.
    standings: list[Standing] = msgspec.field(default_factory=list)
    raffles: list[RaffleDraw] = msgspec.field(default_factory=list)
    # VEKN push tracking
    vekn_pushed_at: datetime | None = None  # When results were pushed to vekn.net
    # Results diverged after the push (reopen or result-affecting edit). The push
    # is write-once — corrections never reach vekn.net via API, so this is sticky;
    # only a manual admin fix (there and here) clears it.
    vekn_results_stale: bool = False
    # Offline mode: device-level locking for offline tournament management
    offline_mode: bool = False
    offline_device_id: str = (
        ""  # Device identifier (localStorage UUID) that holds the lock
    )
    offline_user_uid: str = ""  # User UID of organizer who locked it (for display)
    offline_since: datetime | None = None  # When tournament went offline
    # Timer state (online-only, not processed by Rust engine)
    timer: TimerState = msgspec.field(default_factory=TimerState)
    table_extra_time: dict[str, int] = msgspec.field(
        default_factory=dict
    )  # table_idx → extra seconds
    # Live organizer announcements (online-only, member-projected, capped)
    announcements: list[Announcement] = msgspec.field(default_factory=list)


# OAuth 2.0 models


class OAuthScope(StrEnum):
    PROFILE_READ = "profile:read"
    USER_IMPERSONATE = "user:impersonate"


class OAuthClient(BaseObject, kw_only=True):
    """Registered third-party OAuth application."""

    name: str
    client_id: str  # 32-char random
    client_secret_hash: str  # Argon2 hash
    redirect_uris: list[str]
    scopes: list[OAuthScope]
    created_by_uid: str  # FK → users (DEV user who registered it)
    active: bool = True


class OAuthAuthorizationCode(BaseObject, kw_only=True):
    """Short-lived authorization code (60s TTL, single use)."""

    code: str  # 64-char random
    client_id: str
    user_uid: str
    redirect_uri: str
    scopes: list[OAuthScope]
    code_challenge: str  # S256 PKCE challenge
    expires_at: datetime
    used: bool = False


class OAuthToken(BaseObject, kw_only=True):
    """Token record for revocation tracking."""

    token_jti: str  # JWT ID
    client_id: str
    user_uid: str
    scopes: list[OAuthScope]
    token_type: str  # "access" or "refresh"
    expires_at: datetime
    revoked: bool = False
    parent_token_uid: str | None = None  # For refresh chain tracking


class OAuthConsent(BaseObject, kw_only=True):
    """Remembered user consent for a client+scopes combination."""

    user_uid: str
    client_id: str
    scopes: list[OAuthScope]
