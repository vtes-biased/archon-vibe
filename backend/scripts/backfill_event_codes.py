"""One-time backfill of the short event code across the whole corpus.

    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/backfill_event_codes.py --dry-run
    … backfill_event_codes.py --apply

Run it **after** `backfill_twda.py`: a reconstruction takes the archive's own key
as its code, and a code is never rewritten, so a row stamped before its archive
entry lands keeps a minted code instead of the one the TWDA publishes for it.

Suppresses broadcasting and regenerates the snapshot at the end, like the TWDA
backfill — every row changes here, and a client should take that as one resync
rather than 8500 SSE frames.

Idempotent: a row that already carries a code is skipped, so a half-finished run
is resumed by re-running.
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
from backend.src.snapshots import generate_snapshots  # noqa: E402


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        uids = await db.tournament_uids_without_event_code()
        print(f"{len(uids)} tournaments without an event code")
        if not args.apply:
            print("\nDry run — pass --apply to write.")
            return 0

        sources = {"vekn": 0, "twda": 0, "minted": 0}
        for uid in uids:
            async with db.tournament_transaction(uid) as (fresh, tx_conn):
                if not fresh or fresh.event_code:
                    continue
                fresh.event_code = await db.resolve_event_code(fresh, tx_conn)
                fresh.modified = datetime.now(UTC)
                await db.save_tournament(fresh, conn=tx_conn)
                if fresh.event_code == fresh.external_ids.get("vekn"):
                    sources["vekn"] += 1
                elif fresh.event_code == fresh.external_ids.get("twda"):
                    sources["twda"] += 1
                else:
                    sources["minted"] += 1
        print(f"\n{sources}")

        print("\nRegenerating snapshots...")
        print(await generate_snapshots())
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
