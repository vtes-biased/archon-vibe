"""Hand a finished tournament back to the hourly VEKN results push.

    # report what would change
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/fix_stuck_vekn_push.py --vekn 12498

    # write it
    … fix_stuck_vekn_push.py --vekn 12498 --apply

Saves without broadcasting, so connected clients pick the change up on their next
snapshot/reconnect rather than live.
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
from backend.src.models import Tournament, TournamentState  # noqa: E402

FIND_BY_VEKN = """
    SELECT uid FROM objects
    WHERE type = 'tournament'
      AND deleted_at IS NULL
      AND "full"->'external_ids'->>'vekn' = %s
"""


async def resolve(vekn: str | None, uid: str | None) -> Tournament | None:
    if uid:
        return await db.get_tournament_by_uid(uid)
    async with db.get_connection() as conn:
        result = await conn.execute(FIND_BY_VEKN, (vekn,))
        rows = await result.fetchall()
    if len(rows) != 1:
        print(f"vekn {vekn}: expected 1 live tournament, found {len(rows)}")
        return None
    return await db.get_tournament_by_uid(str(rows[0][0]))


def describe(t: Tournament) -> str:
    return (
        f"{t.uid}  '{t.name}'\n"
        f"  state={t.state.value} vekn={t.external_ids.get('vekn') or '-'} "
        f"rounds={len(t.rounds)} standings={len(t.standings)} "
        f"winner={t.winner or '-'}\n"
        f"  vekn_pushed_at={t.vekn_pushed_at} vekn_results_stale={t.vekn_results_stale}"
    )


async def check(t: Tournament) -> list[str]:
    problems = []
    if not t.external_ids.get("vekn"):
        problems.append("no external_ids.vekn — push would create a NEW calendar event")
    if not t.vekn_pushed_at:
        problems.append("already unstamped — batch_push picks it up as it is")
    if t.state is not TournamentState.FINISHED:
        problems.append(f"state {t.state.value} — the push set is Finished-only")
    if not t.standings:
        problems.append("no standings — push_tournament_results would refuse")
    missing = []
    for s in t.standings:
        user = await db.get_user_by_uid(s.user_uid)
        if not user or not user.vekn_id:
            missing.append(s.user_uid)
    if missing:
        problems.append(
            f"{len(missing)} player(s) without a vekn_id — the push would no-op: "
            + ", ".join(missing[:5])
        )
    return problems


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        t = await resolve(args.vekn, args.uid)
        if t is None:
            return 1
        print("Before:\n" + describe(t))
        problems = await check(t)
        if problems:
            print("\nBLOCKED:")
            for p in problems:
                print(f"  - {p}")
            return 1
        if not args.apply:
            print("\nWould: clear vekn_pushed_at. Re-run with --apply.")
            return 0
        t.vekn_pushed_at = None
        t.modified = datetime.now(UTC)
        async with db.get_connection() as conn:
            await db.save_tournament(t, conn=conn)
        print("\nAfter:\n" + describe(t))
        print(
            "\nNext hourly batch_push will upload results to the existing vekn event."
        )
        return 0
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--vekn", help="vekn event id of the stuck tournament")
    g.add_argument("--uid", help="tournament uid")
    p.add_argument("--apply", action="store_true", help="write (default: report)")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
