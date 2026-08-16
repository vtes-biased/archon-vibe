"""Rebuild the stored public/member/full projections for tournaments and leagues.

Projections are computed at WRITE time (`db.save_object` → `access_levels`), so
widening one only affects rows saved afterwards: tournaments gaining the
attend-decision fields, and leagues losing `organizers_uids`, both leave every
existing row on its old projection.

A re-save is required rather than an UPDATE of the `public` column, for two
reasons. The projection functions are Python, so SQL cannot reproduce them; and
the `objects` BEFORE-UPDATE trigger stamps `modified_at = CURRENT_TIMESTAMP`,
the cursor clients sync on. Rewriting the column alone leaves the new payload
invisible — an anonymous PWA holds the narrow rows already and only asks for
`modified_at > since`. `modified` (user-visible, and nobody edited these) is
deliberately not touched; only the replication cursor moves.

    # count what would be rewritten (no row writes; init_db still applies schema.sql)
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/reproject_public.py

    # rewrite
    … reproject_public.py --apply

Run it from the DEPLOYED tree, after deploying the matching `access_levels.py` —
it re-runs whatever projection code is installed (an old build faithfully rewrites
the old, narrow projection), and `init_db` applies that tree's `schema.sql`. Safe
against a live backend: each row is re-read under the same `FOR UPDATE` lock the
app's writers take, so a concurrent organizer edit is never rolled back.
Idempotent. Soft-deleted rows are included (they sync as tombstones).
No SSE broadcast is emitted, as this runs outside the web process; clients pick
the rows up on their next catch-up, which a redeploy forces anyway.
"""

import argparse
import asyncio
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
from backend.src.models import ObjectType  # noqa: E402

REPROJECT_TYPES = (ObjectType.TOURNAMENT, ObjectType.LEAGUE)

UIDS_QUERY = """
    SELECT uid, type
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
                UIDS_QUERY, ([t.value for t in REPROJECT_TYPES],)
            )
            targets = await result.fetchall()

        counts = {t.value: 0 for t in REPROJECT_TYPES}
        async with db.get_connection() as conn:
            for uid, obj_type in targets:
                counts[obj_type] += 1
                if not args.apply:
                    continue
                # One transaction PER ROW: a single wrapping transaction would stamp
                # every row with the same CURRENT_TIMESTAMP, and catch-up's strict
                # `modified_at > since` would skip a run split across a cursor.
                async with conn.transaction():
                    row = await (await conn.execute(LOCK_ROW_QUERY, (uid,))).fetchone()
                    if row is None:
                        continue  # hard-deleted since the sweep began
                    full_data, deleted_at = row
                    await db.save_object(
                        obj_type,
                        uid,
                        full_data,
                        conn=conn,
                        deleted_at=deleted_at.isoformat() if deleted_at else None,
                    )

        verb = "rewritten" if args.apply else "to rewrite (use --apply)"
        for obj_type, count in counts.items():
            print(f"  {count:>6} {obj_type}")
        print(f"{len(targets)} row(s) {verb}.")
        return 0
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--apply", action="store_true", help="write the projections")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
