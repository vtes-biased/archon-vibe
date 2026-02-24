#!/usr/bin/env python3
"""Fetch VEKN CSV card data and produce engine/data/cards.json.

Downloads vtescrypt.csv and vteslib.csv from static.krcg.org,
parses them, and outputs a JSON file keyed by card ID.
"""

import json
from pathlib import Path
from urllib.request import urlopen

KRCG_BASE = "https://static.krcg.org/data/vtes.json"
OUTPUT = Path(__file__).resolve().parent.parent / "engine" / "data" / "cards.json"


def fetch_vtes_json() -> list[dict]:
    """Fetch the full VTES card database from krcg static server."""
    print(f"Fetching {KRCG_BASE}...")
    with urlopen(KRCG_BASE) as resp:
        return json.loads(resp.read())


def card_type_kind(types: list[str]) -> str:
    """Determine if card is 'crypt' or 'library'."""
    crypt_types = {"Vampire", "Imbued"}
    if any(t in crypt_types for t in types):
        return "crypt"
    return "library"


def extract_cost(card: dict) -> dict | None:
    """Extract cost info from card data."""
    # Library cards may have pool/blood/conviction cost in card_text
    # The vtes.json doesn't have explicit cost fields, parse from _set or text
    # Actually vtes.json doesn't expose cost directly - we'll skip for now
    # and add if needed
    return None


def transform_card(card: dict) -> dict:
    """Transform a vtes.json card entry to our simplified format."""
    types = card.get("types", [])
    kind = card_type_kind(types)
    result = {
        "id": card["id"],
        "name": card.get("name", card.get("printed_name", "")),
        "printed_name": card.get("printed_name", ""),
        "types": types,
        "kind": kind,
    }
    if kind == "crypt":
        result["disciplines"] = card.get("disciplines", [])
        result["clan"] = card.get("clans", [""])[0] if card.get("clans") else ""
        result["group"] = card.get("group", "")
        result["capacity"] = card.get("capacity", 0)
        result["adv"] = card.get("adv", False)
    else:
        result["disciplines"] = card.get("disciplines", [])
        result["clan"] = ""
        result["group"] = ""
        result["capacity"] = 0

    result["banned"] = card.get("banned", "")
    # Collect set codes
    result["sets"] = list(card.get("sets", {}).keys())
    # Name variants for lookup
    result["name_variants"] = card.get("name_variants", [])
    return result


def main():
    cards = fetch_vtes_json()
    print(f"Fetched {len(cards)} cards")

    output = {}
    for card in cards:
        transformed = transform_card(card)
        output[str(transformed["id"])] = transformed

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Wrote {len(output)} cards to {OUTPUT} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
