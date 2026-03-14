"""Data models using msgspec.

WARNING: When modifying msgspec.Struct classes in this file,
always run the python-to-typescript-models rule to keep TypeScript
definitions in frontend/src/lib/types.ts synchronized.
"""

import secrets
from datetime import datetime
from enum import StrEnum

import msgspec


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


# Mapping: subcategory → parent category
SUBCATEGORIES_BY_CATEGORY: dict[SanctionCategory, list[SanctionSubcategory]] = {
    SanctionCategory.PROCEDURAL_ERROR: [
        SanctionSubcategory.MISSED_MANDATORY_EFFECT,
        SanctionSubcategory.CARD_ACCESS_ERROR,
        SanctionSubcategory.GAME_RULE_VIOLATION,
        SanctionSubcategory.FAILURE_TO_MAINTAIN_GAME_STATE,
    ],
    SanctionCategory.TOURNAMENT_ERROR: [
        SanctionSubcategory.ILLEGAL_DECKLIST,
        SanctionSubcategory.ILLEGAL_MAIN_DECK_LEGAL_DECKLIST,
        SanctionSubcategory.ILLEGAL_MAIN_DECK_NO_DECKLIST,
        SanctionSubcategory.OUTSIDE_ASSISTANCE,
        SanctionSubcategory.SLOW_PLAY,
        SanctionSubcategory.LIMITED_PROCEDURE_VIOLATION,
        SanctionSubcategory.PUBLIC_INFO_MISCOMMUNICATION,
        SanctionSubcategory.OBSCURING_GAME_STATE,
        SanctionSubcategory.MARKED_CARDS,
        SanctionSubcategory.INSUFFICIENT_SHUFFLING,
    ],
    SanctionCategory.UNSPORTSMANLIKE_CONDUCT: [
        SanctionSubcategory.MINOR,
        SanctionSubcategory.MAJOR,
        SanctionSubcategory.AGGRESSIVE_BEHAVIOUR,
        SanctionSubcategory.BRIBERY_AND_WAGERING,
        SanctionSubcategory.THEFT_OF_TOURNAMENT_MATERIAL,
        SanctionSubcategory.STALLING,
        SanctionSubcategory.CHEATING,
        SanctionSubcategory.FRAUD,
        SanctionSubcategory.COLLUSION,
        SanctionSubcategory.HEALTH_AND_SAFETY_DISRUPTION,
        SanctionSubcategory.RAGE_QUITTING,
        SanctionSubcategory.FAILURE_TO_PLAY_TO_WIN,
    ],
}

# Baseline penalties from Judges Guide v2
BASELINE_PENALTIES: dict[SanctionSubcategory, SanctionLevel] = {
    # Procedural Errors (v2 §2)
    SanctionSubcategory.MISSED_MANDATORY_EFFECT: SanctionLevel.CAUTION,
    SanctionSubcategory.CARD_ACCESS_ERROR: SanctionLevel.CAUTION,
    SanctionSubcategory.GAME_RULE_VIOLATION: SanctionLevel.CAUTION,
    SanctionSubcategory.FAILURE_TO_MAINTAIN_GAME_STATE: SanctionLevel.STANDINGS_ADJUSTMENT,
    # Tournament Errors (v2 §3)
    SanctionSubcategory.ILLEGAL_DECKLIST: SanctionLevel.WARNING,
    SanctionSubcategory.ILLEGAL_MAIN_DECK_LEGAL_DECKLIST: SanctionLevel.STANDINGS_ADJUSTMENT,
    SanctionSubcategory.ILLEGAL_MAIN_DECK_NO_DECKLIST: SanctionLevel.STANDINGS_ADJUSTMENT,
    SanctionSubcategory.OUTSIDE_ASSISTANCE: SanctionLevel.STANDINGS_ADJUSTMENT,
    SanctionSubcategory.SLOW_PLAY: SanctionLevel.CAUTION,
    SanctionSubcategory.LIMITED_PROCEDURE_VIOLATION: SanctionLevel.CAUTION,
    SanctionSubcategory.PUBLIC_INFO_MISCOMMUNICATION: SanctionLevel.WARNING,
    SanctionSubcategory.OBSCURING_GAME_STATE: SanctionLevel.CAUTION,
    SanctionSubcategory.MARKED_CARDS: SanctionLevel.WARNING,
    SanctionSubcategory.INSUFFICIENT_SHUFFLING: SanctionLevel.WARNING,
    # Unsportsmanlike Conduct (v2 §4)
    SanctionSubcategory.MINOR: SanctionLevel.WARNING,
    SanctionSubcategory.MAJOR: SanctionLevel.STANDINGS_ADJUSTMENT,
    SanctionSubcategory.AGGRESSIVE_BEHAVIOUR: SanctionLevel.DISQUALIFICATION,
    SanctionSubcategory.BRIBERY_AND_WAGERING: SanctionLevel.DISQUALIFICATION,
    SanctionSubcategory.THEFT_OF_TOURNAMENT_MATERIAL: SanctionLevel.DISQUALIFICATION,
    SanctionSubcategory.STALLING: SanctionLevel.DISQUALIFICATION,
    SanctionSubcategory.CHEATING: SanctionLevel.DISQUALIFICATION,
    SanctionSubcategory.FRAUD: SanctionLevel.DISQUALIFICATION,
    SanctionSubcategory.COLLUSION: SanctionLevel.DISQUALIFICATION,
    SanctionSubcategory.HEALTH_AND_SAFETY_DISRUPTION: SanctionLevel.WARNING,
    SanctionSubcategory.RAGE_QUITTING: SanctionLevel.DISQUALIFICATION,
    SanctionSubcategory.FAILURE_TO_PLAY_TO_WIN: SanctionLevel.WARNING,
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


class CommunityLink(msgspec.Struct, kw_only=True, frozen=True):
    """A community resource link shared by a member."""

    type: CommunityLinkType
    url: str
    label: str = ""
    language: str = ""  # ISO 639-1 code (e.g., "en", "es"). Empty = unset.
    moderation: LinkModeration | None = None


class TimeExtensionPolicy(StrEnum):
    """Time extension method per VEKN Judges Guide v2 section 1.2.4."""

    ADDITIONS = "additions"  # Manual +N min per table
    CLOCK_STOP = "clock_stop"  # Pause/resume per table
    BOTH = "both"  # Both mechanisms available


class TimerState(msgspec.Struct, kw_only=True):
    """Global round timer state. Clients compute countdown locally."""

    started_at: datetime | None = None  # When timer was started/resumed (UTC)
    elapsed_before_pause: float = 0.0  # Seconds accumulated in prior running periods
    paused: bool = True  # True = not running


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

    # Community links (officials only: NC/Prince/IC)
    community_links: list[CommunityLink] = msgspec.field(default_factory=list)

    # Cooptation tracking (who granted VEKN membership)
    coopted_by: str | None = None  # user_uid of Prince/NC/IC who granted VEKN ID
    coopted_at: datetime | None = None

    # VEKN sync tracking
    vekn_synced: bool = False  # True if user data came from VEKN API
    vekn_synced_at: datetime | None = None  # Last sync timestamp
    local_modifications: set[str] = msgspec.field(
        default_factory=set
    )  # Fields modified locally (won't be overwritten by sync)

    # VEKN prefix (for Prince/NC users, extracted from princeid/coordinatorid)
    vekn_prefix: str | None = None  # Used to infer coopted_by during sync

    # Resync tracking: set to DB now() when roles or vekn_id changes,
    # triggers full SSE resync for this user on next connect
    resync_after: datetime | None = None

    # Calendar feed: URL-safe token for iCal subscription authentication
    calendar_token: str | None = None

    # Embedded rating data (merged from separate Rating objects)
    constructed_online: CategoryRating | None = None
    constructed_offline: CategoryRating | None = None
    limited_online: CategoryRating | None = None
    limited_offline: CategoryRating | None = None
    wins: list[str] = msgspec.field(
        default_factory=list
    )  # All-time tournament UIDs won


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


class Rating(BaseObject, kw_only=True):
    user_uid: str
    country: str | None = None
    constructed_online: CategoryRating | None = None
    constructed_offline: CategoryRating | None = None
    limited_online: CategoryRating | None = None
    limited_offline: CategoryRating | None = None
    wins: list[str] = msgspec.field(
        default_factory=list
    )  # All-time tournament UIDs won


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
    table_rooms: list[Room] = msgspec.field(default_factory=list)
    # Timer config
    round_time: int = 0  # Round duration in seconds (0 = no timer)
    finals_time: int = 0  # Finals duration in seconds (0 = use round_time)
    time_extension_policy: TimeExtensionPolicy = TimeExtensionPolicy.ADDITIONS


class PlayerState(StrEnum):
    REGISTERED = "Registered"
    CHECKED_IN = "Checked-in"
    PLAYING = "Playing"
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


class Seat(msgspec.Struct, kw_only=True):
    player_uid: str  # FK → users
    result: Score = Score()
    judge_uid: str = ""  # FK → users (if a judge sets the score, players cannot modify)


class TableState(StrEnum):
    FINISHED = "Finished"
    IN_PROGRESS = "In Progress"
    INVALID = "Invalid"


class ScoreOverride(msgspec.Struct, kw_only=True):
    judge_uid: str  # FK → users
    comment: str = ""


class Table(msgspec.Struct, kw_only=True):
    seating: list[Seat]
    state: TableState = TableState.IN_PROGRESS
    override: ScoreOverride | None = None


class FinalsTable(Table, kw_only=True):
    seating: list[Seat]
    seed_order: list[str]


class Deck(msgspec.Struct, kw_only=True):
    round: int | None = None
    name: str = ""
    author: str = ""  # for attribution
    comments: str = ""
    cards: dict[str, int] = msgspec.field(default_factory=dict)  # card_uid: count
    attribution: str | None = None  # None = anonymous, vekn_id = attributed to member


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
    table_paused_at: dict[str, str] = msgspec.field(
        default_factory=dict
    )  # table_idx → ISO datetime


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
