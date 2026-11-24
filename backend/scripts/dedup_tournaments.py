"""Audit and resolve duplicate live tournaments (same event, several live copies).

Historical import paths (the retired VEKN tournament sync, keyed on
`external_ids.vekn`, and the legacy-archon merge, keyed on the old uid /
`external_ids.archon` / old archon's `extra.vekn_id`) could insert two copies of
one event when an old event carried no vekn id.

    # report every group, with the metrics the choice hangs on
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/dedup_tournaments.py

    # write a proposed keep/drop per group, review it, then apply it
    … dedup_tournaments.py --emit-decisions /tmp/dedup.tsv
    … dedup_tournaments.py --apply /tmp/dedup.tsv

Reported groups are live copies of one event where SOME BUT NOT ALL copies hold a
vekn id. Copies that all lack one were never linked to anything.

Resolution is per group and NOT mechanical: the vekn-less copy is often the
richer one (it ran in the app; the vekn-linked copy can hold zero players). The
proposal ranks by play data, never by which copy holds the vekn id.

Applying a decision soft-deletes the losing copies (cascading their decks and
sanctions) and transplants `external_ids.vekn` onto the survivor so short-link
fallback keeps resolving. A loser's archive key travels the same way, as
`external_ids.twda_entry` — the survivor is the event that entry describes now,
and never a reconstruction, whatever the loser was.

Ratings are NOT recomputed here — the rating window aggregates whatever is live,
so if the report marks more than one copy of a group rating-eligible, both were
counted and a recompute is owed after applying (daily job or `recompute_all_ratings`).
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
from backend.src.decks import soft_delete_tournament  # noqa: E402
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


async def print_group(group: dict) -> tuple[list[Tournament], list[Tournament]]:
    """Print a group's copies and the double-rating warning; return (copies, rated)."""
    print(f"\n'{group['name']}' — {group['day']} ({len(group['uids'])} copies)")
    copies = []
    for uid in group["uids"]:
        t, line = await describe(uid)
        print(line)
        if t is not None:
            copies.append(t)
    rated = [t for t in copies if rating_eligible(t)]
    if len(rated) > 1:
        print(f"    ⚠ {len(rated)} copies are rating-eligible — points counted twice")
    return copies, rated


async def audit(emit_path: str | None) -> int:
    decisions: list[str] = []
    twda_groups = 0
    groups = await db.find_duplicate_tournament_groups()
    if not groups:
        print("No mixed-vekn duplicate groups.")
    double_rated = 0
    for group in sorted(groups, key=lambda g: (str(g["day"]), g["name"])):
        copies, rated = await print_group(group)
        if len(rated) > 1:
            double_rated += 1
        if not copies:
            continue
        # `richness` always ranks a one-player archive reconstruction last: right
        # for a true duplicate, destructive for a false pair off a generic event
        # name, and the script cannot tell them apart. Report, never propose.
        if any(t.external_ids.get("twda") for t in copies):
            twda_groups += 1
            print("    → no proposal: an archive reconstruction is in this group")
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

    if groups:
        print(
            f"\n{len(groups)} mixed-vekn group(s); {double_rated} "
            "double-counted in ratings."
        )
        if twda_groups:
            print(
                f"{twda_groups} of them hold an archive reconstruction and got no "
                "proposal — decide those by hand."
            )
    if emit_path:
        if decisions:
            Path(emit_path).write_text(
                "# keep_uid<TAB>drop_uid[,drop_uid]<TAB>vekn_id — review before --apply\n"
                + "\n".join(decisions)
                + "\n"
            )
            print(f"Proposed decisions written to {emit_path} — review before --apply.")
        else:
            print("No proposals — nothing written.")
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
        archive_key = ""
        for drop_uid in [u.strip() for u in drop_csv.split(",") if u.strip()]:
            if drop_uid == keep_uid:
                continue
            result = await soft_delete_tournament(drop_uid)
            if result:
                lost = result[0].external_ids
                archive_key = archive_key or lost.get("twda_entry") or lost.get("twda")
            print(f"  soft-deleted {drop_uid}" if result else f"  {drop_uid} <gone>")

        adopted = vekn and keep.external_ids.get("vekn") != vekn
        settles = archive_key and not (
            keep.external_ids.keys() & {"twda", "twda_entry"}
        )
        if adopted:
            keep.external_ids["vekn"] = vekn
        if settles:
            keep.external_ids["twda_entry"] = archive_key
        if adopted or settles:
            async with db.get_connection() as conn:
                await db.save_tournament(keep, conn=conn)
        if adopted:
            print(f"  {keep_uid} adopted vekn event {vekn}")
        if settles:
            print(f"  {keep_uid} adopted archive entry {archive_key}")
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
