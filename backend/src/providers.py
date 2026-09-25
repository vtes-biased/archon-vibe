"""Deck URL providers: fetch + resolve deck data from VDB, VTESDecks, Amaranth."""

import asyncio
import itertools
import logging
import urllib.parse
from typing import Any

import aiohttp
import msgspec
from krcg import loader, providers

from . import http_client
from .card_data import cards_json_bytes

logger = logging.getLogger(__name__)


class DeckFetchError(Exception):
    def __init__(self, message: str, code: str, params: dict[str, str] | None = None):
        super().__init__(message)
        self.code = code
        self.params = params or {}


_known_ids: frozenset[int] | None = None
# amaranth_id -> VEKN id. Its /api/cards catalog is ~4k rows, so fetch it once and
# reuse; the lock keeps concurrent imports from double-fetching.
_amaranth_ids: dict[str, int] | None = None
_amaranth_lock = asyncio.Lock()

# Legacy/alternate hostnames. Only the netloc is remapped for routing.
_NETLOC_ALIASES = {
    "vdb.smeea.casa": "vdb.im",
    "api.vtesdecks.com": "vtesdecks.com",
}


def _card_ids() -> frozenset[int]:
    global _known_ids
    if _known_ids is None:
        data = cards_json_bytes()
        if data is None:
            raise RuntimeError("card database unavailable")
        _known_ids = frozenset(msgspec.json.decode(data, type=dict[int, msgspec.Raw]))
    return _known_ids


async def _amaranth_map(session: aiohttp.ClientSession) -> dict[str, int]:
    global _amaranth_ids
    if _amaranth_ids is None:
        async with _amaranth_lock:
            if _amaranth_ids is None:
                cards = await asyncio.to_thread(loader.load)
                by_card = await providers.get_amaranth_cards_map(session, cards)
                _amaranth_ids = {aid: card.id for aid, card in by_card.items()}
    return _amaranth_ids


def _deck(data: dict[str, Any], name_key: str) -> dict:
    return {
        "name": data.get(name_key) or "",
        "comments": data.get("description") or "",
        "cards": {},
    }


def _add(deck: dict, vekn_id: int, count: Any) -> None:
    count = int(count)
    if count <= 0:
        return
    if vekn_id not in _card_ids():
        raise KeyError(vekn_id)
    deck["cards"][str(vekn_id)] = count


async def _get_json(session: aiohttp.ClientSession, url: str) -> Any:
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.json()


async def _fetch_vdb(
    session: aiohttp.ClientSession, url: urllib.parse.ParseResult
) -> dict:
    params = urllib.parse.parse_qs(url.query)
    if "id" in params:
        uid = params["id"][0]
    elif url.path == "/decks/deck":
        if not url.fragment:
            raise ValueError("Empty VDB deck in URL")
        deck = {
            "name": params.get("name", [""])[0],
            "comments": params.get("description", [""])[0],
            "cards": {},
        }
        for item in url.fragment.split(";"):
            cid, count = item.split("=", 1)
            _add(deck, int(cid), count)
        return deck
    elif url.path.startswith("/decks/"):
        uid = url.path[7:]
    else:
        raise ValueError("Unknown VDB URL path")
    data = await _get_json(session, "https://vdb.im/api/deck/" + uid)
    deck = _deck(data, "name")
    for cid, count in data["cards"].items():
        _add(deck, int(cid), count)
    return deck


async def _fetch_vtesdecks(
    session: aiohttp.ClientSession, url: urllib.parse.ParseResult
) -> dict:
    if not url.path.startswith("/deck/"):
        raise ValueError("Invalid URL")
    data = await _get_json(
        session, "https://api.vtesdecks.com/1.0/decks/" + url.path[6:]
    )
    deck = _deck(data, "name")
    for card in itertools.chain(data["crypt"], data["library"]):
        _add(deck, int(card["id"]), card["number"])
    return deck


async def _fetch_amaranth(
    session: aiohttp.ClientSession, url: urllib.parse.ParseResult
) -> dict:
    # a hash-routed SPA: share URLs carry the deck in the fragment (#deck/<uid>)
    path = "/" + url.fragment if url.fragment.startswith("deck/") else url.path
    if not path.startswith("/deck/"):
        raise ValueError("Invalid URL")
    ids = await _amaranth_map(session)
    data = await _get_json(
        session, "https://amaranth.vtes.co.nz/api/deck?id=" + path[6:]
    )
    if not data.get("success"):
        raise ValueError(f"Amaranth: {data.get('error', {}).get('message')}")
    result = data["result"]
    deck = _deck(result, "title")
    for cid, count in result["cards"].items():
        _add(deck, ids[cid], count)
    return deck


async def fetch_deck_from_url(url: str) -> dict:
    """Fetch + resolve a deck from a supported deckbuilding URL.

    Returns ``{"name", "comments", "cards": {vekn_id_str: count}}`` with
    all card ids resolved to VEKN ids.
    """
    parsed = urllib.parse.urlparse(url)
    netloc = _NETLOC_ALIASES.get(parsed.netloc, parsed.netloc)
    session = http_client.session()
    try:
        if netloc == "amaranth.vtes.co.nz":
            return await _fetch_amaranth(session, parsed)
        elif netloc == "vdb.im":
            return await _fetch_vdb(session, parsed)
        elif netloc == "vtesdecks.com":
            return await _fetch_vtesdecks(session, parsed)
        else:
            raise DeckFetchError(
                f"Unsupported deck URL provider: {parsed.netloc}",
                "deck_fetch.bad_link",
            )
    except DeckFetchError:
        raise
    except KeyError as e:
        # A referenced card id isn't in the card DB (unknown/storyline/counter card).
        raise DeckFetchError(
            f"Deck references an unknown card ({e})", "deck_fetch.bad_link"
        ) from e
    except ValueError as e:
        raise DeckFetchError(
            f"Could not read the deck at {parsed.netloc}: {e}", "deck_fetch.bad_link"
        ) from e
    except (aiohttp.ClientError, TimeoutError) as e:
        if isinstance(e, aiohttp.ClientResponseError) and 400 <= e.status < 500:
            raise DeckFetchError(
                f"{parsed.netloc} refused the deck link: {e.status} {e.message}",
                "deck_fetch.bad_link",
            ) from e
        raise DeckFetchError(
            f"Could not fetch deck from {parsed.netloc}: {e}",
            "deck_fetch.provider_unavailable",
            {"provider": netloc},
        ) from e
