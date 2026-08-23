"""Collapse stored `community_links[].moderation` objects to one string.

Moderation used to be a `{status, scope, by, at}` object; it is now a single
value — `"hidden"`, `"national"`, `"global"`, or null. `User` decodes strictly,
so a row still carrying the object shape raises on every read of that member
until this runs.

    # report what would change (safe, read-only)
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/collapse_link_moderation.py

    # rewrite
    … collapse_link_moderation.py --apply

Run it from the DEPLOYED tree, immediately after deploying the collapse. Running
it against the old code would have that code write the object shape straight
back. A re-save (not an UPDATE of the column) is required: the projections are Python
and `modified_at`, the cursor clients sync on, is stamped by the row trigger.
Safe against a live backend — the affected rows are exactly the ones the app
cannot decode, so nothing else can be writing them. Idempotent: a second run
finds nothing. Soft-deleted rows are included; they sync as tombstones.
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

STALE_QUERY = """
    SELECT uid FROM objects
    WHERE type = 'user'
      AND jsonb_path_exists("full", '$.community_links[*].moderation.status')
    ORDER BY uid
"""

LOCK_ROW_QUERY = 'SELECT "full", deleted_at FROM objects WHERE uid = %s FOR UPDATE'


def collapsed(moderation: dict) -> str | None:
    if moderation["status"] == "hidden":
        return "hidden"
    # A promotion with no scope was already read as unmoderated, never rendered.
    return moderation.get("scope")


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    await db.init_db()
    try:
        async with db.get_connection() as conn:
            result = await conn.execute(STALE_QUERY)
            uids = [row[0] for row in await result.fetchall()]

        rewritten = 0
        async with db.get_connection() as conn:
            for uid in uids:
                if not args.apply:
                    rewritten += 1
                    continue
                # One transaction PER ROW: a single wrapping one would stamp every
                # row with the same CURRENT_TIMESTAMP, and catch-up's strict
                # `modified_at > since` would skip a run split across a cursor.
                async with conn.transaction():
                    row = await (await conn.execute(LOCK_ROW_QUERY, (uid,))).fetchone()
                    if row is None:
                        continue  # hard-deleted since the sweep began
                    full_data, deleted_at = row
                    for link in full_data.get("community_links") or []:
                        if isinstance(link.get("moderation"), dict):
                            link["moderation"] = collapsed(link["moderation"])
                    await db.save_object(
                        ObjectType.USER,
                        uid,
                        full_data,
                        conn=conn,
                        deleted_at=deleted_at.isoformat() if deleted_at else None,
                    )
                    rewritten += 1

        verb = "rewritten" if args.apply else "to rewrite (use --apply)"
        print(f"{rewritten} user(s) {verb}.")
        return 0
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--apply", action="store_true", help="write the collapses")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
