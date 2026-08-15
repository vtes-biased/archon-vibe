"""Rewrite tz-aware tournament start/finish as the naive wall clock they should be.

`Tournament.start`/`finish` are stored NAIVE and paired with `Tournament.timezone`
(wiki/architecture.md, "API conventions"): readers anchor the wall clock in that
zone (`routes/calendar._as_utc`, frontend `utils.zonedDate`), so a stored instant
gets shifted by the venue's offset a second time — a 09:00 Madrid event reads back
as 07:00.

Three writers used to store instants: the VEKN import (venue wall clock → UTC), the
Finished hook (`finish = now(UTC)`), and the legacy merge (UTC forced onto old
archon's naive values). All three are fixed, and most rows heal themselves — the
VEKN sync and the legacy merge both compare start/finish and rewrite what they own.
What does NOT heal is a `finish` stamped by the app on a tournament run here: no
sync owns it, so nothing ever rewrites it. This script is that one-off.

    # report what would change (safe, read-only)
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/normalize_wall_clock.py

    # rewrite them
    … normalize_wall_clock.py --apply

Idempotent: it only touches values that still carry an offset, so a second run
reports nothing. Run it AFTER the final legacy merge and VEKN sync (so the
self-healing writers have done their part) and BEFORE the ratings recompute — a
rating's date comes from `finish or start`, and a shifted instant can land on the
wrong day at the edges.

Ratings are NOT recomputed here (admin route, `recompute_all_ratings`), and no SSE
broadcast is emitted: this runs outside the web process, so connected clients pick
the change up on their next reconnect/snapshot — a redeploy is part of the cutover
anyway.
"""

import argparse
import asyncio
import importlib.util
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.src import db  # noqa: E402
from backend.src.models import Tournament  # noqa: E402

# Stored as JSON strings, so the offset is visible in SQL — keeps the scan cheap
# and the intent greppable instead of decoding every tournament row.
AWARE_DATES_QUERY = """
    SELECT "full" FROM objects
    WHERE type = 'tournament'
      AND deleted_at IS NULL
      AND (("full"->>'start') ~ '(Z|[+-][0-9]{2}:?[0-9]{2})$'
           OR ("full"->>'finish') ~ '(Z|[+-][0-9]{2}:?[0-9]{2})$')
    ORDER BY "full"->>'start'
"""


def to_wall_clock(dt: datetime | None, tz_name: str) -> datetime | None:
    """The instant, read as wall clock in the tournament's own timezone."""
    if dt is None or dt.tzinfo is None:
        return dt
    try:
        zone = ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        zone = UTC  # unknown zone: at least drop the offset rather than skip the row
    return dt.astimezone(zone).replace(tzinfo=None)


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        async with db.get_connection() as conn:
            result = await conn.execute(AWARE_DATES_QUERY)
            rows = await result.fetchall()
        found = [db.decode_json(row[0], Tournament) for row in rows]

        for t in found:
            start, finish = (
                to_wall_clock(t.start, t.timezone),
                to_wall_clock(t.finish, t.timezone),
            )
            print(
                f"  {t.uid}  {t.name[:40]:<40} tz={t.timezone}\n"
                f"    start  {t.start} → {start}\n"
                f"    finish {t.finish} → {finish}"
            )
            if not args.apply:
                continue
            t.start, t.finish = start, finish
            t.modified = datetime.now(UTC)
            async with db.get_connection() as conn:
                await db.save_tournament(t, conn=conn)

        verb = "rewritten" if args.apply else "to rewrite (use --apply)"
        print(f"{len(found)} tournament(s) {verb}.")
        if found and args.apply:
            print("Ratings are date-derived — recompute them (admin route).")
        return 0
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--apply", action="store_true", help="write the rewrites")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
