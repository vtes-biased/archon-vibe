#!/usr/bin/env python3
"""Audit VEKN cities against geonames database.

Fetches all VEKN members and checks whether their city (after FIX_CITIES
corrections) resolves against the geonames city database.

Usage:
    python3 -m scripts.audit_cities

Requires VEKN_API_USERNAME and VEKN_API_PASSWORD environment variables.
"""

import asyncio
import sys
from collections import Counter, defaultdict

# Ensure package imports work when run from backend/
sys.path.insert(0, ".")

from src.geonames import load_countries, match_city  # noqa: E402
from src.vekn_api import VEKNAPIClient  # noqa: E402
from src.vekn_sync import FIX_CITIES  # noqa: E402


def _country_name_to_code() -> dict[str, str]:
    """Build country name -> ISO code mapping."""
    countries = load_countries()
    return {c["name"]: code for code, c in countries.items()}


async def main() -> None:
    name_to_code = _country_name_to_code()

    print("Fetching all VEKN members...")
    client = VEKNAPIClient()
    try:
        players = await client.fetch_all_members()
    finally:
        await client.close()
    print(f"Fetched {len(players)} members\n")

    matched = 0
    matched_after_fix = 0
    unmatched_cities: dict[str, list[tuple[str, int]]] = defaultdict(list)
    no_city = 0
    no_country = 0
    stale_fixes: list[tuple[str, str, str]] = []  # (country, src, target)

    for player in players:
        city_raw = player.get("city") or ""
        city_raw = city_raw.strip()
        country_name = player.get("countryname") or ""
        country_code = player.get("countrycode") or ""

        if not city_raw:
            no_city += 1
            continue
        if not country_code:
            no_country += 1
            continue

        # Apply FIX_CITIES
        city = city_raw
        was_fixed = False
        if country_name in FIX_CITIES:
            fixed = FIX_CITIES[country_name].get(city)
            if fixed:
                city = fixed
                was_fixed = True

        result = match_city(city, country_code)
        if result:
            if was_fixed:
                matched_after_fix += 1
            else:
                matched += 1
        else:
            unmatched_cities[country_name].append((city_raw if not was_fixed else f"{city_raw} -> {city}", 1))

    # Aggregate unmatched by (country, city)
    unmatched_agg: dict[str, Counter] = defaultdict(Counter)
    for country, entries in unmatched_cities.items():
        for city_label, count in entries:
            unmatched_agg[country][city_label] += count

    total_unmatched = sum(sum(c.values()) for c in unmatched_agg.values())

    # Check stale FIX_CITIES entries (targets that don't resolve)
    for country_name, fixes in FIX_CITIES.items():
        cc = name_to_code.get(country_name)
        if not cc:
            stale_fixes.append((country_name, "*", f"unknown country: {country_name}"))
            continue
        for src, target in fixes.items():
            if not match_city(target, cc):
                stale_fixes.append((country_name, src, target))

    # --- Report ---
    print("=" * 70)
    print("CITY AUDIT REPORT")
    print("=" * 70)
    print(f"Total members:       {len(players)}")
    print(f"No city:             {no_city}")
    print(f"No country code:     {no_country}")
    print(f"Matched directly:    {matched}")
    print(f"Matched after fix:   {matched_after_fix}")
    print(f"Unmatched:           {total_unmatched}")
    print()

    if stale_fixes:
        print("-" * 70)
        print(f"STALE FIX_CITIES ENTRIES ({len(stale_fixes)} targets don't resolve):")
        print("-" * 70)
        for country, src, target in sorted(stale_fixes):
            print(f"  {country}: {src!r} -> {target!r}")
        print()

    if unmatched_agg:
        print("-" * 70)
        print("UNMATCHED CITIES BY COUNTRY:")
        print("-" * 70)
        for country in sorted(unmatched_agg):
            cities = unmatched_agg[country]
            total = sum(cities.values())
            print(f"\n  {country} ({total} users):")
            for city_label, count in cities.most_common():
                print(f"    {city_label} ({count})")


if __name__ == "__main__":
    asyncio.run(main())
