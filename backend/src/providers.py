"""Deck URL providers: fetch deck data from VDB, VTESDecks, Amaranth."""

import json
import logging
import urllib.parse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class DeckFetchError(Exception):
    pass


def fetch_deck_from_url(url: str) -> dict:
    """Fetch deck cards from a supported deckbuilding URL.

    Returns dict: { "name": str, "author": str, "comments": str, "cards": { card_id_str: count } }
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc in {"vdb.smeea.casa", "vdb.im"}:
        return _fetch_vdb(parsed)
    elif parsed.netloc == "vtesdecks.com" or parsed.netloc == "api.vtesdecks.com":
        return _fetch_vtesdecks(parsed)
    elif parsed.netloc == "amaranth.vtes.co.nz":
        return _fetch_amaranth(parsed)
    else:
        raise DeckFetchError(f"Unsupported deck URL provider: {parsed.netloc}")


def _fetch_vdb(parsed: urllib.parse.ParseResult) -> dict:
    """Fetch from VDB (vdb.im)."""
    # URL formats:
    # vdb.im/decks?id=DECK_ID
    # vdb.im/decks/DECK_ID
    # vdb.im/decks/deck?name=X&author=Y#card_id=count;...
    params = urllib.parse.parse_qs(parsed.query)

    if parsed.fragment:
        # Inline deck in URL fragment
        cards = {}
        for item in parsed.fragment.split(";"):
            if "=" not in item:
                continue
            card_id, count = item.split("=", 1)
            cards[card_id] = int(count)
        return {
            "name": params.get("name", [""])[0],
            "author": params.get("author", [""])[0],
            "comments": params.get("description", [""])[0],
            "cards": cards,
        }

    # API fetch
    deck_id = params.get("id", [None])[0]
    if not deck_id and parsed.path.startswith("/decks/"):
        deck_id = parsed.path[7:]
    if not deck_id:
        raise DeckFetchError("Cannot extract VDB deck ID from URL")

    req = Request(f"https://vdb.im/api/deck/{deck_id}")
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    cards = {
        str(cid): int(count)
        for cid, count in data.get("cards", {}).items()
        if int(count) > 0
    }
    return {
        "name": data.get("name", ""),
        "author": data.get("author", data.get("owner", "")),
        "comments": data.get("description", ""),
        "cards": cards,
    }


def _fetch_vtesdecks(parsed: urllib.parse.ParseResult) -> dict:
    """Fetch from VTESDecks."""
    if not parsed.path.startswith("/deck/"):
        raise DeckFetchError("Unknown VTESDecks URL path")
    deck_id = parsed.path[6:]

    req = Request(f"https://api.vtesdecks.com/1.0/decks/{deck_id}")
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    cards = {}
    for card in data.get("crypt", []) + data.get("library", []):
        count = int(card.get("number", 0))
        if count > 0:
            cards[str(card["id"])] = count

    return {
        "name": data.get("name", ""),
        "author": data.get("author", ""),
        "comments": data.get("description", ""),
        "cards": cards,
    }


def _fetch_amaranth(parsed: urllib.parse.ParseResult) -> dict:
    """Fetch from Amaranth."""
    if not parsed.fragment.startswith("deck/"):
        raise DeckFetchError("Unknown Amaranth URL format")
    deck_id = parsed.fragment[5:]

    req = Request(
        "https://amaranth.vtes.co.nz/api/deck",
        data=f"id={deck_id}".encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    result = data.get("result", {})
    # Amaranth uses its own card IDs; we need the VEKN mapping
    # For now store as-is; the backend will need to map these
    cards = {
        str(cid): int(count)
        for cid, count in result.get("cards", {}).items()
        if int(count) > 0
    }
    return {
        "name": result.get("title", ""),
        "author": result.get("author", ""),
        "comments": result.get("description", ""),
        "cards": cards,
    }
