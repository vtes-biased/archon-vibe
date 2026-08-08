"""Unstick a migrated tournament whose results never reached vekn.net.

Legacy archon left one event mid-flight: a trailing EMPTY round its own UI would
not let the organizer delete, which legacy's push validation then rejected, so
the results were never uploaded. The migration carried the shape over verbatim
and stamped `vekn_pushed_at` (imported history is stamped at import so batch_push
leaves it alone), so nothing on this side retried it either.

    # report what would change
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/fix_stuck_vekn_push.py --vekn 13379

    # write it
    … fix_stuck_vekn_push.py --vekn 13379 --apply

Three writes on one tournament:

1. clear `vekn_pushed_at` — the migration stamp is exactly what makes batch_push
   skip it (UNPUSHED_RESULTS_QUERY).
2. CancelRound on the trailing empty round — hard-removes the last round so the
   pushed archondata reports the rounds actually played (generate_archondata's
   nrounds is len(rounds) + finals). The app UI cannot do this: isRoundCancellable
   requires Playing AND no finals, and these events have finals. The engine allows
   it (require_state_or_finished).
3. FinishTournament — the push set is Finished-only, and the migration left this
   one Playing.

The next hourly batch_push then uploads results to the EXISTING calendar event:
`external_ids.vekn` is already set, so no duplicate event is created.

Order note for anyone doing this by hand through the API instead: clear
`vekn_pushed_at` FIRST. The action route stamps the sticky `vekn_results_stale`
when rounds change while `vekn_pushed_at` is set, which would read as "diverged
from vekn.net" on results vekn.net never received. This script bypasses the route,
so it just clears the stamp up front.

Targeted on purpose — never a sweep. A trailing empty round on a Playing
tournament is also the normal transient shape of a round an organizer has just
opened but not yet seated.

Saves without broadcasting, so connected clients pick the change up on their next
snapshot/reconnect rather than live.
"""

import argparse
import asyncio
import importlib.util
import json
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
from archon_engine import PyEngine  # noqa: E402

from backend.src import db  # noqa: E402
from backend.src.models import Tournament, TournamentState  # noqa: E402
from backend.src.routes.tournaments import (  # noqa: E402
    _build_decks_json,
    _process_deck_ops,
)

_engine = PyEngine()

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
        f"rounds={len(t.rounds)} tables_per_round={[len(r) for r in t.rounds]}\n"
        f"  finals={'y' if t.finals else '-'} standings={len(t.standings)} "
        f"winner={t.winner or '-'}\n"
        f"  vekn_pushed_at={t.vekn_pushed_at} vekn_results_stale={t.vekn_results_stale}"
    )


async def check(t: Tournament) -> list[str]:
    """Preconditions. Anything returned here blocks --apply."""
    problems = []
    if not t.external_ids.get("vekn"):
        problems.append("no external_ids.vekn — push would create a NEW calendar event")
    if not t.rounds:
        problems.append("no rounds")
    elif t.rounds[-1]:
        problems.append(
            f"last round is not empty ({len(t.rounds[-1])} tables) — nothing to remove"
        )
    elif len(t.rounds) < 2:
        problems.append(
            "removing the empty round would leave 0 rounds (push needs > 0)"
        )
    if t.state not in (
        TournamentState.PLAYING,
        TournamentState.WAITING,
        TournamentState.FINISHED,
    ):
        problems.append(f"state {t.state.value} cannot be finished")
    if not t.standings:
        problems.append("no standings — push_tournament_results would refuse")
    # Sanctions shift finals scoring when rounds.len() changes
    # (refresh_finals_scoring derives the finals round number from it), so a
    # tournament carrying any is out of scope for this repair.
    if await db.get_sanctions_for_tournament(t.uid):
        problems.append("tournament has sanctions — finals re-scoring is not in scope")
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


async def apply(t: Tournament) -> None:
    t.vekn_pushed_at = None
    t_json = msgspec.json.encode(t).decode()
    actor_json = json.dumps(
        {
            "uid": "fix_stuck_vekn_push",
            "roles": ["IC"],
            "is_organizer": True,
            "can_organize_league_uids": [],
            "now": datetime.now(UTC).isoformat(),
        }
    )
    decks_json = await _build_decks_json(t.uid)

    deck_ops: list = []
    for event in (
        {"type": "CancelRound", "round": len(t.rounds) - 1},
        {"type": "FinishTournament"},
    ):
        result = json.loads(
            _engine.process_tournament_event(
                t_json, json.dumps(event), actor_json, "[]", decks_json
            )
        )
        t_json = json.dumps(result["tournament"])
        deck_ops.extend(result.get("deck_ops", []))
        print(f"  applied {event['type']}")

    updated = msgspec.convert(json.loads(t_json), Tournament)
    updated.vekn_pushed_at = None  # authoritative: the engine round-trips the field
    updated.modified = datetime.now(UTC)
    async with db.get_connection() as conn:
        await db.save_tournament(updated, conn=conn)
    if deck_ops:
        await _process_deck_ops(deck_ops, updated.uid, org_uids=updated.organizers_uids)
        print(f"  processed {len(deck_ops)} deck op(s)")
    print("\nAfter:\n" + describe(updated))
    print("\nNext hourly batch_push will upload results to the existing vekn event.")


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
            print(
                f"\nWould: clear vekn_pushed_at, CancelRound round "
                f"{len(t.rounds) - 1} (empty), FinishTournament. Re-run with --apply."
            )
            return 0
        print("\nApplying:")
        await apply(t)
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
