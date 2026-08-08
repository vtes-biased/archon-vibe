"""Repair tournaments whose `finish` lands before their `start`.

Two populations, and only one is repairable (prod, 2026-08-08: 423 inverted).

The majority — 247 rows, `finish` at exactly midnight — is ours: `_parse_date`
applies a time only when `event_endtime` is truthy, so a VEKN event carrying an
`event_enddate` but no end time lands on midnight of that date. With
`enddate == startdate` that is midnight of the *start* date, before any start
time. Nothing ran past midnight; we invented an end time from a missing one.
Those are left alone here (fixing the importer is the real answer) because
rolling them forward would fabricate a duration for each.

The rest is genuine: an evening event whose end time rolled past midnight while
the date stayed on the start day. Those are repaired, and only when rolling
`finish` forward one day yields a plausible duration. Everything else is
reported UNRESOLVED with its reason: a finish that is merely *wrong* is a guess
we have no basis to make.

    # report (safe, read-only)
    sudo systemd-run --uid=archon --pipe --wait \\
      -p EnvironmentFile=/etc/archon/archon-backend.env \\
      /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/fix_finish_before_start.py

    # rewrite the repairable ones
    … fix_finish_before_start.py --apply

Idempotent: a repaired row no longer matches. Rewrites `modified`, so touched
tournaments re-download on each client's next reconnect. Ratings key off
`finish or start` and this only moves `finish`, so a rating's date is unchanged
unless the row's `start` was already absent — recompute anyway if in doubt.
"""

import argparse
import asyncio
import importlib.util
import os
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.src import db  # noqa: E402
from backend.src.models import Tournament  # noqa: E402

# Both values are naive ISO-8601 after normalize_wall_clock, so lexicographic
# ordering is chronological — the comparison is re-done on decoded datetimes below.
INVERTED_QUERY = """
    SELECT "full" FROM objects
    WHERE type = 'tournament'
      AND deleted_at IS NULL
      AND ("full"->>'finish') IS NOT NULL
      AND ("full"->>'finish') < ("full"->>'start')
    ORDER BY "full"->>'start'
"""

# A tournament running longer than this in one sitting is not credible, so a roll
# that produces it means the row is broken some other way — report, don't guess.
MAX_PLAUSIBLE = timedelta(hours=18)


def roll_forward(t: Tournament) -> tuple[datetime | None, str]:
    """`finish` a day later, when that is the reading the data supports.

    Returns (new_finish, reason-it-was-refused).
    """
    if t.start is None or t.finish is None or t.finish >= t.start:
        return None, "not inverted"
    if t.finish.date() != t.start.date():
        return None, "spans days — not a midnight roll"
    # vekn_tournament_sync._parse_date leaves midnight when event_endtime is
    # empty, so an exact-midnight finish means "no end time recorded" far more
    # often than "ended at midnight". Rolling it invents a duration.
    if t.finish.time() == time(0, 0, 0):
        return None, "midnight — no end time recorded upstream"
    rolled = t.finish + timedelta(days=1)
    if rolled - t.start > MAX_PLAUSIBLE:
        return None, f"rolled duration {rolled - t.start} implausible"
    return rolled, ""


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        async with db.get_connection() as conn:
            result = await conn.execute(INVERTED_QUERY)
            rows = await result.fetchall()
        found = [db.decode_json(row[0], Tournament) for row in rows]
        found = [t for t in found if t.start and t.finish and t.finish < t.start]

        repaired, unresolved = 0, 0
        for t in found:
            rolled, why = roll_forward(t)
            print(f"  {t.uid}  {t.name[:40]:<40} tz={t.timezone}")
            print(f"    start  {t.start}")
            if rolled is None:
                unresolved += 1
                print(f"    finish {t.finish}   UNRESOLVED — {why}")
                continue
            repaired += 1
            print(f"    finish {t.finish} → {rolled}  ({rolled - t.start} long)")
            if not args.apply:
                continue
            t.finish = rolled
            t.modified = datetime.now(UTC)
            async with db.get_connection() as conn:
                await db.save_tournament(t, conn=conn)

        verb = "repaired" if args.apply else "repairable (use --apply)"
        print(f"{len(found)} inverted, {repaired} {verb}, {unresolved} unresolved.")
        return 0
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--apply", action="store_true", help="write the repairs")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
