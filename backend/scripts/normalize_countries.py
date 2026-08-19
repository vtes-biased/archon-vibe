"""One-time re-save normalising stored country values to ISO codes.

The daily legacy merge seeded country *names* — `Brazil`, `Spain` — into a field
every consumer reads as a two-letter code, so an NC is not recognised in their
own country, the same-country projection never fires and every filter misses the
rows. Tournaments, users and leagues all take the field from that same source.

    # report the distinct values it would rewrite, per type
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/normalize_countries.py

    # rewrite
    … normalize_countries.py --apply

Run it **after** deploying the matching `migrate_from_archon.py`: that merge
re-saves a league or tournament on any full-struct diff, so a row normalised
while the old mapping is installed is rewritten back to the name within a day.

`modified` is deliberately untouched — nobody edited these rows; only the
replication cursor moves, and clients pick the rows up on their next catch-up.
No SSE broadcast is emitted (this runs outside the web process). Re-saving also
recomputes the access projections, which the corrected country changes.
Idempotent: a row already holding its normalised value is skipped.
"""

import argparse
import asyncio
import collections
import importlib.util
import os
import sys
from pathlib import Path

try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.src import db  # noqa: E402
from backend.src.geonames import stored_country  # noqa: E402
from backend.src.models import ObjectType  # noqa: E402

NORMALIZED_TYPES = (ObjectType.TOURNAMENT, ObjectType.USER, ObjectType.LEAGUE)

CANDIDATES_QUERY = """
    SELECT uid, type, "full"->>'country'
    FROM objects
    WHERE type = ANY(%s)
    ORDER BY type, uid
"""

# Re-read under the same row lock the app's writers take, so a payload edited
# between the sweep's start and this row's turn is not clobbered by a stale read.
LOCK_ROW_QUERY = 'SELECT "full", deleted_at FROM objects WHERE uid = %s FOR UPDATE'


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    await db.init_db()
    try:
        async with db.get_connection() as conn:
            result = await conn.execute(
                CANDIDATES_QUERY, ([t.value for t in NORMALIZED_TYPES],)
            )
            rows = await result.fetchall()

        targets = [
            (uid, obj_type, raw, stored_country(raw))
            for uid, obj_type, raw in rows
            if stored_country(raw) != raw
        ]

        if not args.apply:
            per_type: dict[str, collections.Counter] = {
                t.value: collections.Counter() for t in NORMALIZED_TYPES
            }
            for _, obj_type, raw, new in targets:
                per_type[obj_type][(raw, new)] += 1
            for obj_type, counter in per_type.items():
                print(f"{obj_type}: {sum(counter.values())} row(s) to rewrite")
                for (raw, new), count in counter.most_common():
                    print(f"  {count:>6}  {raw!r} → {new!r}")
            print("\nReport only — pass --apply to write.")
            return 0

        rewritten = collections.Counter()
        async with db.get_connection() as conn:
            for uid, obj_type, _, new in targets:
                # One transaction PER ROW: a single wrapping transaction would stamp
                # every row with the same CURRENT_TIMESTAMP, and catch-up's strict
                # `modified_at > since` would skip a run split across a cursor.
                async with conn.transaction():
                    row = await (await conn.execute(LOCK_ROW_QUERY, (uid,))).fetchone()
                    if row is None:
                        continue  # hard-deleted since the sweep began
                    full_data, deleted_at = row
                    if stored_country(full_data.get("country")) != new:
                        continue  # edited since the sweep began
                    full_data["country"] = new
                    await db.save_object(
                        obj_type,
                        uid,
                        full_data,
                        conn=conn,
                        deleted_at=deleted_at.isoformat() if deleted_at else None,
                    )
                    rewritten[obj_type] += 1

        for obj_type, count in rewritten.items():
            print(f"  {count:>6} {obj_type}")
        print(f"{sum(rewritten.values())} row(s) rewritten.")
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
