"""Clear the Antarctica location the placeholder venue wrote onto app-created events.

vekn.net's venue resource rejects POST, so an in-person event the app files gets
the generic placeholder venue, which reads back as "Check on Archon" in AQ. The
metadata refresh took that for the truth and overwrote country, timezone, venue,
address and map url within the hour, undoing every hand re-entry on the next run.
The sync now drops the placeholder and keeps what the app holds — but the rows
already flipped hold Antarctica as their own value, and the sync preserving them
is exactly what stops them healing. This script is that one-off.

    # report what would change (safe, read-only)
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/clear_placeholder_venue_location.py

    # clear them
    … clear_placeholder_venue_location.py --apply

It clears rather than guesses: the overwritten location is not recoverable from
our own data, so the organizer re-enters it — which now sticks. The organizers
are printed so they can be told.

Idempotent: a cleared row no longer carries the placeholder name, so a second run
reports nothing. No SSE broadcast — this runs outside the web process, so clients
pick the change up on their next reconnect.
"""

import argparse
import asyncio
import importlib.util
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.src import db  # noqa: E402
from backend.src.models import Tournament  # noqa: E402
from backend.src.vekn_api import PLACEHOLDER_VENUE_NAME  # noqa: E402

PLACEHOLDER_VENUE_QUERY = """
    SELECT "full" FROM objects
    WHERE type = 'tournament'
      AND deleted_at IS NULL
      AND "full"->>'venue' = %s
    ORDER BY "full"->>'start'
"""


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        async with db.get_connection() as conn:
            result = await conn.execute(
                PLACEHOLDER_VENUE_QUERY, (PLACEHOLDER_VENUE_NAME,)
            )
            rows = await result.fetchall()
        found = [db.decode_json(row[0], Tournament) for row in rows]
        organizers = await db.get_users_by_uids(
            {uid for t in found for uid in t.organizers_uids}
        )

        for t in found:
            names = [
                organizers[uid].name for uid in t.organizers_uids if uid in organizers
            ]
            print(
                f"  {t.uid}  {t.name[:40]:<40} {t.start}\n"
                f"    clearing {t.country} / {t.timezone} / {t.venue} / {t.address}\n"
                f"    organizers: {', '.join(names) or '(none)'}"
            )
            if not args.apply:
                continue
            t.country = None
            t.timezone = "UTC"
            t.venue = ""
            t.venue_url = ""
            t.address = ""
            t.map_url = ""
            t.modified = datetime.now(UTC)
            async with db.get_connection() as conn:
                await db.save_tournament(t, conn=conn)

        verb = "cleared" if args.apply else "to clear (use --apply)"
        print(f"{len(found)} tournament(s) {verb}.")
        if found and args.apply:
            print("Tell the organizers above to re-enter the location.")
        return 0
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--apply", action="store_true", help="write the clears")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
