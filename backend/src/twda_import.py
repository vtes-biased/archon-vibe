"""Reconstruct historic tournaments from the TWDA, and import winner decklists.

The archive is the only record of roughly a quarter of the events we hold wins
for: it only began carrying vekn.net event links around 2013, so everything older
reaches us through `backend/src/data/twda_decisions.tsv`, a reviewed mapping from
archive entry to either one of our tournaments or a reconstruction of one. What
that mapping settles is written onto the corpus, so the file is only ever
consulted for an entry nobody has settled yet.

Nothing here guesses. An entry the decisions file does not resolve is counted and
skipped — never created on a hunch, because a wrong reconstruction mints a
duplicate event and credits a real person with a win they did not take.
"""

import importlib.resources
import logging
import re
from datetime import UTC, datetime
from uuid import uuid7

import aiohttp
import msgspec

from . import http_client
from .data.timezones import CITY_TZ_OVERRIDES, COUNTRY_TIMEZONE
from .db import (
    get_connection,
    resolve_event_code,
    save_object_from_model,
    save_tournament,
    tournament_transaction,
)
from .decks import save_deck
from .geonames import City, CityIndex, city_index, match_city_in, normalize_country
from .models import (
    AttributionKind,
    DeckAttribution,
    DeckObject,
    ObjectType,
    Player,
    PlayerState,
    Standing,
    Tournament,
    TournamentFormat,
    TournamentState,
)
from .ratings import recompute_wins

logger = logging.getLogger(__name__)

# Legacy archon filed events against GoblinTrader Mallorca from 2025 on.
LEGACY_PLACEHOLDER_SINCE = "2025-01-01"

TWDA_URL = "https://static.krcg.org/data/twda.json"
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def extract_vekn_event_id(entry: dict) -> str | None:
    """Extract VEKN event ID from a TWDA entry.

    Recent entries have numeric `id` matching VEKN event IDs.
    Older entries have alphanumeric `id` but `event.url` (or legacy `event_link`)
    contains the VEKN ID.
    """
    entry_id = str(entry.get("id", ""))
    if entry_id.isdigit():
        return entry_id
    event = entry.get("event")
    link = (event.get("url", "") if isinstance(event, dict) else "") or entry.get(
        "event_link", ""
    )
    if "/event/" in link:
        return link.rsplit("/event/", 1)[-1].split("/")[0].split("?")[0]
    return None


class _TwdaCard(msgspec.Struct):
    id: int
    count: int = 1


class _TwdaEvent(msgspec.Struct):
    name: str = ""
    place: str = ""
    date: str = ""
    online: bool = False
    format: str = ""
    players_count: int = 0
    rounds: int = 0
    url: str = ""


class TwdaEntry(msgspec.Struct):
    id: str
    name: str = ""
    comment: str = ""
    cards: list[_TwdaCard] = []
    event: _TwdaEvent = msgspec.field(default_factory=_TwdaEvent)


def _flatten_twda_cards(entry: TwdaEntry) -> dict[str, int]:
    """{card_id_str: count} over the entry's card list."""
    cards: dict[str, int] = {}
    for card in entry.cards:
        key = str(card.id)
        cards[key] = cards.get(key, 0) + card.count
    return cards


async def _deck_owners_by_tournament(uids: list[str]) -> dict[str, set[str]]:
    """tournament uid -> user uids that already have a deck there.

    Owners only, not decks: the archive resolves against thousands of
    tournaments at once and decoding every deck of every one of them to ask a
    membership question is the whole corpus in memory for a boolean.
    """
    if not uids:
        return {}
    owners: dict[str, set[str]] = {}
    async with get_connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT "full"->>'tournament_uid', "full"->>'user_uid'
                   FROM objects
                   WHERE type = %s
                     AND "full"->>'tournament_uid' = ANY(%s)
                     AND deleted_at IS NULL""",
                (ObjectType.DECK, uids),
            )
        ).fetchall()
    for tournament_uid, user_uid in rows:
        owners.setdefault(tournament_uid, set()).add(user_uid)
    return owners


def load_decisions() -> dict[str, tuple[str, str]]:
    """twda entry id -> (action, target), from the reviewed decisions file.

    Actions are `attach` (target is one of our tournament uids) and `create`
    (target is the winning member's uid). Everything else in the file is an
    undecided line and is deliberately absent from the result, so the caller
    counts it as unresolved rather than acting on it.

    An absent file is a degraded run, not a failure: every entry already settled
    onto the corpus resolves without it, and only the ones nobody has settled yet
    go unresolved.
    """
    try:
        text = (
            importlib.resources.files("backend.src.data")
            .joinpath("twda_decisions.tsv")
            .read_text()
        )
    except FileNotFoundError:
        logger.warning("TWDA sync: no decisions file — settled entries only")
        return {}
    decisions: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entry_id, action, *rest = line.split("\t")
        target = rest[0] if rest else ""
        if action.startswith("attach:"):
            decisions[entry_id] = ("attach", action.removeprefix("attach:"))
        elif action == "create" and target:
            decisions[entry_id] = ("create", target)
    return decisions


def _twda_timezone(country: str | None, city: str) -> str:
    """Best-effort IANA zone from a country code and a city name.

    Line for line the venue sync's `_guess_timezone`, deliberately: that module
    retires with the VEKN API and this one outlives it, so the survivor must not
    import from it. The shared fact is the two tables, and those are shared.
    """
    if not country:
        return "UTC"
    country = country.upper()
    for cc, override_city, tz in CITY_TZ_OVERRIDES:
        if cc == country and override_city.lower() in city.lower():
            return tz
    return COUNTRY_TIMEZONE.get(country, "UTC")


def _twda_place(entry: TwdaEntry) -> tuple[str | None, str]:
    """(ISO country, city) from `event.place` — "City (STATE), Country"."""
    place = entry.event.place.strip()
    if not place:
        return None, ""
    head, _, tail = place.rpartition(",")
    country = normalize_country(tail) if head else None
    return country, head.split("(")[0].strip()


def twda_city(entry: TwdaEntry, cities: CityIndex) -> City | None:
    *head, tail = entry.event.place.split(",")
    country = normalize_country(tail) if head else None
    if not country:
        return None
    if (
        head[-1].strip() == "Palma de Mallorca"
        and _ISO_DATE_RE.match(entry.event.date)
        and entry.event.date >= LEGACY_PLACEHOLDER_SINCE
    ):
        return None
    for segment in reversed(head):
        name, _, region = segment.partition("(")
        if city := match_city_in(cities, name, country, [region.strip(" )"), *head]):
            return city
    return None


def reconstructed_tournament(
    entry: TwdaEntry, winner_uid: str, now: datetime, city: City | None = None
) -> Tournament:
    """The canonical rounds-less archival shape, as the VEKN and archon imports
    already write it — with the attested field size the archive supplies.

    The winner's `Player` row is not decoration: without it the tournament page
    renders the winner as a raw uid, the organizer roster reads empty against a
    populated member view, and the wins refresh never fires. Scores stay zero
    because the archive's is a total including the final, while `standings` is
    prelim-only by contract — splitting it would plant a guess where later
    arithmetic trusts a measurement.
    """
    country, place_city = _twda_place(entry)
    day = entry.event.date
    start = datetime.strptime(day, "%Y-%m-%d") if _ISO_DATE_RE.match(day) else None
    return Tournament(
        uid=str(uuid7()),
        modified=now,
        name=entry.event.name or f"VTES Tournament — {place_city or country or day}",
        format=TournamentFormat.Standard,
        online=entry.event.online or entry.event.place.strip().lower() == "online",
        start=start,
        finish=start,
        timezone=_twda_timezone(country, place_city),
        country=country,
        city=city["name"] if city else None,
        city_geoname_id=city["geoname_id"] if city else None,
        state=TournamentState.FINISHED,
        max_rounds=entry.event.rounds,
        # The archive's own file key — never `vekn`, since these have no vekn.net row.
        external_ids={"twda": entry.id},
        players=[
            Player(user_uid=winner_uid, state=PlayerState.FINISHED, finalist=True)
        ],
        standings=[Standing(user_uid=winner_uid, finalist=True)],
        winner=winner_uid,
        # The only field that survives to say how big this was. `players_count`
        # is absent on ~100 entries; 0 there means "unattested", same as anywhere.
        reported_player_count=entry.event.players_count,
    )


async def _tournaments_by_twda_id() -> dict[str, str]:
    """twda entry id -> our tournament uid, for every entry the corpus has settled."""
    async with get_connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT coalesce("full"->'external_ids'->>'twda',
                                   "full"->'external_ids'->>'twda_entry'), uid
                FROM objects
                WHERE type = %s
                  AND deleted_at IS NULL
                  AND ("full"->'external_ids'->>'twda' IS NOT NULL
                       OR "full"->'external_ids'->>'twda_entry' IS NOT NULL)""",
                (ObjectType.TOURNAMENT,),
            )
        ).fetchall()
    return {row[0]: row[1] for row in rows}


async def _settle_attachment(entry_id: str, uid: str, city: City | None = None) -> bool:
    """Stamp the archive key onto the tournament an `attach` names, so the next
    run reads the attachment off the corpus and never consults the file for it.

    Never under `twda`: that key means "reconstructed from the archive".
    """
    async with tournament_transaction(uid) as (tournament, conn):
        if tournament is None or tournament.deleted_at:
            return False
        held = tournament.external_ids.get("twda_entry") or tournament.external_ids.get(
            "twda"
        )
        if held:
            if held != entry_id:
                logger.warning(
                    f"TWDA sync: entry {entry_id} attaches to {uid}, which already "
                    f"holds archive entry {held} — not settling"
                )
            return False
        tournament.external_ids["twda_entry"] = entry_id
        if (
            city
            and not tournament.city_geoname_id
            and not tournament.online
            and (tournament.country or "").upper() == city["country_code"].upper()
        ):
            tournament.city = city["name"]
            tournament.city_geoname_id = city["geoname_id"]
        tournament.modified = datetime.now(UTC)
        await save_tournament(tournament, conn=conn)
    return True


async def _winners_by_tournament_uid(
    uids: list[str],
) -> dict[str, tuple[str, list, str | None]]:
    """uid -> (winner uid, organizer uids, state) for the tournaments a deck may
    attach to."""
    if not uids:
        return {}
    async with get_connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT uid, "full"->>'winner',
                          coalesce("full"->'organizers_uids', '[]'::jsonb),
                          "full"->>'state'
                   FROM objects
                   WHERE type = %s AND uid = ANY(%s) AND deleted_at IS NULL""",
                (ObjectType.TOURNAMENT, uids),
            )
        ).fetchall()
    return {row[0]: (row[1] or "", list(row[2] or []), row[3]) for row in rows}


async def run_twda_sync() -> dict[str, int]:
    """Reconcile the whole archive against our corpus: settle every entry onto
    the event it belongs to — reconstructing the ones we lack — then give every
    resolved winner their decklist.

    Deliberately no ETag. Once identities are attached from a reviewed file, OUR
    side moves while the archive sits still — a member is created, renamed, or
    claims a VEKN id — and a 304 short-circuit would skip the reconciliation
    forever, silently and permanently. A 12 MB fetch against a static CDN is the
    cheaper half of that trade.
    """
    entries = await _fetch_twda()
    decisions = load_decisions()
    known = await _tournaments_by_twda_id()
    now = datetime.now(UTC)

    stats = {
        "entries": len(entries),
        "created": 0,
        "settled": 0,
        "unresolved": 0,
        "stale_targets": 0,
        "orphaned": 0,
        "decks_created": 0,
    }
    resolved: dict[str, str] = {}
    cities: CityIndex | None = None

    for entry in entries:
        entry_id = entry.id
        existing = known.get(entry_id)
        if existing:
            resolved[entry_id] = existing
            continue
        action, target = decisions.get(entry_id, ("", ""))
        if not action:
            stats["unresolved"] += 1
            continue
        if cities is None:
            cities = city_index()
        city = twda_city(entry, cities)
        if action == "attach":
            resolved[entry_id] = target
            if await _settle_attachment(entry_id, target, city):
                stats["settled"] += 1
            continue
        tournament = reconstructed_tournament(entry, target, now, city)
        async with get_connection() as conn:
            tournament.event_code = await resolve_event_code(tournament, conn)
            await save_object_from_model(ObjectType.TOURNAMENT, tournament, conn=conn)
        resolved[entry_id] = tournament.uid
        stats["created"] += 1

    # A settled row whose entry left the archive — renamed upstream, or withdrawn.
    # Never auto-repaired: the row may hold a corrected result or a deck, and only
    # a human can tell a rename from a retraction.
    orphaned = sorted(set(known) - {e.id for e in entries})
    stats["orphaned"] = len(orphaned)
    if orphaned:
        logger.warning(
            f"TWDA sync: {len(orphaned)} rows carry an archive key the archive no "
            f"longer has, left alone for review: {orphaned[:20]}"
        )

    stats["decks_created"], stale, deck_winners = await _import_decks(
        entries, resolved, now
    )
    stats["stale_targets"] = len(stale)

    # A reconstruction enters the Hall of Fame only once its winner's deck lands,
    # so this follows the deck pass — and stays here, ahead of the backfill
    # regenerating the snapshot a later win list would miss.
    await recompute_wins(deck_winners)
    if stale:
        logger.warning(
            f"TWDA sync: {len(stale)} decisions name tournaments we do not hold "
            f"and have never settled — regenerate the decisions file: {stale[:20]}"
        )
    logger.info(f"TWDA sync: {stats}")
    return stats


async def _import_decks(
    entries: list[TwdaEntry],
    resolved: dict[str, str],
    now: datetime,
) -> tuple[int, list[str], set[str]]:
    """(decks created, decisions whose target we no longer hold, winners touched).

    One winner decklist per resolved event that does not already have one.
    `DeckObject.user_uid` is required and load-bearing in three indexes, so an
    entry whose winner we could not resolve gets no deck at all rather than an
    orphan owned by nobody.
    """
    uids = list(resolved.values())
    winners = await _winners_by_tournament_uid(uids)
    existing = await _deck_owners_by_tournament(uids)
    created = 0
    stale: list[str] = []
    touched: set[str] = set()
    for entry in entries:
        entry_id = entry.id
        tournament_uid = resolved.get(entry_id)
        if not tournament_uid:
            continue
        row = winners.get(tournament_uid)
        if not row:
            stale.append(entry_id)
            continue
        winner_uid = row[0]
        cards = _flatten_twda_cards(entry)
        if not winner_uid or not cards:
            continue
        if winner_uid in existing.get(tournament_uid, ()):
            continue
        deck = DeckObject(
            uid=str(uuid7()),
            modified=now,
            tournament_uid=tournament_uid,
            user_uid=winner_uid,
            name=entry.name,
            comments=entry.comment,
            cards=cards,
            attribution=DeckAttribution(kind=AttributionKind.OWNER),
            public=True,
            winner=True,
            finalist=True,
        )
        await save_deck(deck, row[2], row[1])
        created += 1
        touched.add(winner_uid)
    return created, stale, touched


async def _fetch_twda() -> list[TwdaEntry]:
    async with http_client.session().get(
        TWDA_URL, timeout=aiohttp.ClientTimeout(total=120.0)
    ) as resp:
        resp.raise_for_status()
        entries = msgspec.json.decode(await resp.read(), type=dict[str, TwdaEntry])
        return list(entries.values())
