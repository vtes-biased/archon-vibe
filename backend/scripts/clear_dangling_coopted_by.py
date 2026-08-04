"""Clear coopted_by values that point at no live user (one-off cleanup).

The nightly legacy merge used to copy old archon's `sponsor` refs into
`coopted_by` verbatim when they didn't resolve — and legacy's sponsor uids
dangle even within its own members table and rotate to fresh uids nightly, so
~10k users got a new dangling value (and a full SSE re-download) every night.
The merge no longer writes unresolvable sponsors (`remap_coopted_by`), but the
last night's garbage stays put: it never re-resolves, and it blocks the VEKN
sync's coopted_by inference, which only fills the field where it is UNSET.

This script clears every live user's coopted_by that doesn't reference a live
user, so the next member sync's inference (sponsor prefix, then city/country)
can repopulate the field with real values. Users who locally edited the field
are left alone.

    # report what would change (safe, read-only)
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/clear_dangling_coopted_by.py

    # clear them
    … clear_dangling_coopted_by.py --apply

Idempotent: a second run finds nothing. No SSE broadcast is emitted (runs
outside the web process); clients pick the change up on their next reconnect —
one final corpus-sized catch-up, then nightly churn is over.
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
from backend.src.models import User  # noqa: E402

DANGLING_QUERY = """
    SELECT o."full" FROM objects o
    WHERE o.type = 'user'
      AND o.deleted_at IS NULL
      AND o."full"->>'coopted_by' IS NOT NULL
      AND o."full"->>'coopted_by' != ''
      AND NOT EXISTS (
          SELECT 1 FROM objects s
          WHERE s.uid = o."full"->>'coopted_by'
            AND s.type = 'user'
            AND s.deleted_at IS NULL)
    ORDER BY o.uid
"""


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        async with db.get_connection() as conn:
            result = await conn.execute(DANGLING_QUERY)
            rows = await result.fetchall()
        found = [db.decode_json(row[0], User) for row in rows]

        cleared = skipped_local = 0
        for u in found:
            if "coopted_by" in u.local_modifications:
                skipped_local += 1
                continue
            cleared += 1
            if not args.apply:
                continue
            u.coopted_by = None
            u.coopted_at = None
            u.modified = datetime.now(UTC)
            await db.save_user(u)
            if cleared % 2000 == 0:
                print(f"  …{cleared} cleared")

        verb = "cleared" if args.apply else "to clear (use --apply)"
        print(f"{cleared} user(s) {verb}; {skipped_local} locally-edited skipped.")
        if cleared and args.apply:
            print("Next VEKN member sync re-infers coopted_by for cleared users.")
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
