"""Strip deckbuilder import noise from the deck comments stored before the import did.

A deck-link import now runs the engine's `strip_deckbuilder_noise` on the
description it copies into `comments`; the decks imported before it still hold
the restated headers, crypt lines and revision stamps, and the TWDA export
publishes a comment verbatim. This script is that one-off.

    # report what would change (safe, read-only)
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/strip_deck_comment_noise.py

    # rewrite them
    … strip_deck_comment_noise.py --apply

Idempotent: a stripped comment strips to itself, so a second run reports nothing.
No SSE broadcast — this runs outside the web process, so clients pick the change
up on their next reconnect.
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

from archon_engine import PyEngine  # noqa: E402

from backend.src import db  # noqa: E402
from backend.src.models import ObjectType  # noqa: E402

COMMENTED_DECKS_QUERY = """
    SELECT uid, "full"->>'comments' FROM objects
    WHERE type = 'deck'
      AND "full"->>'deleted_at' IS NULL
      AND coalesce("full"->>'comments', '') <> ''
"""

_LOCK_ROW = 'SELECT "full" FROM objects WHERE uid = %s FOR UPDATE'


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    engine = PyEngine()
    await db.init_db()
    try:
        async with db.get_connection() as conn:
            result = await conn.execute(COMMENTED_DECKS_QUERY)
            rows = await result.fetchall()
        changed = [
            (uid, comments, engine.strip_deckbuilder_noise(comments))
            for uid, comments in rows
        ]
        changed = [c for c in changed if c[1].rstrip() != c[2]]

        for uid, before, after in changed:
            print(f"  {uid}\n    before: {before!r}\n    after:  {after!r}")
            if not args.apply:
                continue
            async with db.get_connection() as conn, conn.transaction():
                result = await conn.execute(_LOCK_ROW, (uid,))
                row = await result.fetchone()
                if row is None:
                    continue
                full_data = row[0]
                full_data["comments"] = engine.strip_deckbuilder_noise(
                    full_data.get("comments", "")
                )
                await db.save_object(ObjectType.DECK, uid, full_data, conn=conn)

        verb = "rewritten" if args.apply else "to rewrite (use --apply)"
        print(f"{len(changed)} of {len(rows)} commented deck(s) {verb}.")
    finally:
        await db.close_db()
    return 0


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
