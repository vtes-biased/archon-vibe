"""Compare the placement vekn.net actually stores against the one we would push.

Our own `standings` is the PRELIMINARY order — `ratings._final_standings` reorders
it into the placement sheet using `winner` — so comparing `standings[0]` against
`winner` finds every final won from a lower seat, not every record vekn.net got
wrong. And `vekn_pushed_at` is stamped by the legacy-archon migration and the
vekn.net importer too, not only by our push, so the stamp is no evidence that
this code uploaded anything. Neither question is answerable from our database
alone: only what vekn.net returns settles it.

So this reads. For every finished event carrying a vekn id, it fetches the event
and compares upstream's `pos` field against the placement `generate_archondata`
would send today, reporting the events that disagree and how.

Read-only — it never writes to vekn.net or to our database. It needs the VEKN
credentials, which the service env carries:

    sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \\
      /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/audit_vekn_placement.py'

`--limit N` stops after N events, for a quick sample against a live API.
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

from backend.src import db  # noqa: E402
from backend.src.db import decode_json, get_user_by_uid  # noqa: E402
from backend.src.models import ObjectType, Tournament  # noqa: E402
from backend.src.ratings import _final_standings  # noqa: E402
from backend.src.vekn_api import VEKNAPIClient, VEKNAPIConnectionError  # noqa: E402

# The rounds guard drops vekn.net imports, which carry standings but no round
# data. Legacy-archon migrations DO carry rounds and are deliberately kept: what
# upstream holds for them is exactly what is unknown.
CANDIDATES_QUERY = """
    SELECT "full" FROM objects
    WHERE type = %s
      AND deleted_at IS NULL
      AND "full"->>'state' = 'Finished'
      AND ("full"->'external_ids'->>'vekn') IS NOT NULL
      AND COALESCE("full"->>'winner', '') <> ''
      AND jsonb_array_length(COALESCE("full"->'rounds', '[]'::jsonb)) > 0
    ORDER BY "full"->>'start'
"""


async def _ours(t: Tournament) -> dict[str, int]:
    """{vekn_id: placement} as `generate_archondata` would emit it today."""
    out: dict[str, int] = {}
    for row in _final_standings(t):
        if row["non_competing"] or row["disqualified"] or row["no_show"]:
            continue
        user = await get_user_by_uid(row["user_uid"])
        if user and user.vekn_id:
            out[str(user.vekn_id)] = int(row["rank"])
    return out


def _theirs(event: dict) -> tuple[dict[str, int], int]:
    """({vekn_id: pos} as vekn.net holds it, upstream row count). `pos` on a DQ'd
    or withdrawn row is the field size rather than a placement, so those rows
    carry no placement. An empty map over a non-empty roster means upstream
    stores no placement for this event at all — not that it disagrees."""
    out: dict[str, int] = {}
    rows = event.get("players", []) or []
    for p in rows:
        vekn_id = str(p.get("veknid") or "")
        pos = str(p.get("pos") or "")
        if not vekn_id or not pos.isdigit():
            continue
        if str(p.get("dq") or "0") == "1" or str(p.get("wd") or "0") == "1":
            continue
        out[vekn_id] = int(pos)
    return out, len(rows)


def _calendar_rounds(raw: str) -> int:
    """Total rounds the calendar entry declares. The field reads like `3R+F` —
    a prelim count and an optional final — and the archon file's count includes
    the final, so `+F` must be added back rather than dropped the way
    `vekn_tournament_sync._parse_rounds` drops it for `max_rounds`."""
    m = re.match(r"\s*(\d+)", raw)
    if not m:
        return -1
    return int(m.group(1)) + (1 if "F" in raw.upper() else 0)


def _top(placement: dict[str, int], n: int) -> set[str]:
    return {v for v, pos in placement.items() if 1 <= pos <= n}


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    await db.init_db()
    client = VEKNAPIClient()
    checked = agreed = unreachable = 0
    wrong_crown: list[str] = []
    wrong_five: list[str] = []
    no_placement: list[str] = []
    round_mismatch = 0
    try:
        async with db.get_connection() as conn:
            rows = await (
                await conn.execute(CANDIDATES_QUERY, (ObjectType.TOURNAMENT,))
            ).fetchall()

        for row in rows:
            if args.limit and checked >= args.limit:
                break
            t = decode_json(row[0], Tournament)
            event_id = t.external_ids.get("vekn")
            try:
                event = await client.fetch_event(int(event_id))
            except (VEKNAPIConnectionError, ValueError) as e:
                unreachable += 1
                print(f"  ?  {event_id:>6} {t.name} — {e}")
                continue
            if not event:
                unreachable += 1
                print(f"  ?  {event_id:>6} {t.name} — no such event upstream")
                continue

            checked += 1
            ours = await _ours(t)
            theirs, upstream_rows = _theirs(event)
            if not theirs:
                # vekn.net refuses an upload whose round count disagrees with the
                # calendar, so the two counts are reported next to the absence.
                no_placement.append(str(event_id))
                ours_n = len(t.rounds) + (1 if t.finals else 0)
                raw = str(event.get("rounds") or "")
                theirs_n = _calendar_rounds(raw)
                flag = "ROUNDS" if theirs_n != ours_n else "      "
                round_mismatch += 1 if flag.strip() else 0
                print(
                    f"  NONE  {event_id:>6} {flag} ours:{ours_n} "
                    f"vekn:{theirs_n} ({raw or '?'}) {upstream_rows} row(s) — {t.name}"
                )
                continue

            our_first = {v for v, pos in ours.items() if pos == 1}
            their_first = {v for v, pos in theirs.items() if pos == 1}
            crown_differs = our_first != their_first
            five_differs = _top(ours, 5) != _top(theirs, 5)

            if not crown_differs and not five_differs:
                agreed += 1
                continue
            label = "CROWN" if crown_differs else "FIVE "
            (wrong_crown if crown_differs else wrong_five).append(str(event_id))
            print(f"  {label} {event_id:>6} {t.name}")
            print(f"        ours   1:{sorted(our_first)} top5:{sorted(_top(ours, 5))}")
            print(
                f"        vekn   1:{sorted(their_first)} top5:{sorted(_top(theirs, 5))}"
            )

        print()
        print(f"{checked} event(s) compared, {unreachable} unreachable.")
        print(f"  {agreed:>6} agree with vekn.net")
        print(f"  {len(no_placement):>6} hold no placement upstream at all")
        print(f"  {round_mismatch:>6} of those disagree with the calendar on rounds")
        print(f"  {len(wrong_crown):>6} crown a different player at position 1")
        print(f"  {len(wrong_five):>6} agree on the winner but not on the five")
        if wrong_crown:
            print(f"\nwrong crown: {','.join(wrong_crown)}")
        if wrong_five:
            print(f"wrong five: {','.join(wrong_five)}")
        if no_placement:
            print(f"no placement: {','.join(no_placement)}")
        return 0
    finally:
        await client.close()
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--limit", type=int, default=0, help="stop after N events")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
