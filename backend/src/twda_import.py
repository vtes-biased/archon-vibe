"""Import winner decklists from TWDA (static.krcg.org) into matching tournaments."""

import logging
from datetime import UTC, datetime

import httpx
import msgspec
from uuid6 import uuid7

from .broadcast import broadcast_precomputed
from .db import get_connection, save_object_from_model
from .models import DeckObject, ObjectType, Tournament

logger = logging.getLogger(__name__)

TWDA_URL = "https://static.krcg.org/data/twda.json"
_last_etag: str | None = None


def _extract_vekn_event_id(entry: dict) -> str | None:
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


async def _get_tournaments_by_vekn_ids(
    vekn_ids: list[str],
) -> dict[str, Tournament]:
    """Get finished tournaments with a winner, keyed by VEKN event ID."""
    if not vekn_ids:
        return {}
    decoder = msgspec.json.Decoder(Tournament)
    result: dict[str, Tournament] = {}
    async with get_connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT "full"::text FROM objects
                WHERE type = %s
                  AND "full"->'external_ids'->>'vekn' = ANY(%s)
                  AND "full"->>'winner' != ''
                  AND deleted_at IS NULL""",
                (ObjectType.TOURNAMENT, vekn_ids),
            )
        ).fetchall()
    for row in rows:
        t = decoder.decode(row[0].encode())
        vekn_id = t.external_ids.get("vekn")
        if vekn_id:
            result[vekn_id] = t
    return result


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


async def import_twda_decks() -> dict[str, int]:
    """Fetch TWDA data and import winner decklists for matching tournaments.

    Returns stats dict with counts of processed/created/skipped.
    """
    global _last_etag

    # 1. Fetch with ETag
    headers: dict[str, str] = {}
    if _last_etag:
        headers["If-None-Match"] = _last_etag

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(TWDA_URL, headers=headers)

    if resp.status_code == 304:
        logger.info("TWDA data unchanged (304)")
        return {"status": "unchanged"}

    resp.raise_for_status()
    _last_etag = resp.headers.get("ETag")

    # 2. Parse & build compact lookup
    raw_entries: list[dict] = resp.json()
    twda_lookup: dict[str, dict] = {}
    for entry in raw_entries:
        event_id = _extract_vekn_event_id(entry)
        if not event_id:
            continue
        twda_lookup[event_id] = {
            "name": entry.get("name", ""),
            "player": entry.get("player", ""),
            "comments": entry.get("comments", ""),
            "cards": _flatten_twda_cards(entry),
        }
    del raw_entries  # release ~12MB

    if not twda_lookup:
        return {"twda_entries": 0, "created": 0}

    # 3. Find matching tournaments
    vekn_ids = list(twda_lookup.keys())
    tournaments = await _get_tournaments_by_vekn_ids(vekn_ids)

    if not tournaments:
        return {"twda_entries": len(twda_lookup), "matched": 0, "created": 0}

    # 4. Check existing decks
    t_uids = [t.uid for t in tournaments.values()]
    existing_decks = await _get_decks_by_tournament_uids(t_uids)

    # 5. Create missing winner decks
    now = datetime.now(UTC)
    created = 0
    skipped = 0

    for vekn_id, tournament in tournaments.items():
        twda = twda_lookup.get(vekn_id)
        if not twda or not twda["cards"]:
            skipped += 1
            continue

        # Skip if winner already has a deck for this tournament
        winner_uid = tournament.winner
        tournament_decks = existing_decks.get(tournament.uid, [])
        if any(d.user_uid == winner_uid for d in tournament_decks):
            skipped += 1
            continue

        deck = DeckObject(
            uid=str(uuid7()),
            modified=now,
            tournament_uid=tournament.uid,
            user_uid=winner_uid,
            name=twda["name"],
            author=twda["player"],
            comments=twda["comments"],
            cards=twda["cards"],
            attribution="twda",
            public=True,
        )
        bd = await save_object_from_model(ObjectType.DECK, deck)
        bd.org_uids = tournament.organizers_uids
        broadcast_precomputed(bd)
        created += 1

    return {
        "twda_entries": len(twda_lookup),
        "matched": len(tournaments),
        "created": created,
        "skipped": skipped,
    }
