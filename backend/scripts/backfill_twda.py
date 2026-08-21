"""One-time backfill of the historic archive: settle every reviewed decision onto
the corpus — reconstructing the ~1100 tournaments we lack and stamping the archive
key onto the ~3400 events we already hold — import their winning decks, recompute
the Hall of Fame, then regenerate the snapshot.

    # reports what it would do; --apply is the only thing that writes
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/backfill_twda.py
    … backfill_twda.py --apply

Not the recurring task's first run. That path broadcasts each object as it lands,
which is right for a weekly delta of a handful and wrong for a burst of a
thousand — every connected client would take the lot as individual SSE frames.
So this suppresses broadcasting and regenerates the snapshot at the end instead,
the way the archon migration did. Clients pick the corpus up on their next resync.

Idempotent: an entry the corpus already holds is recognised by its `twda` or
`twda_entry` external id and skipped, so a half-finished run is resumed by
re-running. From then on the decisions file is only read for what is left.

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
from backend.src.ratings import recompute_wins  # noqa: E402
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
        settle = 0
        for entry in entries:
            entry_id = str(entry.get("id", ""))
            action = decisions.get(entry_id, ("unresolved", ""))[0]
            by_action[action] = by_action.get(action, 0) + 1
            if entry_id in held:
                continue
            if action == "create":
                todo += 1
            elif action == "attach":
                settle += 1

        print(f"archive:  {len(entries)} entries")
        for action, count in sorted(by_action.items()):
            print(f"  {count:6d}  {action}")
        print(f"already settled on the corpus: {len(held)}")
        print(f"\nwould create {todo} tournaments and settle {settle} attachments")
        if not args.apply:
            print("\nDry run — pass --apply to write.")
            return 0

        stats = await run_twda_sync(broadcast=False, max_creates=None)
        print(f"\n{stats}")

        # The sync recomputes only the winners it touched — every Hall of Fame
        # addition, no removal. A full pass settles both before the snapshot.
        print("\nRecomputing Hall of Fame wins...")
        print(f"{len(await recompute_wins())} win lists changed")

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
