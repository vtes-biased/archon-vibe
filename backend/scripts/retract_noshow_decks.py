"""One-time retraction of decks "All" mode published for players who never sat.

    # reports what it would do; --apply is the only thing that writes
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/retract_noshow_decks.py
    … retract_noshow_decks.py --apply

No broadcast: clients take the retraction on their next resync.
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

import msgspec  # noqa: E402

from backend.src import db  # noqa: E402
from backend.src.models import (  # noqa: E402
    DeckObject,
    ObjectType,
    TableState,
    Tournament,
)


async def all_mode_tournaments() -> list[Tournament]:
    async with db.get_connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT "full"::text FROM objects
                   WHERE type = 'tournament' AND deleted_at IS NULL
                     AND "full"->>'state' = 'Finished'
                     AND "full"->>'decklists_mode' = 'All'
                     AND jsonb_array_length(coalesce("full"->'rounds', '[]')) > 0"""
            )
        ).fetchall()
    return [msgspec.json.decode(r[0].encode(), type=Tournament) for r in rows]


def seated(t: Tournament) -> set[str]:
    return {
        seat.player_uid
        for round_ in t.rounds
        for table in round_
        if table.state != TableState.CANCELLED
        for seat in table.seating
    }


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        retract: list[DeckObject] = []
        for t in await all_mode_tournaments():
            played = seated(t)
            for d in await db.get_decks_for_tournament(t.uid):
                if d.public and d.user_uid != t.winner and d.user_uid not in played:
                    vekn = t.external_ids.get("vekn", "-")
                    print(f"{t.uid}  vekn {vekn}  {t.name!r}: deck {d.uid}  {d.name!r}")
                    retract.append(d)

        print(f"\n{len(retract)} published deck(s) of players who never sat.")
        if not args.apply:
            print("Dry run — pass --apply to write.")
            return 0

        now = datetime.now(UTC)
        for d in retract:
            await db.save_object_from_model(
                ObjectType.DECK, msgspec.structs.replace(d, public=False, modified=now)
            )
        print(f"retracted {len(retract)}")
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
