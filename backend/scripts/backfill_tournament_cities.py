"""One-time fill of the tournament city across the corpus.

    # lists each city and its source, then what stays empty; --apply writes
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/backfill_tournament_cities.py
    … backfill_tournament_cities.py --apply

`tournament_cities.json` beside this script maps uid -> [GeoNames id, country
or null, source]; the country is set only where the row had none.
Regenerates the snapshot at the end rather than broadcasting each row.
"""

import argparse
import asyncio
import importlib.util
import json
import os
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

from backend.src import db  # noqa: E402
from backend.src.geonames import City, load_cities, normalize_country  # noqa: E402
from backend.src.models import Tournament  # noqa: E402
from backend.src.snapshots import generate_snapshots  # noqa: E402

MAPPING = Path(__file__).with_name("tournament_cities.json")


def _verdict(t: Tournament | None, city: City | None, country: str | None) -> str:
    if city is None:
        return "unknown id"
    if t is None:
        return "gone"
    if t.online:
        return "online now"
    if t.city_geoname_id:
        return "has a city"
    cc = normalize_country(t.country or "") or country
    if cc != city["country_code"].upper():
        return "country differs"
    return "write"


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        mapping: dict[str, list] = json.loads(MAPPING.read_text())
        wanted = {geoname_id for geoname_id, _, _ in mapping.values()}
        cities = {
            c["geoname_id"]: c for c in load_cities() if c["geoname_id"] in wanted
        }

        verdicts: Counter[str] = Counter()
        for uid, (geoname_id, country, source) in mapping.items():
            city = cities.get(geoname_id)
            if not args.apply:
                t = await db.get_tournament_by_uid(uid)
                verdict = _verdict(t, city, country)
                verdicts[verdict] += 1
                if verdict == "write" and t and city:
                    print(
                        f"{source:<14} {t.country or country}  "
                        f"{city['name']:<24} {t.name}"
                    )
                elif verdict != "has a city":
                    print(f"{verdict:<14} {uid}  {t.name if t else ''}")
                continue
            async with db.tournament_transaction(uid) as (t, tx_conn):
                verdict = _verdict(t, city, country)
                verdicts[verdict] += 1
                if verdict != "write" or t is None or city is None:
                    continue
                if t.country in (None, "", "XX"):
                    t.country = city["country_code"].upper()
                t.city = city["name"]
                t.city_geoname_id = geoname_id
                t.modified = datetime.now(UTC)
                await db.save_tournament(t, conn=tx_conn)

        async with db.get_connection() as conn:
            result = await conn.execute(
                """SELECT "full"->>'uid', "full"->>'country', "full"->>'name',
                          "full"->>'address' FROM objects
                   WHERE type = 'tournament' AND deleted_at IS NULL
                     AND ("full"->>'online') IS DISTINCT FROM 'true'
                     AND "full"->>'city_geoname_id' IS NULL
                   ORDER BY "full"->>'start'"""
            )
            left = [row for row in await result.fetchall() if row[0] not in mapping]
        print("\nIn person, no city, and nothing mapped:")
        for uid, country, name, address in left:
            print(f"  {country or '--'}  {uid}  {name}  address: {address!r}")
        print(f"\n{len(mapping)} mapped: {dict(verdicts)}; {len(left)} left unmapped")
        if not args.apply:
            print("\nReport only — pass --apply to write.")
            return 0

        print("\nRegenerating snapshots...")
        print(await generate_snapshots())
        return 0
    finally:
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
