"""Data models using msgspec, hand-synchronized with frontend/src/lib/types.ts."""

import json
import secrets
from datetime import datetime
from enum import StrEnum
from typing import Annotated

import msgspec
from archon_engine import PyEngine

Uid = Annotated[str, msgspec.Meta(description="UUID v7.")]
Instant = Annotated[datetime, msgspec.Meta(description="UTC instant.")]


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
    SHERIFF = "Sheriff"
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
    SPOTIFY = "spotify"
    X = "x"
    BLUESKY = "bluesky"
    OTHER = "other"


_LINK_PLACEMENTS: dict[CommunityLinkType, str] = {
    CommunityLinkType(t["type"]): t["placement"]
    for t in json.loads(PyEngine().community_link_reference())["types"]
}
if set(_LINK_PLACEMENTS) != set(CommunityLinkType):
    raise RuntimeError("CommunityLinkType drifted from engine/src/community.rs")

CONTENT_LINK_TYPES: frozenset[CommunityLinkType] = frozenset(
    t for t, placement in _LINK_PLACEMENTS.items() if placement == "content"
)


class LinkModeration(StrEnum):
    HIDDEN = "hidden"
    NATIONAL = "national"
    GLOBAL = "global"


class CommunityLink(msgspec.Struct, kw_only=True, frozen=True):
    type: CommunityLinkType
    url: str
    label: str = ""
    languages: Annotated[
        list[str],
        msgspec.Meta(
            description="ISO 639-1 codes. Empty means the link is not "
            "language-specific."
        ),
    ] = msgspec.field(default_factory=list)
    country: Annotated[
        str | None,
        msgspec.Meta(
            description="ISO 3166-1 alpha-2 code of the country the link serves. "
            "Null falls back to the owner's country."
        ),
    ] = None
    moderation: Annotated[
        LinkModeration | None,
        msgspec.Meta(
            description="A moderator's decision on the link: hidden, or promoted "
            "to a country's card (national, NC) or the global one (global, IC). "
            "Null when no moderator has acted."
        ),
    ] = None


class TimerState(msgspec.Struct, kw_only=True):
    started_at: Annotated[
        datetime | None,
        msgspec.Meta(
            description="UTC instant the timer last started running. Null while "
            "it has never run."
        ),
    ] = None
    elapsed_before_pause: Annotated[
        float, msgspec.Meta(description="Seconds accumulated before the last pause.")
    ] = 0.0
    paused: bool = True


class Announcement(msgspec.Struct, kw_only=True):
    id: Annotated[
        str,
        msgspec.Meta(
            description="uuid7 hex, the client's dedup and dismissal key. Not a "
            "BaseObject uid."
        ),
    ]
    body: str
    created_at: Instant
    author_uid: Annotated[
        str, msgspec.Meta(description="Uid of the member who posted it.")
    ]
    author_name: str = ""


class RatingCategory(StrEnum):
    CONSTRUCTED_ONLINE = "constructed_online"
    CONSTRUCTED_OFFLINE = "constructed_offline"
    LIMITED_ONLINE = "limited_online"
    LIMITED_OFFLINE = "limited_offline"


class TournamentRatingEntry(msgspec.Struct, kw_only=True, frozen=True):
    tournament_uid: Annotated[
        str, msgspec.Meta(description="Uid of the tournament this result is from.")
    ]
    tournament_name: str
    date: Annotated[
        str,
        msgspec.Meta(description="The tournament's start date, ISO 8601 `YYYY-MM-DD`."),
    ]
    player_count: int
    rank: Annotated[
        str,
        msgspec.Meta(description="TournamentRank value, empty for an ordinary event."),
    ]
    vp: float
    gw: int
    finalist_position: Annotated[
        int,
        msgspec.Meta(description="0 not a finalist, 1 winner, 2 runner-up."),
    ]
    points: int
    position: Annotated[
        int,
        msgspec.Meta(
            description="VEKN 3.7.5 band: winner 1, other finalists tied 2, then "
            "non-finalists. 0 on rows written before the field existed."
        ),
    ] = 0


class CategoryRating(msgspec.Struct, kw_only=True):
    total: Annotated[
        int, msgspec.Meta(description="Rating points across the listed tournaments.")
    ] = 0
    tournaments: Annotated[
        list[TournamentRatingEntry],
        msgspec.Meta(description="Every rated result contributing to the total."),
    ] = msgspec.field(default_factory=list)


class BaseObject(msgspec.Struct, kw_only=True):
    uid: Uid
    modified: Annotated[
        datetime, msgspec.Meta(description="UTC instant of the last write.")
    ]
    deleted_at: Annotated[
        datetime | None,
        msgspec.Meta(description="UTC instant of the soft delete. Null while live."),
    ] = None


class AuthMethod(msgspec.Struct, kw_only=True):
    uid: Uid
    modified: Annotated[
        datetime, msgspec.Meta(description="UTC instant of the last write.")
    ]
    user_uid: Annotated[str, msgspec.Meta(description="Uid of the member it logs in.")]
    method_type: AuthMethodType
    identifier: Annotated[
        str,
        msgspec.Meta(
            description="Email address, Discord snowflake id, or WebAuthn "
            "credential id, per method_type."
        ),
    ]
    credential_hash: Annotated[
        str | None,
        msgspec.Meta(description="Password hash or passkey public key."),
    ] = None
    verified: bool = False
    created_at: Annotated[
        datetime | None, msgspec.Meta(description="UTC instant of first use.")
    ] = None
    last_used_at: Annotated[
        datetime | None, msgspec.Meta(description="UTC instant of the last login.")
    ] = None
    sign_count: Annotated[
        int, msgspec.Meta(description="WebAuthn signature counter.")
    ] = 0


class User(BaseObject, kw_only=True):
    name: str
    country: Annotated[
        str | None,
        msgspec.Meta(description="ISO 3166-1 alpha-2 code of the member's country."),
    ] = None
    vekn_id: Annotated[
        str | None, msgspec.Meta(description="The member's VEKN number.")
    ] = None
    city: str | None = None
    city_geoname_id: Annotated[
        int | None, msgspec.Meta(description="GeoNames id of the city.")
    ] = None
    state: str | None = None
    nickname: str | None = None
    roles: Annotated[
        list[Role], msgspec.Meta(description="Organizational roles held, if any.")
    ] = msgspec.field(default_factory=list)

    avatar_path: str | None = None

    # server-written only (promo_stock.recompute), full projection only.
    promo_stock: Annotated[
        dict[str, int],
        msgspec.Meta(description="Promo uid to copies the member still holds."),
    ] = msgspec.field(default_factory=dict)

    contact_email: str | None = None
    contact_discord: str | None = None
    discord_id: Annotated[
        str | None, msgspec.Meta(description="Discord snowflake id.")
    ] = None
    contact_phone: str | None = None
    phone_is_whatsapp: bool = False

    # full projection only; github_login can go stale on rename/recycle,
    # github_id is the stable anchor.
    github_login: str | None = None
    github_id: str | None = None

    community_links: list[CommunityLink] = msgspec.field(default_factory=list)

    coopted_by: Annotated[
        str | None, msgspec.Meta(description="Uid of the member who co-opted them.")
    ] = None
    coopted_at: Annotated[datetime | None, msgspec.Meta(description="UTC.")] = None

    # not a soft-delete; history and ratings stay live.
    deceased_at: Annotated[
        datetime | None,
        msgspec.Meta(description="UTC instant the in-memoriam marker was set."),
    ] = None
    deceased_by_uid: str | None = None  # audit only; full projection only

    vekn_synced: bool = False
    vekn_synced_at: Annotated[
        datetime | None, msgspec.Meta(description="UTC instant of the last VEKN sync.")
    ] = None
    local_modifications: Annotated[
        set[str],
        msgspec.Meta(description="User field names never overwritten by VEKN sync."),
    ] = msgspec.field(default_factory=set)

    vekn_prefix: Annotated[
        str | None,
        msgspec.Meta(
            description="VEKN id prefix this member administers members under."
        ),
    ] = None
    calendar_token: str | None = None

    constructed_online: CategoryRating | None = None
    constructed_offline: CategoryRating | None = None
    limited_online: CategoryRating | None = None
    limited_offline: CategoryRating | None = None
    wins: Annotated[
        list[str], msgspec.Meta(description="Uids of the tournaments this member won.")
    ] = msgspec.field(default_factory=list)


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
    issued_at: Instant
    expires_at: Annotated[
        datetime | None, msgspec.Meta(description="UTC. Null means permanent.")
    ] = None
    lifted_at: Annotated[
        datetime | None,
        msgspec.Meta(description="UTC instant it was lifted. Null while it stands."),
    ] = None
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
    format: Annotated[
        str | None,
        msgspec.Meta(description="TournamentFormat value. Null accepts any format."),
    ] = None
    country: Annotated[
        str | None,
        msgspec.Meta(description="ISO 3166-1 alpha-2 code. Null means worldwide."),
    ] = None
    start: Annotated[
        datetime | None,
        msgspec.Meta(
            description="Local opening of the league window, ISO 8601 and "
            "carrying no offset."
        ),
    ] = None
    finish: Annotated[
        datetime | None,
        msgspec.Meta(
            description="Local close, same convention as `start`. Null means ongoing."
        ),
    ] = None
    description: str = ""
    organizers_uids: Annotated[
        list[str], msgspec.Meta(description="Uids of the members running the league.")
    ] = msgspec.field(default_factory=list)
    parent_uid: Annotated[
        str | None,
        msgspec.Meta(description="Uid of the meta-league this one belongs to."),
    ] = None
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
    """An empty string is an ordinary event, which is most of them."""

    BASIC = ""
    NC = "National Championship"
    CC = "Continental Championship"


class TournamentMinimal(BaseObject, kw_only=True):
    name: str
    format: TournamentFormat = TournamentFormat.Standard
    rank: Annotated[TournamentRank, msgspec.Meta(description="Championship level.")] = (
        TournamentRank.BASIC
    )
    online: bool = False
    start: Annotated[
        datetime | None,
        msgspec.Meta(
            description="Local start, ISO 8601 and carrying no offset. Pair it "
            "with `timezone` to get an instant."
        ),
    ] = None
    finish: Annotated[
        datetime | None,
        msgspec.Meta(description="Local finish, same convention as `start`."),
    ] = None
    timezone: Annotated[
        str,
        msgspec.Meta(
            description="IANA name, such as `Europe/Stockholm`. The one to read "
            "`start` and `finish` in."
        ),
    ] = "UTC"
    country: Annotated[
        str | None,
        msgspec.Meta(
            description="ISO 3166-1 alpha-2 code of the host country. Empty when "
            "the event predates the field, which many imported records do."
        ),
    ] = None
    league_uid: Annotated[
        str | None,
        msgspec.Meta(
            description="Uid of the league this event counts towards, null if none."
        ),
    ] = None
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
    organizers_uids: Annotated[
        list[str], msgspec.Meta(description="Uids of the members organizing the event.")
    ] = msgspec.field(default_factory=list)
    venue: str = ""
    venue_url: str = ""
    address: str = ""
    map_url: str = ""
    registration_url: Annotated[
        str,
        msgspec.Meta(
            description="External page taking the sign-ups, empty when Archon takes them."
        ),
    ] = ""
    proxies: bool = False
    multideck: bool = False
    decklist_required: bool = False
    description: str = ""
    standings_mode: StandingsMode = StandingsMode.PRIVATE
    decklists_mode: DeckListsMode = DeckListsMode.WINNER
    max_rounds: Annotated[
        int,
        msgspec.Meta(
            description="Preliminary rounds planned. 0 means it was never set."
        ),
    ] = 0
    max_players: Annotated[
        int, msgspec.Meta(description="Soft cap on registrations. 0 means none.")
    ] = 0
    # House (non-VEKN) event: per-player cap from a shared pool, never pushed to
    # VEKN/ratings/RTP. Decoupled from max_rounds, which VEKN-push forces to 2-4.
    open_rounds: bool = False
    self_organized_rounds: bool = (
        False  # open rounds: registered players may seat their own pod
    )
    table_rooms: list[Room] = msgspec.field(default_factory=list)
    round_time: Annotated[
        int, msgspec.Meta(description="Round length in seconds. 0 means untimed.")
    ] = 0
    finals_time: Annotated[
        int,
        msgspec.Meta(
            description="Finals length in seconds. 0 falls back to `round_time`."
        ),
    ] = 0


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
    toss: Annotated[
        int, msgspec.Meta(description="Draw for finals seeding. 0 means no draw.")
    ] = 0
    result: Annotated[
        Score,
        msgspec.Meta(
            description="Aggregated score, used when there is no round detail."
        ),
    ] = Score()
    finalist: bool = False
    display_name: str | None = None
    non_competing: Annotated[
        bool,
        msgspec.Meta(description="Proxy stand-in: excluded from rank, RTP and finals."),
    ] = False
    missing_decklist: Annotated[
        bool,
        msgspec.Meta(description="Checked in without the decklist the event requires."),
    ] = False
    waitlisted: Annotated[
        bool,
        msgspec.Meta(
            description="Signed up past max_players: cannot check in until promoted."
        ),
    ] = False


class Seat(msgspec.Struct, kw_only=True):
    player_uid: Annotated[
        str, msgspec.Meta(description="Uid of the member seated here.")
    ]
    result: Score = Score()
    # players can't edit a seat a judge has scored
    judge_uid: Annotated[
        str,
        msgspec.Meta(
            description="Uid of the judge who scored the seat. Empty if none."
        ),
    ] = ""


class TableState(StrEnum):
    FINISHED = "Finished"
    IN_PROGRESS = "In Progress"
    INVALID = "Invalid"
    # soft-cancelled; slot preserved, excluded from cap/standings
    CANCELLED = "Cancelled"


class ScoreOverride(msgspec.Struct, kw_only=True):
    judge_uid: Annotated[
        str, msgspec.Meta(description="Uid of the judge who overrode the score.")
    ]
    comment: str = ""


class Table(msgspec.Struct, kw_only=True):
    seating: list[Seat]
    state: TableState = TableState.IN_PROGRESS
    override: ScoreOverride | None = None
    organized_by: Annotated[
        str | None,
        msgspec.Meta(
            description="Uid of the player who seated this table themselves, in a "
            "tournament that allows it. Null on a table the organizer seated."
        ),
    ] = None


class FinalsTable(Table, kw_only=True):
    seating: list[Seat]
    organized_by: Annotated[
        str | None,
        msgspec.Meta(
            description="Always null: a final is never self-organized. The field "
            "is inherited from the preliminary table shape."
        ),
    ] = None
    seed_order: Annotated[
        list[str], msgspec.Meta(description="Uids of the finalists in seeding order.")
    ]


class DeckObject(BaseObject, kw_only=True):
    tournament_uid: Annotated[
        str, msgspec.Meta(description="Uid of the tournament the deck was played in.")
    ]
    user_uid: Annotated[
        str, msgspec.Meta(description="Uid of the member who played it.")
    ]
    round: Annotated[
        int | None,
        msgspec.Meta(
            description="The round this deck was played in, null when it is the "
            "event's single registered deck."
        ),
    ] = None
    name: str = ""
    author: str = ""
    comments: str = ""
    cards: Annotated[
        dict[str, int],
        msgspec.Meta(
            description="Card id to count. Ids are krcg's, resolvable at "
            "https://v4.api.krcg.org."
        ),
    ] = msgspec.field(default_factory=dict)
    attribution: Annotated[
        str | None,
        msgspec.Meta(
            description="Designer credit: a VEKN id, the sentinel `twda` when the "
            "credit lives in the archive rather than with us, or null for anonymous."
        ),
    ] = None
    public: bool = False  # engine-set from decklists_mode, not client-writable


class Standing(msgspec.Struct, kw_only=True, frozen=True):
    # set by the engine on FinishRound/FinishTournament, or directly by VEKN sync
    # (no round detail in that case).
    user_uid: Annotated[str, msgspec.Meta(description="Uid of the ranked member.")]
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
    winners: Annotated[
        list[str], msgspec.Meta(description="Uids of the members drawn.")
    ] = msgspec.field(default_factory=list)
    # display-only; never written to promos_distributed
    prize_promo_uid: Annotated[
        str | None, msgspec.Meta(description="Uid of the promo awarded.")
    ] = None


class PromoDistribution(msgspec.Struct, kw_only=True):
    promo_uid: Annotated[str, msgspec.Meta(description="Uid of the promo handed out.")]
    qty: int


class TwdaOutcome(StrEnum):
    SUBMITTED = "submitted"
    SKIPPED = "skipped"
    FAILED = "failed"


class TwdaStatus(msgspec.Struct, kw_only=True):
    # organizer-facing transparency for the fire-and-forget PR flow in
    # routes/tournaments.maybe_submit_twda.

    outcome: TwdaOutcome
    reason: Annotated[
        str,
        msgspec.Meta(
            description="Skip reason code, or `step[:http-status]` for a "
            "failure, mapped to a message frontend-side."
        ),
    ] = ""
    pr_url: str = ""
    at: Annotated[
        datetime | None, msgspec.Meta(description="UTC instant of the attempt.")
    ] = None


class Tournament(TournamentConfig, kw_only=True):
    # bytes live in the banners table.
    banner_path: Annotated[
        str | None,
        msgspec.Meta(
            description="Path to the event's image on this host, already versioned "
            "(`?v=<epoch-ms>`). Null when there is none."
        ),
    ] = None
    external_ids: Annotated[
        dict[str, str],
        msgspec.Meta(
            description="This event's id on other systems, keyed by system name. "
            "`vekn` is a vekn.net event id."
        ),
    ] = msgspec.field(default_factory=dict)
    # Written once and never rewritten: a published TWDA branch and every shared
    # short link key hang on it. Not `checkin_code`, which is a capability token
    # — publishing it grants check-in.
    event_code: Annotated[
        str,
        msgspec.Meta(
            description="The event's permanent public handle. Empty on records "
            "imported from an archive."
        ),
    ] = ""
    checkin_code: str = msgspec.field(default_factory=lambda: secrets.token_urlsafe(16))
    players: list[Player] = msgspec.field(default_factory=list)
    rounds: list[list[Table]] = msgspec.field(default_factory=list)
    finals: FinalsTable | None = None
    winner: Annotated[
        str,
        msgspec.Meta(description="Uid of the winning member. Empty while undecided."),
    ] = ""
    # engine-computed or VEKN-sync-populated; not cleared when rounds are empty.
    standings: list[Standing] = msgspec.field(default_factory=list)
    # Never `player_count`: league scoring already reads that key off a
    # synthesized summary object.
    reported_player_count: Annotated[
        int,
        msgspec.Meta(
            description="Externally attested field size for a row that carries no "
            "roster of its own. 0 means no attestation, derive it from the roster."
        ),
    ] = 0
    raffles: list[RaffleDraw] = msgspec.field(default_factory=list)
    # organizer-entered via ReportPromos; server never writes this — the offline
    # device is authoritative on go-online.
    promos_distributed: list[PromoDistribution] = msgspec.field(default_factory=list)
    promo_stock_source_uid: Annotated[
        str,
        msgspec.Meta(
            description="Uid of the holder the event's promos are drawn from."
        ),
    ] = ""
    vekn_pushed_at: Annotated[
        datetime | None,
        msgspec.Meta(
            description="UTC instant the results were pushed to vekn.net. Null if "
            "never pushed."
        ),
    ] = None
    # sticky: results changed after vekn_pushed_at. The push is write-once, so
    # only a manual admin fix clears it.
    vekn_results_stale: bool = False
    vekn_event_absent_at: Annotated[
        datetime | None,
        msgspec.Meta(
            description="UTC instant the calendar scan last confirmed vekn.net "
            "holds no event at this id. Null while the event still answers."
        ),
    ] = None
    twda_status: TwdaStatus | None = None  # organizer projection only
    offline_mode: bool = False
    offline_device_id: str = ""
    offline_user_uid: Annotated[
        str, msgspec.Meta(description="Uid of the member holding the event offline.")
    ] = ""
    offline_since: Annotated[
        datetime | None,
        msgspec.Meta(description="UTC instant the event went offline."),
    ] = None
    timer: TimerState = msgspec.field(default_factory=TimerState)  # online-only
    table_extra_time: Annotated[
        dict[str, int],
        msgspec.Meta(
            description="Extra seconds granted per table, keyed by the table's "
            "index within its round as a string."
        ),
    ] = msgspec.field(default_factory=dict)
    announcements: list[Announcement] = msgspec.field(default_factory=list)


class PromoKind(StrEnum):
    CARD = "card"
    PACK = "pack"
    OTHER = "other"


class PromoHolding(msgspec.Struct, kw_only=True):
    """Server-computed inventory aggregate for one holder (promo ledger)."""

    assigned: Annotated[
        int, msgspec.Meta(description="Stock credited in: assignments plus intakes.")
    ] = 0
    remaining: int = 0


class PromoLedgerKind(StrEnum):
    INTAKE = "intake"
    ASSIGNMENT = "assignment"
    DISTRIBUTION = "distribution"


class PromoLedgerEntry(msgspec.Struct, kw_only=True):
    # promo_ledger side table, not synced. Append-mostly — corrections are
    # compensating rows (negative qty), never edits.

    uid: Uid
    kind: PromoLedgerKind
    promo_uid: Annotated[str, msgspec.Meta(description="Uid of the promo moved.")]
    qty: Annotated[
        int,
        msgspec.Meta(
            description="Copies moved. Negative is a compensating correction."
        ),
    ]
    from_uid: Annotated[
        str,
        msgspec.Meta(
            description="Uid of the source holder; of the receiver on an intake."
        ),
    ]
    to_uid: Annotated[
        str | None,
        msgspec.Meta(
            description="Uid of the assignment target. Null on an intake or a "
            "distribution."
        ),
    ] = None
    note: str = ""
    happened_at: Annotated[
        datetime, msgspec.Meta(description="UTC instant the move actually happened.")
    ]
    created_by: Annotated[
        str, msgspec.Meta(description="Uid of the member who recorded the row.")
    ]
    created_at: Instant


class Promo(BaseObject, kw_only=True):
    # catalog fields are IC-edited; holdings is server-written only, denormalized
    # so every client reads the same counts.

    name: str
    kind: PromoKind = PromoKind.CARD
    description: str = ""
    release_date: Annotated[
        datetime | None,
        msgspec.Meta(description="UTC. Null when the promo has no announced release."),
    ] = None
    # retirement flag; a referenced promo is never soft-deleted so historical
    # references keep resolving.
    active: bool = True
    # UX-only distribution filter, no access control; empty = unrestricted, both
    # set means AND.
    allowed_ranks: list[TournamentRank] = msgspec.field(default_factory=list)
    league_uids: Annotated[
        list[str],
        msgspec.Meta(description="Uids of the leagues the promo is restricted to."),
    ] = msgspec.field(default_factory=list)
    image_path: str | None = None
    holdings: Annotated[  # full projection only
        dict[str, PromoHolding],
        msgspec.Meta(description="Holder uid to that holder's inventory."),
    ] = msgspec.field(default_factory=dict)


class OAuthScope(StrEnum):
    PROFILE_READ = "profile:read"
    EVENT_RUN = "event:run"
    API_READ = "api:read"


class OAuthClient(BaseObject, kw_only=True):
    name: str
    client_id: Annotated[str, msgspec.Meta(description="32-character random id.")]
    client_secret_hash: Annotated[str, msgspec.Meta(description="Argon2 hash.")]
    redirect_uris: list[str]
    scopes: list[OAuthScope]
    created_by_uid: Annotated[
        str, msgspec.Meta(description="Uid of the member who registered the client.")
    ]
    active: bool = True


class OAuthAuthorizationCode(BaseObject, kw_only=True):
    """Short-lived authorization code (60s TTL, single use)."""

    code: Annotated[str, msgspec.Meta(description="64-character random code.")]
    client_id: str
    user_uid: Annotated[
        str, msgspec.Meta(description="Uid of the member who authorized it.")
    ]
    redirect_uri: str
    scopes: list[OAuthScope]
    tournament_uid: Annotated[
        str | None,
        msgspec.Meta(description="The event event:run is scoped to."),
    ] = None
    code_challenge: Annotated[str, msgspec.Meta(description="S256 PKCE challenge.")]
    expires_at: Annotated[
        datetime, msgspec.Meta(description="UTC instant the code stops working.")
    ]
    used: bool = False


class OAuthToken(BaseObject, kw_only=True):
    token_jti: Annotated[str, msgspec.Meta(description="JWT id.")]
    client_id: str
    user_uid: Annotated[str, msgspec.Meta(description="Uid of the member it acts for.")]
    scopes: list[OAuthScope]
    tournament_uid: Annotated[
        str | None,
        msgspec.Meta(description="The event event:run is scoped to."),
    ] = None
    token_type: Annotated[
        str, msgspec.Meta(description='Either "access" or "refresh".')
    ]
    expires_at: Annotated[
        datetime, msgspec.Meta(description="UTC instant the token stops verifying.")
    ]
    revoked: bool = False
    parent_token_uid: Annotated[
        str | None,
        msgspec.Meta(description="Uid of the token this one was refreshed from."),
    ] = None


class OAuthConsent(BaseObject, kw_only=True):
    user_uid: Annotated[str, msgspec.Meta(description="Uid of the consenting member.")]
    client_id: str
    scopes: list[OAuthScope]
    tournament_uid: Annotated[
        str | None,
        msgspec.Meta(description="The event event:run is scoped to."),
    ] = None
