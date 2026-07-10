"""Deck URL providers: fetch + resolve deck data from VDB, VTESDecks, Amaranth.

krcg does the fetching and, crucially, maps each provider's native card ids to VEKN
ids — notably Amaranth, whose API returns its own ids (storing them verbatim was the
original import bug). Resolution uses krcg's bundled card DB, independent of our
generated ``cards.json``.
"""

import asyncio
import logging
import urllib.parse

import aiohttp
from krcg import loader, providers
from krcg.collections import CardDict
from krcg.models import Card, Deck

logger = logging.getLogger(__name__)


class DeckFetchError(Exception):
    pass


# krcg's card DB, loaded once (offline pickle/local) and reused across requests.
_cards: CardDict | None = None
# Amaranth's amaranth_id -> Card map. Its /api/cards catalog is ~4k rows, so fetch it
# once and reuse; the lock keeps concurrent imports from double-fetching.
_amaranth_map: dict[str, Card] | None = None
_amaranth_lock = asyncio.Lock()

# Legacy/alternate hostnames krcg's own dispatcher doesn't recognize. Only the netloc
# is remapped for routing; the krcg fetchers key off path/query/fragment, not netloc.
_NETLOC_ALIASES = {
    "vdb.smeea.casa": "vdb.im",
    "api.vtesdecks.com": "vtesdecks.com",
}


def _cards_dict() -> CardDict:
    global _cards
    if _cards is None:
        _cards = loader.load()
    return _cards


async def _amaranth_cards_map(session: aiohttp.ClientSession) -> dict[str, Card]:
    global _amaranth_map
    if _amaranth_map is None:
        async with _amaranth_lock:
            if _amaranth_map is None:
                _amaranth_map = await providers.get_amaranth_cards_map(
                    session, _cards_dict()
                )
    return _amaranth_map


def _deck_to_dict(deck: Deck) -> dict:
    return {
        "name": deck.name or "",
        "author": deck.author or "",
        "comments": deck.comment or "",
        "cards": {str(c.id): c.count for c in deck.cards if c.count > 0},
    }


async def fetch_deck_from_url(url: str) -> dict:
    """Fetch + resolve a deck from a supported deckbuilding URL.

    Returns ``{"name", "author", "comments", "cards": {vekn_id_str: count}}`` with
    all card ids resolved to VEKN ids.
    """
    parsed = urllib.parse.urlparse(url)
    netloc = _NETLOC_ALIASES.get(parsed.netloc, parsed.netloc)
    cards = _cards_dict()
    try:
        async with aiohttp.ClientSession() as session:
            if netloc == "amaranth.vtes.co.nz":
                amap = await _amaranth_cards_map(session)
                deck = await providers.fetch_amaranth(
                    session, parsed, cards, amaranth_map=amap
                )
            elif netloc == "vdb.im":
                deck = await providers.fetch_vdb(session, parsed, cards)
            elif netloc == "vtesdecks.com":
                deck = await providers.fetch_vtesdecks(session, parsed, cards)
            else:
                raise DeckFetchError(f"Unsupported deck URL provider: {parsed.netloc}")
    except DeckFetchError:
        raise
    except KeyError as e:
        # A referenced card id isn't in krcg's DB (unknown/storyline/counter card).
        raise DeckFetchError(f"Deck references an unknown card ({e})") from e
    except (ValueError, aiohttp.ClientError) as e:
        raise DeckFetchError(f"Could not fetch deck from {parsed.netloc}: {e}") from e
    return _deck_to_dict(deck)
