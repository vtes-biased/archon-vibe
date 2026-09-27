"""One-time resubmission of TWDA entries published with the wrong player count.

    # lists what it would resubmit; --apply is the only thing that writes
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/resubmit_twda_counts.py
    … resubmit_twda_counts.py --apply
"""

import argparse
import asyncio
import importlib.util
import os
import re
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
from backend.src.twda import TWDA_FORK_REPO, TWDA_TARGET_REPO  # noqa: E402

_PLAYERS = re.compile(r"^(\d+) players$", re.MULTILINE)


async def _get(url: str) -> tuple[int, str]:
    async with http_client.session().get(url) as resp:
        return resp.status, await resp.text()


async def _open_branches() -> set[str]:
    status, text = await _get(
        f"https://api.github.com/repos/{TWDA_TARGET_REPO}/pulls?state=open&per_page=100"
    )
    if status != 200:
        raise RuntimeError(f"open pull requests: {status}")
    return {
        pr["head"]["ref"]
        for pr in msgspec.json.decode(text)
        if (pr["head"]["repo"] or {}).get("full_name") == TWDA_FORK_REPO
    }


async def _count(url: str) -> int | None:
    status, text = await _get(url)
    if status == 404:
        return None
    if status != 200:
        raise RuntimeError(f"{url}: {status}")
    found = _PLAYERS.search(text)
    return int(found.group(1)) if found else -1


async def _candidate(t: Tournament, open_branches: set[str]) -> tuple[str, bool] | None:
    """The listing line, and whether `--apply` resubmits it."""
    status = t.twda_status
    if not status:
        return None
    attested = _engine.attested_player_count(msgspec.json.encode(t).decode())
    if status.outcome == TwdaOutcome.SUBMITTED:
        branch = f"archon/{t.event_code}"
        path = f"decks/{t.event_code}.txt"
        ours = f"https://raw.githubusercontent.com/{TWDA_FORK_REPO}/{branch}/{path}"
        if branch in open_branches:
            where, published = "open", await _count(ours)
        else:
            where = "archived"
            published = await _count(
                f"https://raw.githubusercontent.com/{TWDA_TARGET_REPO}/master/{path}"
            )
        if published == attested:
            return None
        if published is None:
            return f"not in the archive  → {attested}", False
        if published < 0:
            return f"no count line  → {attested}", False
        if where == "archived":
            sent = await _count(ours)
            if sent is not None and sent != published:
                return f"hand-corrected  {sent} → {published}, not {attested}", False
        if attested < TWDA_MIN_PLAYERS:
            return f"below floor  {published} → {attested}", False
        return f"{where}  {published} → {attested}", True
    if (
        status.outcome == TwdaOutcome.SKIPPED
        and status.reason == "too_few_players"
        and t.rounds
        and not t.external_ids.get("twda")
        and attested >= TWDA_MIN_PLAYERS
    ):
        return f"too small  now {attested}", True
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
        open_branches = await _open_branches()
        listed: list[str] = []
        held = 0
        for (full,) in rows:
            t = db.decode_json(full, Tournament)
            candidate = await _candidate(t, open_branches)
            if not candidate:
                continue
            line, resubmit = candidate
            if resubmit:
                listed.append(t.uid)
            else:
                held += 1
            print(f"{t.event_code or t.uid:<12} {line:<30} {t.name}")
        print(f"\n{len(listed)} to resubmit, {held} held for the TWDA admin")
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
