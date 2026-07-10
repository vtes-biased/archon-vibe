#!/usr/bin/env python3
"""Build engine/data/cards.json from krcg's canonical card data.

Sources the VTES card database through krcg (the owner-maintained canonical
library) so the generated cards.json carries krcg's three name forms and its
computed name_variants — the data half of correct card-name resolution shared by
the Rust engine (offline text import) and the frontend:

- ``printed_name`` — bare name, for display (group/advanced shown as separate badges)
- ``unique_name``  — minimal disambiguator (most vampires bare; later groups /
  advanced get the suffix), for text decklist output
- ``full_name``    — always group/advanced suffixed
- ``name_variants``— accents, player-shorthand aliases and ordinals, all as parse keys

All three names plus the variants are lookup keys for the parser; the parser folds
accents so an ASCII-only spelling still resolves.
"""

import asyncio
import json
import os
from pathlib import Path

import aiohttp
from krcg import loader
from krcg.collections import CardDict
from krcg.models import Card

OUTPUT = Path(
    os.getenv("CARDS_JSON_OUT")
    or Path(__file__).resolve().parent.parent / "engine" / "data" / "cards.json"
)


def _group(card: Card) -> str:
    """Crypt group as a bare digit ("3"), "any" for group-independent, else ""."""
    g = getattr(card, "group", None)
    if g is None:
        return ""
    value = g.value  # "G1".."G7" or "Any"
    return "any" if value.lower() == "any" else value.lstrip("Gg")


def _disciplines(card: Card) -> list[str]:
    """Crypt disciplines (case-encodes level) or a library card's requirement."""
    if card.kind == Card.Kind.CRYPT:
        return list(card.disciplines)
    req = getattr(card, "discipline_requirement", None)
    return list(req.disciplines) if req else []


def _sets(card: Card, cards: CardDict) -> list[str]:
    """Distinct set names the card was printed in (for the engine's format checks)."""
    names: list[str] = []
    for print_ in card.prints:
        entry = cards.sets.get(print_.set.code) or cards.sets.get(print_.set.id)
        name = entry.name if entry else print_.set.code
        if name not in names:
            names.append(name)
    return names


def transform(card: Card, cards: CardDict) -> dict:
    """Project a krcg card to the engine's cards.json entry."""
    crypt = card.kind == Card.Kind.CRYPT
    return {
        "id": card.id,
        "printed_name": card.printed_name,
        "unique_name": card.unique_name,
        "full_name": card.full_name,
        "types": [t.value for t in card.types],
        "kind": "crypt" if crypt else "library",
        "img": card.url,
        "disciplines": _disciplines(card),
        "clan": getattr(card, "clan", "") or "",
        "group": _group(card) if crypt else "",
        "capacity": (card.capacity or 0) if crypt else 0,
        "adv": bool(getattr(card, "advanced", False)),
        "banned": card.banned.isoformat() if card.banned else "",
        "sets": _sets(card, cards),
        "name_variants": list(dict.fromkeys(nv.name for nv in card.name_variants)),
    }


async def _load() -> CardDict:
    async with aiohttp.ClientSession() as session:
        return await loader.load_online(session)


def main() -> None:
    cards = asyncio.run(_load())
    output = {str(c.id): transform(c, cards) for c in cards.cards()}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Wrote {len(output)} cards to {OUTPUT} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
