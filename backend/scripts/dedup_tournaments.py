"""Audit and resolve duplicate live tournaments (same event, several live copies).

Two import paths create tournaments: the VEKN tournament sync (keyed on
`external_ids.vekn`) and the legacy-archon merge (keyed on the old uid /
`external_ids.archon` / old archon's `extra.vekn_id`). An old event that never
carried a vekn id is invisible to both keys, so each path inserted its own copy —
members see one event twice, the copies disagree on results, and the vekn-less
copy keeps retrying a calendar-event create that vekn.net rejects as already
existing. The import paths now match on name + start day, so this is about the
copies that already exist.

    # report every group, with the metrics the choice hangs on
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/dedup_tournaments.py

    # write a proposed keep/drop per group, review it, then apply it
    … dedup_tournaments.py --emit-decisions /tmp/dedup.tsv
    … dedup_tournaments.py --apply /tmp/dedup.tsv

Resolution is per group and NOT mechanical: the vekn-less copy is often the
richer one (it ran in the app; the vekn-linked copy can hold zero players). The
proposal ranks by play data, never by which copy holds the vekn id.

Applying a decision soft-deletes the losing copies (cascading their decks and
sanctions) and transplants `external_ids.vekn` onto the survivor. The transplant
is load-bearing: without it the next VEKN sync finds no live holder of that event
id and re-creates the copy just deleted.

Ratings are NOT recomputed here — the rating window aggregates whatever is live,
so if the report marks more than one copy of a group rating-eligible, both were
counted and a recompute is owed after applying (admin route, `recompute_all_ratings`).
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
from archon_engine import PyEngine  # noqa: E402

from backend.src import db  # noqa: E402
from backend.src.models import Tournament, TournamentState  # noqa: E402

_engine = PyEngine()


def rating_eligible(t: Tournament) -> bool:
    """Would this copy contribute rating points? Same predicate ratings.py applies."""
    if t.state != TournamentState.FINISHED:
        return False
    return _engine.ranking_eligibility(msgspec.json.encode(t).decode()) == "eligible"


def richness(t: Tournament) -> tuple:
    """Sort key for 'most complete copy' — play data first, vekn id never."""
    return (len(t.rounds), 1 if t.finals else 0, len(t.standings), len(t.players))


async def describe(uid: str) -> tuple[Tournament | None, str]:
    t = await db.get_tournament_by_uid(uid)
    if t is None:
        return None, f"    {uid}  <gone>"
    decks = await db.get_decks_for_tournament(uid)
    sanctions = await db.get_sanctions_for_tournament(uid)
    line = (
        f"    {uid}  {t.state.value:<12} vekn={t.external_ids.get('vekn') or '-':<6} "
        f"archon={'y' if t.external_ids.get('archon') else '-'}  "
        f"players={len(t.players):<3} rounds={len(t.rounds)} "
        f"finals={'y' if t.finals else '-'} standings={len(t.standings):<3} "
        f"decks={len(decks):<3} sanctions={len(sanctions):<2} "
        f"start={t.start.isoformat() if t.start else '-'} "
        f"rated={'YES' if rating_eligible(t) else 'no'}"
    )
    return t, line


async def audit(emit_path: str | None) -> int:
    groups = await db.find_duplicate_tournament_groups()
    if not groups:
        print("No duplicate live tournaments.")
        return 0

    decisions: list[str] = []
    double_rated = 0
    for group in sorted(groups, key=lambda g: (str(g["day"]), g["name"])):
        print(f"\n'{group['name']}' — {group['day']} ({len(group['uids'])} copies)")
        copies = []
        for uid in group["uids"]:
            t, line = await describe(uid)
            print(line)
            if t is not None:
                copies.append(t)
        rated = [t for t in copies if rating_eligible(t)]
        if len(rated) > 1:
            double_rated += 1
            print(
                f"    ⚠ {len(rated)} copies are rating-eligible — points counted twice"
            )
        if not copies:
            continue
        keep = max(copies, key=richness)
        drop = [t.uid for t in copies if t.uid != keep.uid]
        vekn = next(
            (t.external_ids["vekn"] for t in copies if t.external_ids.get("vekn")), ""
        )
        print(
            f"    → proposed keep {keep.uid}, drop {','.join(drop)}, vekn={vekn or '-'}"
        )
        decisions.append(f"{keep.uid}\t{','.join(drop)}\t{vekn}")

    print(
        f"\n{len(groups)} duplicate group(s); {double_rated} double-counted in ratings."
    )
    if emit_path:
        Path(emit_path).write_text(
            "# keep_uid<TAB>drop_uid[,drop_uid]<TAB>vekn_id — review before --apply\n"
            + "\n".join(decisions)
            + "\n"
        )
        print(f"Proposed decisions written to {emit_path} — review before --apply.")
    return 0


async def apply(path: str) -> int:
    errors = 0
    for lineno, raw in enumerate(Path(path).read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            print(f"line {lineno}: expected keep<TAB>drop[,drop][<TAB>vekn]")
            errors += 1
            continue
        keep_uid, drop_csv = parts[0].strip(), parts[1].strip()
        vekn = parts[2].strip() if len(parts) > 2 else ""
        keep = await db.get_tournament_by_uid(keep_uid)
        if keep is None or keep.deleted_at:
            print(f"line {lineno}: keep {keep_uid} is not live — skipped")
            errors += 1
            continue

        # Losers first: the survivor must never be the second live holder of an
        # event id, and their id is already in hand from the decisions file.
        for drop_uid in [u.strip() for u in drop_csv.split(",") if u.strip()]:
            if drop_uid == keep_uid:
                continue
            result = await db.soft_delete_tournament(drop_uid)
            print(f"  soft-deleted {drop_uid}" if result else f"  {drop_uid} <gone>")

        if vekn and keep.external_ids.get("vekn") != vekn:
            keep.external_ids["vekn"] = vekn
            async with db.get_connection() as conn:
                await db.save_tournament(keep, conn=conn)
            print(f"  {keep_uid} adopted vekn event {vekn}")
        print(f"resolved '{keep.name}' → {keep_uid}")
    return 1 if errors else 0


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        if args.apply:
            return await apply(args.apply)
        return await audit(args.emit_decisions)
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--emit-decisions", metavar="PATH", help="write proposed keep/drop")
    p.add_argument("--apply", metavar="PATH", help="apply a reviewed decisions file")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
