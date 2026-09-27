"""One-time fill of the tournament city across the corpus.

    # lists each event's chosen city and source; --apply is the only thing that writes
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/backfill_tournament_cities.py
    … backfill_tournament_cities.py --apply

Regenerates the snapshot at the end rather than broadcasting each row.
Idempotent: a row that already carries a city is skipped.
"""

import argparse
import asyncio
import importlib.util
import os
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.src import db, http_client  # noqa: E402
from backend.src.geonames import (  # noqa: E402
    City,
    CityIndex,
    city_index,
    match_city,
)
from backend.src.models import Tournament  # noqa: E402
from backend.src.snapshots import generate_snapshots  # noqa: E402
from backend.src.twda_import import _fetch_twda, twda_city  # noqa: E402
from backend.src.vekn_sync import fix_city  # noqa: E402

_POSTCODE = re.compile(r"\b[\w-]*\d[\w-]*\b")


def _address_city(t: Tournament, cities: CityIndex) -> City | None:
    for segment in reversed(re.split(r"[,\r\n]", t.address)):
        for name in (segment, _POSTCODE.sub(" ", segment)):
            name = " ".join(name.split())
            name = fix_city(name, t.country or "")
            if city := match_city(cities, name, t.country or ""):
                return city
    return None


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        async with db.get_connection() as conn:
            result = await conn.execute(
                """SELECT "full" FROM objects
                   WHERE type = 'tournament' AND deleted_at IS NULL
                     AND ("full"->>'online') IS DISTINCT FROM 'true'
                     AND "full"->>'city_geoname_id' IS NULL
                   ORDER BY "full"->>'start'"""
            )
            rows = await result.fetchall()
        entries = {e.id: e for e in await _fetch_twda()}
        cities = city_index()

        chosen: dict[str, tuple[City, str]] = {}
        sources: Counter[str] = Counter()
        for (full,) in rows:
            t = db.decode_json(full, Tournament)
            if not t.country:
                sources["no country"] += 1
                continue
            key = t.external_ids.get("twda_entry") or t.external_ids.get("twda")
            entry = entries.get(key or "")
            archived = twda_city(entry, cities) if entry else None
            if archived and archived["country_code"].upper() != t.country.upper():
                archived = None
            if city := _address_city(t, cities):
                source = "venue"
            elif city := archived:
                source = "twda"
            else:
                sources["unmatched"] += 1
                print(f"{'-':<8} {t.country}  {t.event_code or t.uid:<12} {t.name}")
                print(
                    f"{'':<11} address: {t.address!r}, twda: {entry.place if entry else ''!r}"
                )
                continue
            sources[source] += 1
            chosen[t.uid] = (city, source)
            print(
                f"{source:<8} {t.country}  {t.event_code or t.uid:<12} "
                f"{city['name']:<24} {t.name}"
            )
        print(f"\n{len(rows)} in-person tournaments without a city: {dict(sources)}")
        if not args.apply:
            print("\nReport only — pass --apply to write.")
            return 0

        written = 0
        for uid, (city, _source) in chosen.items():
            async with db.tournament_transaction(uid) as (fresh, tx_conn):
                if not fresh or fresh.city_geoname_id or fresh.online:
                    continue
                fresh.city = city["name"]
                fresh.city_geoname_id = city["geoname_id"]
                fresh.modified = datetime.now(UTC)
                await db.save_tournament(fresh, conn=tx_conn)
                written += 1
        print(f"\n{written} written")

        print("\nRegenerating snapshots...")
        print(await generate_snapshots())
        return 0
    finally:
        await http_client.close()
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument(
        "--apply", action="store_true", help="write; without it, report only"
    )
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
