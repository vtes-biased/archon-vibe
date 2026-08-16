"""Reconstruct historic tournaments from the TWDA, and import winner decklists.

The archive is the only record of roughly a quarter of the events we hold wins
for: it only began carrying vekn.net event links around 2013, so everything older
reaches us through `backend/src/data/twda_decisions.tsv`, a reviewed mapping from
archive entry to either one of our tournaments or a reconstruction of one.

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

from .broadcast import broadcast_precomputed
from .data.timezones import CITY_TZ_OVERRIDES, COUNTRY_TIMEZONE
from .db import get_connection, save_object_from_model
from .geonames import normalize_country
from .models import (
    DeckObject,
    ObjectType,
    Player,
    PlayerState,
    Standing,
    Tournament,
    TournamentFormat,
    TournamentState,
)

logger = logging.getLogger(__name__)

TWDA_URL = "https://static.krcg.org/data/twda.json"
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def extract_vekn_event_id(entry: dict) -> str | None:
    """Extract VEKN event ID from a TWDA entry.

    Recent entries have numeric `id` matching VEKN event IDs.
    Older entries have alphanumeric `id` but `event_link` contains the VEKN ID.
    """
    entry_id = str(entry.get("id", ""))
    if entry_id.isdigit():
        return entry_id
    # Fall back to extracting from event_link URL
    link = entry.get("event_link", "")
    if "/event/" in link:
        return link.rsplit("/event/", 1)[-1].split("/")[0].split("?")[0]
    return None


def _flatten_twda_cards(entry: dict) -> dict[str, int]:
    """Flatten TWDA crypt/library dicts into {card_id_str: count}.

    Crypt: {count, cards: [{id, count, name}, ...]}
    Library: {count, cards: [{type, count, cards: [{id, count, name}, ...]}, ...]}
    """
    cards: dict[str, int] = {}
    # Crypt cards are flat
    for card in entry.get("crypt", {}).get("cards", []):
        card_id = card.get("id")
        if card_id is not None:
            cards[str(card_id)] = card.get("count", 1)
    # Library cards are nested by type
    for group in entry.get("library", {}).get("cards", []):
        for card in group.get("cards", []):
            card_id = card.get("id")
            if card_id is not None:
                cards[str(card_id)] = card.get("count", 1)
    return cards


async def _get_decks_by_tournament_uids(
    uids: list[str],
) -> dict[str, list[DeckObject]]:
    """Get existing decks grouped by tournament_uid."""
    if not uids:
        return {}
    decoder = msgspec.json.Decoder(DeckObject)
    result: dict[str, list[DeckObject]] = {}
    async with get_connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT "full"::text FROM objects
                WHERE type = %s
                  AND "full"->>'tournament_uid' = ANY(%s)
                  AND deleted_at IS NULL""",
                (ObjectType.DECK, uids),
            )
        ).fetchall()
    for row in rows:
        d = decoder.decode(row[0].encode())
        result.setdefault(d.tournament_uid, []).append(d)
    return result


def load_decisions() -> dict[str, tuple[str, str]]:
    """twda entry id -> (action, target), from the reviewed decisions file.

    Actions are `attach` (target is one of our tournament uids) and `create`
    (target is the winning member's uid). Everything else in the file is an
    undecided line and is deliberately absent from the result, so the caller
    counts it as unresolved rather than acting on it.
    """
    text = (
        importlib.resources.files("backend.src.data")
        .joinpath("twda_decisions.tsv")
        .read_text()
    )
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
    """Best-effort IANA zone for an archive `place`. A local copy of the venue
    sync's: that reads vekn.net venue records, this reads a "City (STATE),
    Country" string, and the two sources part company when the API retires."""
    if not country:
        return "UTC"
    country = country.upper()
    for cc, override_city, tz in CITY_TZ_OVERRIDES:
        if cc == country and override_city.lower() in city.lower():
            return tz
    return COUNTRY_TIMEZONE.get(country, "UTC")


def _twda_place(entry: dict) -> tuple[str | None, str]:
    """(ISO country, city) from `place` — "City (STATE), Country"."""
    place = (entry.get("place") or "").strip()
    if not place:
        return None, ""
    head, _, tail = place.rpartition(",")
    country = normalize_country(tail) if head else None
    return country, head.split("(")[0].strip()


def reconstructed_tournament(entry: dict, winner_uid: str, now: datetime) -> Tournament:
    """The canonical rounds-less archival shape, as the VEKN and archon imports
    already write it — with the attested field size the archive supplies.

    The winner's `Player` row is not decoration: without it the tournament page
    renders the winner as a raw uid, the organizer roster reads empty against a
    populated member view, and the wins refresh never fires. Scores stay zero
    because the archive's is a total including the final, while `standings` is
    prelim-only by contract — splitting it would plant a guess where later
    arithmetic trusts a measurement.
    """
    country, city = _twda_place(entry)
    day = entry.get("date", "")
    start = datetime.strptime(day, "%Y-%m-%d") if _ISO_DATE_RE.match(day) else None
    rounds = re.match(r"\s*(\d+)", str(entry.get("tournament_format") or ""))
    return Tournament(
        uid=str(uuid7()),
        modified=now,
        name=entry.get("event") or f"VTES Tournament — {city or country or day}",
        format=TournamentFormat.Standard,
        online=(entry.get("place") or "").strip().lower() == "online",
        start=start,
        finish=start,
        timezone=_twda_timezone(country, city),
        country=country,
        state=TournamentState.FINISHED,
        max_rounds=int(rounds.group(1)) if rounds else 0,
        # The archive's own file key. Never `vekn`: these have no vekn.net row,
        # and never `vekn_pushed_at`, which would mean "we exchanged results with
        # vekn.net" and would permanently block deleting a bad reconstruction.
        external_ids={"twda": str(entry.get("id", ""))},
        players=[
            Player(user_uid=winner_uid, state=PlayerState.FINISHED, finalist=True)
        ],
        standings=[Standing(user_uid=winner_uid, finalist=True)],
        winner=winner_uid,
        # The only field that survives to say how big this was. `players_count`
        # is absent on ~100 entries; 0 there means "unattested", same as anywhere.
        reported_player_count=int(entry.get("players_count") or 0),
    )


async def _tournaments_by_twda_id() -> dict[str, str]:
    """twda entry id -> our tournament uid, for everything already reconstructed."""
    async with get_connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT "full"->'external_ids'->>'twda', uid FROM objects
                WHERE type = %s
                  AND "full"->'external_ids'->>'twda' IS NOT NULL
                  AND deleted_at IS NULL""",
                (ObjectType.TOURNAMENT,),
            )
        ).fetchall()
    return {row[0]: row[1] for row in rows}


async def _winners_by_tournament_uid(uids: list[str]) -> dict[str, tuple[str, list]]:
    """uid -> (winner uid, organizer uids) for the tournaments a deck may attach to."""
    if not uids:
        return {}
    async with get_connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT uid, "full"->>'winner',
                          coalesce("full"->'organizers_uids', '[]'::jsonb)
                   FROM objects
                   WHERE type = %s AND uid = ANY(%s) AND deleted_at IS NULL""",
                (ObjectType.TOURNAMENT, uids),
            )
        ).fetchall()
    return {row[0]: (row[1] or "", list(row[2] or [])) for row in rows}


async def run_twda_sync(*, broadcast: bool = True) -> dict[str, int]:
    """Reconcile the whole archive against our corpus: reconstruct what the
    decisions file says we lack, then give every resolved winner their decklist.

    Deliberately no ETag. Once identities are attached from a reviewed file, OUR
    side moves while the archive sits still — a member is created, renamed, or
    claims a VEKN id — and a 304 short-circuit would skip the reconciliation
    forever, silently and permanently. A 12 MB fetch against a static CDN is the
    cheaper half of that trade.

    `broadcast=False` is for the one-time backfill: pushing a thousand object
    frames at every connected client in a tight loop is a burst the recurring
    delta never produces.
    """
    entries = await _fetch_twda()
    decisions = load_decisions()
    known = await _tournaments_by_twda_id()
    now = datetime.now(UTC)

    stats = {
        "entries": len(entries),
        "created": 0,
        "unresolved": 0,
        "decks_created": 0,
    }
    # entry id -> (our tournament uid, winner uid or "" when the row knows its own)
    resolved: dict[str, tuple[str, str]] = {}

    for entry in entries:
        entry_id = str(entry.get("id", ""))
        action, target = decisions.get(entry_id, ("", ""))
        if not action:
            stats["unresolved"] += 1
            continue
        if action == "attach":
            resolved[entry_id] = (target, "")
            continue
        existing = known.get(entry_id)
        if existing:
            resolved[entry_id] = (existing, target)
            continue
        tournament = reconstructed_tournament(entry, target, now)
        bd = await save_object_from_model(ObjectType.TOURNAMENT, tournament)
        if broadcast:
            broadcast_precomputed(bd)
        resolved[entry_id] = (tournament.uid, target)
        stats["created"] += 1

    stats["decks_created"] = await _import_decks(entries, resolved, now, broadcast)
    logger.info(f"TWDA sync: {stats}")
    return stats


async def _import_decks(
    entries: list[dict],
    resolved: dict[str, tuple[str, str]],
    now: datetime,
    broadcast: bool,
) -> int:
    """One winner decklist per resolved event that does not already have one.

    `DeckObject.user_uid` is required and load-bearing in three indexes, so an
    entry whose winner we could not resolve gets no deck at all rather than an
    orphan owned by nobody.
    """
    uids = [uid for uid, _ in resolved.values()]
    winners = await _winners_by_tournament_uid(uids)
    existing = await _get_decks_by_tournament_uids(uids)
    created = 0
    for entry in entries:
        entry_id = str(entry.get("id", ""))
        target = resolved.get(entry_id)
        if not target:
            continue
        tournament_uid, winner_uid = target
        row = winners.get(tournament_uid)
        if not row:
            continue
        winner_uid = winner_uid or row[0]
        cards = _flatten_twda_cards(entry)
        if not winner_uid or not cards:
            continue
        if any(d.user_uid == winner_uid for d in existing.get(tournament_uid, [])):
            continue
        deck = DeckObject(
            uid=str(uuid7()),
            modified=now,
            tournament_uid=tournament_uid,
            user_uid=winner_uid,
            name=entry.get("name", ""),
            author=entry.get("player", ""),
            comments=entry.get("comments", ""),
            cards=cards,
            attribution="twda",
            public=True,
        )
        bd = await save_object_from_model(ObjectType.DECK, deck)
        bd.org_uids = row[1]
        if broadcast:
            broadcast_precomputed(bd)
        created += 1
    return created


async def _fetch_twda() -> list[dict]:
    timeout = aiohttp.ClientTimeout(total=120.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(TWDA_URL) as resp:
            resp.raise_for_status()
            # content_type=None: static.krcg.org may not serve application/json.
            return await resp.json(content_type=None)
