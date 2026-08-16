"""One-time backfill of the historic archive: reconstruct ~1100 tournaments and
import their winning decks, then regenerate the snapshot.

    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/backfill_twda.py --dry-run
    … backfill_twda.py --apply

Not the recurring task's first run. That path broadcasts each object as it lands,
which is right for a weekly delta of a handful and wrong for a burst of a
thousand — every connected client would take the lot as individual SSE frames.
So this suppresses broadcasting and regenerates the snapshot at the end instead,
the way the archon migration did. Clients pick the corpus up on their next resync.

Idempotent: an entry already carrying a reconstruction is recognised by its
`twda` external id and skipped, so a half-finished run is resumed by re-running.

**Regenerate the decisions file against this database first.** Its targets are
uids: one that moved since the file was written attaches nothing, or reconstructs
an event whose winner resolves to no member and renders as a raw uuid.

    reconcile_twda.py --emit-decisions backend/src/data/twda_decisions.tsv --validate
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
from backend.src.snapshots import generate_snapshots  # noqa: E402
from backend.src.twda_import import (  # noqa: E402
    _fetch_twda,
    _tournaments_by_twda_id,
    load_decisions,
    run_twda_sync,
)


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        decisions = load_decisions()
        entries = await _fetch_twda()
        held = await _tournaments_by_twda_id()
        by_action: dict[str, int] = {}
        todo = 0
        for entry in entries:
            entry_id = str(entry.get("id", ""))
            action = decisions.get(entry_id, ("unresolved", ""))[0]
            by_action[action] = by_action.get(action, 0) + 1
            if action == "create" and entry_id not in held:
                todo += 1

        print(f"archive:  {len(entries)} entries")
        for action, count in sorted(by_action.items()):
            print(f"  {count:6d}  {action}")
        print(f"already reconstructed: {len(held)}")
        print(f"\nwould create {todo} tournaments")
        if not args.apply:
            print("\nDry run — pass --apply to write.")
            return 0

        stats = await run_twda_sync(broadcast=False)
        print(f"\n{stats}")
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
