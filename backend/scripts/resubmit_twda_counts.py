"""One-time resubmission of TWDA entries published with the wrong player count.

    # lists what it would resubmit; --apply is the only thing that writes
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/resubmit_twda_counts.py
    … resubmit_twda_counts.py --apply

The header used to count the registered roster, no-shows included, where the
archive wants the field size `attested_player_count` gives. Before the waitlist
was held out of that roster the waitlisted counted too, so a submission is listed
when either roster count differs from the attested one. Also listed: events the
old seats-only gate skipped as too small that the attested count now admits.

`--apply` re-runs `maybe_submit_twda` on each: an open pull request takes the new
file, a merged one gets a fresh `Update TWD` request. Each opens or moves a pull
request on the archive repo.
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

import msgspec  # noqa: E402

from backend.src import db, http_client  # noqa: E402
from backend.src.db import TWDA_MIN_PLAYERS  # noqa: E402
from backend.src.models import Tournament, TwdaOutcome  # noqa: E402
from backend.src.routes.tournaments import _engine, maybe_submit_twda  # noqa: E402


def _candidate(t: Tournament) -> str | None:
    status = t.twda_status
    if not status:
        return None
    attested = _engine.attested_player_count(msgspec.json.encode(t).decode())
    if status.outcome == TwdaOutcome.SUBMITTED:
        roster = len(t.players)
        present = len([p for p in t.players if not p.waitlisted])
        if attested != roster or attested != present:
            old = str(present) if roster == present else f"{present}/{roster}"
            return f"submitted  {old} → {attested}"
    elif (
        status.outcome == TwdaOutcome.SKIPPED
        and status.reason == "too_few_players"
        and t.rounds
        and not t.external_ids.get("twda")
        and attested >= TWDA_MIN_PLAYERS
    ):
        return f"too small  now {attested}"
    return None


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        async with db.get_connection() as conn:
            result = await conn.execute(
                """SELECT "full" FROM objects
                   WHERE type = 'tournament' AND deleted_at IS NULL
                     AND "full"->'twda_status'->>'outcome' IN ('submitted', 'skipped')
                   ORDER BY "full"->>'event_code'"""
            )
            rows = await result.fetchall()
        listed: list[str] = []
        for (full,) in rows:
            t = db.decode_json(full, Tournament)
            line = _candidate(t)
            if line:
                listed.append(t.uid)
                print(f"{t.event_code or t.uid:<12} {line:<22} {t.name}")
        print(f"\n{len(listed)} of {len(rows)} tournaments with a TWDA outcome")
        if not args.apply:
            print("\nReport only — pass --apply to resubmit.")
            return 0

        for uid in listed:
            fresh = await db.get_tournament_by_uid(uid)
            if not fresh:
                continue
            await maybe_submit_twda(fresh)
            after = await db.get_tournament_by_uid(uid)
            status = after.twda_status if after else None
            print(
                f"{fresh.event_code or uid:<12} "
                f"{status.outcome if status else '-'} "
                f"{status.reason or status.pr_url if status else ''}"
            )
        return 0
    finally:
        await http_client.close()
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument(
        "--apply", action="store_true", help="resubmit; without it, report only"
    )
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
