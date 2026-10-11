"""One-time removal of winner decks held twice by one player for one round.

Where the copies' cards are identical, the legacy uuid5 copy stays, since a
`--merge` rerun would recreate it, and the others are soft-deleted. A group whose
cards differ is listed and left alone for a human to decide.

    # reports what it would do; --apply is the only thing that writes
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/dedup_winner_decks.py
    … dedup_winner_decks.py --apply

No broadcast: clients take the tombstones on their next resync.
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
from backend.src.models import DeckObject, ObjectType  # noqa: E402
from backend.src.ratings import recompute_wins  # noqa: E402


async def duplicate_groups() -> list[list[DeckObject]]:
    async with db.get_connection() as conn:
        rows = await (
            await conn.execute(
                """SELECT array_agg("full"::text ORDER BY uid)
                   FROM objects
                   WHERE type = %s AND deleted_at IS NULL
                     AND ("full"->>'winner')::boolean
                   GROUP BY "full"->>'tournament_uid', "full"->>'user_uid',
                            "full"->>'round'
                   HAVING count(*) > 1""",
                (ObjectType.DECK,),
            )
        ).fetchall()
    return [
        [msgspec.json.decode(d.encode(), type=DeckObject) for d in row[0]]
        for row in rows
    ]


def keeper(group: list[DeckObject]) -> DeckObject:
    legacy = [d for d in group if d.uid[14] == "5"]
    return legacy[0] if len(legacy) == 1 else min(group, key=lambda d: d.uid)


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        groups = await duplicate_groups()
        drops: list[DeckObject] = []
        review = 0
        for group in groups:
            keep = keeper(group)
            same = [d for d in group if d is not keep and d.cards == keep.cards]
            differ = [d for d in group if d is not keep and d.cards != keep.cards]
            print(
                f"{keep.tournament_uid}  player {keep.user_uid}  round "
                f"{keep.round if keep.round is not None else '-'}: keep {keep.uid}"
            )
            for d in same:
                print(f"    drop {d.uid}  {d.name!r}")
            for d in differ:
                print(f"    REVIEW {d.uid}  {d.name!r}  cards differ — left alone")
            drops.extend(same)
            review += bool(differ)

        print(
            f"\n{len(groups)} duplicated winner deck(s); {len(drops)} identical "
            f"copies to drop; {review} group(s) with differing cards to review."
        )
        if not args.apply:
            print("Dry run — pass --apply to write.")
            return 0

        now = datetime.now(UTC)
        for d in drops:
            await db.save_object_from_model(
                ObjectType.DECK,
                msgspec.structs.replace(d, deleted_at=now, modified=now),
            )
        changed = await recompute_wins({d.user_uid for d in drops})
        print(f"soft-deleted {len(drops)}; {len(changed)} win lists changed")
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
