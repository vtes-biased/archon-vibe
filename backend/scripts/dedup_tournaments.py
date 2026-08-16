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

    # additionally probe both-vekn groups against the VEKN API
    # (needs VEKN_API_USERNAME / VEKN_API_PASSWORD — event reads are authenticated)
    … dedup_tournaments.py --probe-vekn [--emit-decisions /tmp/dedup.tsv]

Reported groups are live copies of one event where SOME BUT NOT ALL copies hold a
vekn id. Copies that all lack one were never linked to anything.

Copies that all hold (different) vekn ids are USUALLY distinct events — legacy
placeholder names like "Imported VTES Event" cover hundreds of separate 2005
events, dozens per day — but one real event entered twice on vekn.net lands in
the same shape, and only the VEKN API can tell them apart. `--probe-vekn` fetches
each id: a group where exactly one id is still live is a double-entry whose
duplicate was already deleted on vekn.net, resolvable with the same soft-delete +
transplant (the dead id cannot be re-created by the sync). All-live and all-dead
groups stay report-only: all-live is either distinct events or a double-entry
vekn.net must delete on its side first; a probe failure is reported as
unreachable, never mistaken for a deletion.

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
from backend.src.vekn_api import VEKNAPIClient, VEKNAPIConnectionError  # noqa: E402

_engine = PyEngine()

# Both-vekn groups bigger than this are placeholder-shaped (many distinct legacy
# events sharing a name+day), not double-entries — skipped, with a count logged.
PROBE_GROUP_CAP = 4


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


async def probe_both_vekn(decisions: list[str]) -> int:
    """Probe both-vekn groups against the VEKN API; propose where one id is dead."""
    groups = await db.find_both_vekn_tournament_groups()
    small = [g for g in groups if len(g["uids"]) <= PROBE_GROUP_CAP]
    if len(small) < len(groups):
        print(
            f"\n{len(groups) - len(small)} both-vekn group(s) over {PROBE_GROUP_CAP} "
            "copies skipped — placeholder-shaped, distinct events"
        )
    if not small:
        print("\nNo both-vekn groups to probe.")
        return 0
    print(f"\nProbing {len(small)} both-vekn group(s) against the VEKN API…")
    client = VEKNAPIClient()
    double_rated = 0
    actionable = 0
    all_live = 0
    try:
        for group in sorted(small, key=lambda g: (str(g["day"]), g["name"])):
            copies = []
            for uid in group["uids"]:
                t = await db.get_tournament_by_uid(uid)
                if t is not None:
                    copies.append(t)
            status: dict[str, bool | None] = {}  # id → live / dead(False) / unknown
            for t in copies:
                eid = t.external_ids["vekn"]
                if eid in status:
                    continue
                try:
                    status[eid] = await client.fetch_event(int(eid)) is not None
                except (VEKNAPIConnectionError, ValueError) as e:
                    print(f"probe failed for {eid}: {e}")
                    status[eid] = None
            if all(status.values()):
                # The common case — one line, or placeholder clusters drown the
                # actionable few. No dead id means the rated-count is just a hint.
                all_live += 1
                rated = [t for t in copies if rating_eligible(t)]
                hint = f" [{len(rated)} copies rated]" if len(rated) > 1 else ""
                print(
                    f"'{group['name']}' — {group['day']}: all ids live "
                    f"({', '.join(sorted(status))}) — no local action{hint}"
                )
                continue
            copies, rated = await print_group(group)
            if len(rated) > 1:
                double_rated += 1
            print(
                "    vekn.net: "
                + "  ".join(
                    f"{eid}={'live' if s else 'DELETED' if s is False else 'unreachable'}"
                    for eid, s in sorted(status.items())
                )
            )
            if None in status.values():
                print("    → probe incomplete — no proposal, re-run")
                continue
            live = sorted(eid for eid, s in status.items() if s)
            if len(live) != 1:
                print("    → no single live id — judgement call, no proposal")
                continue
            keep = max(copies, key=richness)
            drop = [t.uid for t in copies if t.uid != keep.uid]
            if (
                keep.external_ids.get("archon")
                and keep.external_ids.get("vekn") != live[0]
            ):
                print(
                    "    ⚠ survivor is legacy-merge-managed: update the legacy "
                    "tournament's extra.vekn_id too, or the nightly merge reverts "
                    "the transplant"
                )
            dead = ", ".join(sorted(set(status) - set(live)))
            print(
                f"    → proposed keep {keep.uid}, drop {','.join(drop)}, "
                f"vekn={live[0]} (dead: {dead})"
            )
            decisions.append(f"{keep.uid}\t{','.join(drop)}\t{live[0]}")
            actionable += 1
    finally:
        await client.close()
    print(
        f"\n{len(small)} both-vekn group(s) probed; {actionable} resolvable locally; "
        f"{all_live} all-live (vekn.net's record to reconcile); "
        f"{double_rated} double-counted in ratings."
    )
    return actionable


async def audit(emit_path: str | None, probe: bool) -> int:
    decisions: list[str] = []
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
    if probe:
        await probe_both_vekn(decisions)
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
        return await audit(args.emit_decisions, args.probe_vekn)
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--emit-decisions", metavar="PATH", help="write proposed keep/drop")
    p.add_argument(
        "--probe-vekn",
        action="store_true",
        help="also probe both-vekn groups against the VEKN API",
    )
    p.add_argument("--apply", metavar="PATH", help="apply a reviewed decisions file")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
