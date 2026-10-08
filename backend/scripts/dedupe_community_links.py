"""Drop a member's repeated community-link URLs, keeping the moderated copy.

Where neither copy carries a moderation value the first one is kept. Each row is
re-read under the app writers' `FOR UPDATE` lock and saved through
`db.save_object`, so the projections and the sync cursor move with it.

    # list what would be dropped
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/dedupe_community_links.py

    # drop it
    … dedupe_community_links.py --apply
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

UIDS_QUERY = """
    SELECT uid FROM objects
    WHERE type = 'user' AND "full"->'community_links' <> '[]'::jsonb
    ORDER BY uid
"""

LOCK_ROW_QUERY = 'SELECT "full", deleted_at FROM objects WHERE uid = %s FOR UPDATE'


def deduped(links: list[dict]) -> list[dict]:
    kept: dict[str, dict] = {}
    for link in links:
        prior = kept.get(link["url"])
        if prior is None or (
            prior.get("moderation") is None and link.get("moderation")
        ):
            kept[link["url"]] = link
    return list(kept.values())


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    await db.init_db()
    try:
        async with db.get_connection() as conn:
            uids = [r[0] for r in await (await conn.execute(UIDS_QUERY)).fetchall()]
            touched = 0
            for uid in uids:
                async with conn.transaction():
                    row = await (await conn.execute(LOCK_ROW_QUERY, (uid,))).fetchone()
                    if row is None:
                        continue
                    full_data, deleted_at = row
                    links = full_data["community_links"]
                    kept = deduped(links)
                    if len(kept) == len(links):
                        continue
                    touched += 1
                    dropped = [
                        (link["type"], link["url"], link.get("moderation"))
                        for link in links
                        if not any(link is k for k in kept)
                    ]
                    print(f"{uid} drops {dropped}")
                    if not args.apply:
                        continue
                    full_data["community_links"] = kept
                    await db.save_object(
                        ObjectType.USER,
                        uid,
                        full_data,
                        conn=conn,
                        deleted_at=deleted_at.isoformat() if deleted_at else None,
                    )
        verb = "rewritten" if args.apply else "to rewrite (use --apply)"
        print(f"{touched} user(s) {verb}.")
        return 0
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--apply", action="store_true", help="drop the repeated links")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
