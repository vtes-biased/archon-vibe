"""Data models using msgspec. Changing a Struct here requires the
python-to-typescript-models rule to keep frontend/src/lib/types.ts synchronized."""

import json
import secrets
from datetime import datetime
from enum import StrEnum

import msgspec
from archon_engine import PyEngine


class ObjectType(StrEnum):
    USER = "user"
    SANCTION = "sanction"
    TOURNAMENT = "tournament"
    DECK = "deck"
    LEAGUE = "league"
    PROMO = "promo"


class DataLevel(StrEnum):
    PUBLIC = "public"
    MEMBER = "member"
    FULL = "full"


class Role(StrEnum):
    IC = "IC"
    NC = "NC"
    PRINCE = "Prince"
    ETHICS = "Ethics"
    PTC = "PTC"
    PT = "PT"
    RULEMONGER = "Rulemonger"
    JUDGE = "Judge"
    JUDGEKIN = "Judgekin"
    DEV = "DEV"


class AuthMethodType(StrEnum):
    EMAIL = "email"
    DISCORD = "discord"
    PASSKEY = "passkey"


class SanctionLevel(StrEnum):
    CAUTION = "caution"
    WARNING = "warning"
    STANDINGS_ADJUSTMENT = "standings_adjustment"
    DISQUALIFICATION = "disqualification"
    SUSPENSION = "suspension"
    PROBATION = "probation"


class SanctionCategory(StrEnum):
    PROCEDURAL_ERROR = "procedural_error"
    TOURNAMENT_ERROR = "tournament_error"
    UNSPORTSMANLIKE_CONDUCT = "unsportsmanlike_conduct"


class SanctionSubcategory(StrEnum):
    MISSED_MANDATORY_EFFECT = "missed_mandatory_effect"
    CARD_ACCESS_ERROR = "card_access_error"
    GAME_RULE_VIOLATION = "game_rule_violation"
    FAILURE_TO_MAINTAIN_GAME_STATE = "failure_to_maintain_game_state"
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


# The enum constructors below raise at import if engine/src/sanctions.rs drifts
# from the enums above, so a missed Judges-Guide revision fails loudly.
_SANCTION_REFERENCE = json.loads(PyEngine().sanction_reference())

SUBCATEGORIES_BY_CATEGORY: dict[SanctionCategory, list[SanctionSubcategory]] = {
    SanctionCategory(c["key"]): [
        SanctionSubcategory(s["key"]) for s in c["subcategories"]
    ]
    for c in _SANCTION_REFERENCE["categories"]
}

BASELINE_PENALTIES: dict[SanctionSubcategory, SanctionLevel] = {
    SanctionSubcategory(s["key"]): SanctionLevel(s["baseline"])
    for c in _SANCTION_REFERENCE["categories"]
    for s in c["subcategories"]
}


class CommunityLinkType(StrEnum):
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
    status: str  # "hidden" | "promoted"
    by: str
    at: datetime
    scope: str | None = None  # promoted only: "global" (IC) | "national" (NC)


class CommunityLink(msgspec.Struct, kw_only=True, frozen=True):
    type: CommunityLinkType
    url: str
    label: str = ""
    # ISO 639-1 codes; empty = shows under every filter.
    languages: list[str] = msgspec.field(default_factory=list)
    moderation: LinkModeration | None = None


class TimerState(msgspec.Struct, kw_only=True):
    started_at: datetime | None = None
    elapsed_before_pause: float = 0.0
    paused: bool = True


class Announcement(msgspec.Struct, kw_only=True):
    id: str  # uuid7 hex, the client dedup/dismissal key (not a BaseObject uid)
    body: str
    created_at: datetime
    author_uid: str
    author_name: str = ""


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
    points: int
    # VEKN 3.7.5 band: winner 1, other finalists tied 2, then non-finalists.
    # 0 = not yet backfilled on rows written before the field existed.
    position: int = 0


class CategoryRating(msgspec.Struct, kw_only=True):
    total: int = 0
    tournaments: list[TournamentRatingEntry] = msgspec.field(default_factory=list)


class BaseObject(msgspec.Struct, kw_only=True):
    uid: str  # UUID v7
    modified: datetime
    deleted_at: datetime | None = None


class AuthMethod(msgspec.Struct, kw_only=True):
    uid: str  # UUID v7
    modified: datetime
    user_uid: str
    method_type: AuthMethodType
    identifier: str  # email address, discord ID, or passkey credential ID
    credential_hash: str | None = None  # password hash or passkey public key
    verified: bool = False
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    sign_count: int = 0  # WebAuthn signature counter


class User(BaseObject, kw_only=True):
    name: str
    country: str | None = None
    vekn_id: str | None = None
    city: str | None = None
    city_geoname_id: int | None = None
    state: str | None = None
    nickname: str | None = None
    roles: list[Role] = msgspec.field(default_factory=list)

    avatar_path: str | None = None

    # promo_uid -> remaining copies; server-written only (promo_stock.recompute),
    # full projection only.
    promo_stock: dict[str, int] = msgspec.field(default_factory=dict)

    contact_email: str | None = None
    contact_discord: str | None = None
    discord_id: str | None = None
    contact_phone: str | None = None
    phone_is_whatsapp: bool = False

    # full projection only; github_login can go stale on rename/recycle,
    # github_id is the stable anchor.
    github_login: str | None = None
    github_id: str | None = None

    community_links: list[CommunityLink] = msgspec.field(default_factory=list)

    coopted_by: str | None = None
    coopted_at: datetime | None = None

    # not a soft-delete; history and ratings stay live.
    deceased_at: datetime | None = None
    deceased_by_uid: str | None = None  # audit only; full projection only

    vekn_synced: bool = False
    vekn_synced_at: datetime | None = None
    local_modifications: set[str] = msgspec.field(
        default_factory=set
    )  # fields never overwritten by VEKN sync

    vekn_prefix: str | None = None
    calendar_token: str | None = None

    constructed_online: CategoryRating | None = None
    constructed_offline: CategoryRating | None = None
    limited_online: CategoryRating | None = None
    limited_offline: CategoryRating | None = None
    wins: list[str] = msgspec.field(
        default_factory=list
    )  # all-time IRL tournament UIDs won; online wins excluded (HoF convention)


class Score(msgspec.Struct, kw_only=True, frozen=True):
    gw: int = 0
    vp: float = 0.0
    tp: int = 0


class Sanction(BaseObject, kw_only=True):
    user_uid: str
    issued_by_uid: str
    tournament_uid: str | None = None
    level: SanctionLevel
    category: SanctionCategory
    subcategory: SanctionSubcategory | None = None
    round_number: int | None = None
    description: str
    issued_at: datetime
    expires_at: datetime | None = None  # None = permanent
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
    name: str
    kind: LeagueKind = LeagueKind.LEAGUE
    standings_mode: LeagueStandingsMode = LeagueStandingsMode.RTP
    format: str | None = None  # TournamentFormat value or None = any
    country: str | None = None  # None = worldwide
    start: datetime | None = None
    finish: datetime | None = None  # None = ongoing
    description: str = ""
    organizers_uids: list[str] = msgspec.field(default_factory=list)
    parent_uid: str | None = None
    open_to_country_princes: bool = False  # attach-only; inert without a country


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
    league_uid: str | None = None
    state: TournamentState = TournamentState.PLANNED


class StandingsMode(StrEnum):
    PRIVATE = "Private"
    CUTOFF = "Cutoff"
    TOP_10 = "Top 10"
    PUBLIC = "Public"


class DeckListsMode(StrEnum):
    WINNER = "Winner"
    FINALISTS = "Finalists"
    ALL = "All"


class Room(msgspec.Struct, kw_only=True):
    name: str
    count: int


class TournamentConfig(TournamentMinimal, kw_only=True):
    organizers_uids: list[str] = msgspec.field(default_factory=list)
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
    # Soft cap (0 = none): the UI warns past it, never blocks; no waitlist.
    max_players: int = 0
    # House (non-VEKN) event: per-player cap from a shared pool, never pushed to
    # VEKN/ratings/RTP. Decoupled from max_rounds, which VEKN-push forces to 2-4.
    open_rounds: bool = False
    self_organized_rounds: bool = (
        False  # open rounds: registered players may seat their own pod
    )
    table_rooms: list[Room] = msgspec.field(default_factory=list)
    round_time: int = 0  # seconds, 0 = no timer
    finals_time: int = 0  # seconds, 0 = use round_time


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
    user_uid: str | None = None
    state: PlayerState = PlayerState.REGISTERED
    payment_status: PaymentStatus = PaymentStatus.PENDING
    toss: int = 0  # non-zero when draws for seeding finals
    result: Score = Score()  # aggregated score, used when no round detail (VEKN sync)
    finalist: bool = False
    display_name: str | None = None
    non_competing: bool = False  # proxy stand-in; excluded from rank/RTP/finals


class Seat(msgspec.Struct, kw_only=True):
    player_uid: str
    result: Score = Score()
    judge_uid: str = ""  # set if a judge scored this seat; players can't edit it then


class TableState(StrEnum):
    FINISHED = "Finished"
    IN_PROGRESS = "In Progress"
    INVALID = "Invalid"
    # soft-cancelled; slot preserved, excluded from cap/standings
    CANCELLED = "Cancelled"


class ScoreOverride(msgspec.Struct, kw_only=True):
    judge_uid: str
    comment: str = ""


class Table(msgspec.Struct, kw_only=True):
    seating: list[Seat]
    state: TableState = TableState.IN_PROGRESS
    override: ScoreOverride | None = None
    organized_by: str | None = None


class FinalsTable(Table, kw_only=True):
    seating: list[Seat]
    seed_order: list[str]


class DeckObject(BaseObject, kw_only=True):
    tournament_uid: str
    user_uid: str
    round: int | None = None
    name: str = ""
    author: str = ""
    comments: str = ""
    cards: dict[str, int] = msgspec.field(default_factory=dict)
    attribution: str | None = None
    public: bool = False  # engine-set from decklists_mode, not client-writable


class Standing(msgspec.Struct, kw_only=True, frozen=True):
    # set by the engine on FinishRound/FinishTournament, or directly by VEKN sync
    # (no round detail in that case).
    user_uid: str
    gw: float = 0.0
    vp: float = 0.0
    tp: int = 0
    toss: int = 0
    finalist: bool = False
    disqualified: bool = False  # forfeited score (zeroed), sorted last, no RTP
    non_competing: bool = False  # excluded from rank/RTP/finals, score NOT zeroed


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
    # display-only; never written to promos_distributed
    prize_promo_uid: str | None = None


class PromoDistribution(msgspec.Struct, kw_only=True):
    promo_uid: str
    qty: int


class TwdaOutcome(StrEnum):
    SUBMITTED = "submitted"
    SKIPPED = "skipped"
    FAILED = "failed"


class TwdaStatus(msgspec.Struct, kw_only=True):
    # organizer-facing transparency for the fire-and-forget PR flow in
    # routes/tournaments.maybe_submit_twda.

    outcome: TwdaOutcome
    reason: str = ""  # skip reason code, mapped to i18n frontend-side
    pr_url: str = ""
    at: datetime | None = None


class Tournament(TournamentConfig, kw_only=True):
    # versioned URL (?v=<epoch-ms>); bytes live in the banners table, this is
    # just the path.
    banner_path: str | None = None
    external_ids: dict[str, str] = msgspec.field(default_factory=dict)  # platform: id
    checkin_code: str = msgspec.field(default_factory=lambda: secrets.token_urlsafe(16))
    players: list[Player] = msgspec.field(default_factory=list)
    rounds: list[list[Table]] = msgspec.field(default_factory=list)
    finals: FinalsTable | None = None
    winner: str = ""
    # engine-computed or VEKN-sync-populated; not cleared when rounds are empty.
    standings: list[Standing] = msgspec.field(default_factory=list)
    raffles: list[RaffleDraw] = msgspec.field(default_factory=list)
    # organizer-entered via ReportPromos; server never writes this — the offline
    # device is authoritative on go-online.
    promos_distributed: list[PromoDistribution] = msgspec.field(default_factory=list)
    promo_stock_source_uid: str = ""
    vekn_pushed_at: datetime | None = None
    # sticky: results changed after vekn_pushed_at. The push is write-once, so
    # only a manual admin fix clears it.
    vekn_results_stale: bool = False
    twda_status: TwdaStatus | None = None  # organizer projection only
    offline_mode: bool = False
    offline_device_id: str = ""
    offline_user_uid: str = ""
    offline_since: datetime | None = None
    timer: TimerState = msgspec.field(default_factory=TimerState)  # online-only
    table_extra_time: dict[str, int] = msgspec.field(
        default_factory=dict
    )  # table_idx → extra seconds
    announcements: list[Announcement] = msgspec.field(default_factory=list)


class PromoKind(StrEnum):
    CARD = "card"
    PACK = "pack"
    OTHER = "other"


class PromoHolding(msgspec.Struct, kw_only=True):
    """Server-computed inventory aggregate for one holder (promo ledger)."""

    assigned: int = 0  # stock credited in (assignments + intakes)
    remaining: int = 0


class PromoLedgerKind(StrEnum):
    INTAKE = "intake"
    ASSIGNMENT = "assignment"
    DISTRIBUTION = "distribution"


class PromoLedgerEntry(msgspec.Struct, kw_only=True):
    # promo_ledger side table, not synced. Append-mostly — corrections are
    # compensating rows (negative qty), never edits.

    uid: str
    kind: PromoLedgerKind
    promo_uid: str
    qty: int  # negative = compensating correction
    from_uid: str  # source holder; for intake, the receiving holder
    to_uid: str | None = None  # assignment target; None for intake/distribution
    note: str = ""
    happened_at: datetime
    created_by: str
    created_at: datetime


class Promo(BaseObject, kw_only=True):
    # catalog fields are IC-edited; holdings is server-written only, denormalized
    # so every client reads the same counts.

    name: str
    kind: PromoKind = PromoKind.CARD
    description: str = ""
    release_date: datetime | None = None
    # retirement flag; a referenced promo is never soft-deleted so historical
    # references keep resolving.
    active: bool = True
    # UX-only distribution filter, no access control; empty = unrestricted, both
    # set means AND.
    allowed_ranks: list[TournamentRank] = msgspec.field(default_factory=list)
    league_uids: list[str] = msgspec.field(default_factory=list)
    image_path: str | None = None
    holdings: dict[str, PromoHolding] = msgspec.field(
        default_factory=dict
    )  # full projection only


class OAuthScope(StrEnum):
    PROFILE_READ = "profile:read"
    USER_IMPERSONATE = "user:impersonate"


class OAuthClient(BaseObject, kw_only=True):
    name: str
    client_id: str  # 32-char random
    client_secret_hash: str  # Argon2 hash
    redirect_uris: list[str]
    scopes: list[OAuthScope]
    created_by_uid: str
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
    token_jti: str  # JWT ID
    client_id: str
    user_uid: str
    scopes: list[OAuthScope]
    token_type: str  # "access" or "refresh"
    expires_at: datetime
    revoked: bool = False
    parent_token_uid: str | None = None  # refresh chain tracking


class OAuthConsent(BaseObject, kw_only=True):
    user_uid: str
    client_id: str
    scopes: list[OAuthScope]
