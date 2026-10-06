"""Print what the judge directory sync would change on this database, writing nothing.

    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/preview_judge_sync.py

Applying is the admin panel's "Sync judges", never a script: the write goes through
`save_member`, whose Discord Linked Roles push is a background task a script would
exit before.
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

from backend.src import db, http_client  # noqa: E402
from backend.src.judge_directory import sync_judges  # noqa: E402


async def run(dsn: str) -> int:
    db.DB_URL = dsn
    os.environ["DATABASE_URL"] = dsn
    await db.init_db()
    try:
        stats = await sync_judges(apply=False)
    finally:
        await http_client.close()
        await db.close_db()
    print(f"directory: {stats['listed']} entries")
    print(f"listed VEKN ids matching no member: {stats['unmatched'] or 'none'}")
    print(f"\n{len(stats['changes'])} members would change:")
    for c in sorted(stats["changes"], key=lambda c: (c["after"], c["vekn_id"])):
        before = ", ".join(c["before"]) or "-"
        after = ", ".join(c["after"]) or "-"
        print(f"  {c['vekn_id']:>8}  {before:>8} -> {after:<8}  {c['name']}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    sys.exit(asyncio.run(run(args.dsn)))
