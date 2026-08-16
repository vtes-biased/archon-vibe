"""Post-ETL integrity checks for the archon → archon-vibe migration.

Runs against the OLD source DB and the NEW objects DB after
`migrate_from_archon.py`. Asserts row-count parity, scans for orphan references
inside the new DB, and spot-checks random tournaments field-by-field. Exits
non-zero if any hard check fails (counts / orphans); spot-check mismatches and
rating drift are reported as warnings.

Scope: the ROW-COUNT parity + uid-keyed spot-checks assume the **ETL/--truncate**
population (uids preserved, every member live). The merge / sync-first path is
validated by `check_merge.py` (vekn-keyed, snapshot deltas) instead — but the
**orphan + internal-consistency scans below are mode-agnostic** and are the key
guard for the member-uid remap (a missed ref field orphans here).

    cd backend
    OLD_DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_old \\
    NEW_DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_new \\
    uv run python scripts/migrate_validate.py [--samples 10]
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

# Make backend/ importable so the #216 fixup tables stay single-sourced.
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from scripts.migrate_from_archon import KNOWN_DROP, KNOWN_REMAP  # noqa: E402

FAIL = "\033[31mFAIL\033[0m"
OK = "\033[32mok\033[0m"
WARN = "\033[33mwarn\033[0m"


async def scalar(conn: psycopg.AsyncConnection, q: str, params=()) -> int:
    row = await (await conn.execute(q, params)).fetchone()
    return next(iter(row.values())) if row else 0


async def main(args) -> int:
    old = await psycopg.AsyncConnection.connect(
        args.old_dsn, autocommit=True, row_factory=dict_row
    )
    new = await psycopg.AsyncConnection.connect(
        args.new_dsn, autocommit=True, row_factory=dict_row
    )
    hard_failures = 0

    def check(label: str, ok: bool, detail: str = "", hard: bool = True) -> None:
        nonlocal hard_failures
        tag = OK if ok else (FAIL if hard else WARN)
        print(f"  [{tag}] {label}{(' — ' + detail) if detail else ''}")
        if not ok and hard:
            hard_failures += 1

    print("== row-count parity ==")
    old_members = await scalar(old, "SELECT count(*) FROM members")
    old_deletions = await scalar(old, "SELECT count(*) FROM member_deletions")
    old_leagues = await scalar(old, "SELECT count(*) FROM leagues")
    old_tournaments = await scalar(old, "SELECT count(*) FROM tournaments")

    new_live_users = await scalar(
        new, "SELECT count(*) FROM objects WHERE type='user' AND deleted_at IS NULL"
    )
    new_del_users = await scalar(
        new, "SELECT count(*) FROM objects WHERE type='user' AND deleted_at IS NOT NULL"
    )
    new_leagues = await scalar(new, "SELECT count(*) FROM objects WHERE type='league'")
    new_tournaments = await scalar(
        new, "SELECT count(*) FROM objects WHERE type='tournament'"
    )
    new_sanctions = await scalar(
        new, "SELECT count(*) FROM objects WHERE type='sanction'"
    )
    new_decks = await scalar(new, "SELECT count(*) FROM objects WHERE type='deck'")
    new_auth = await scalar(new, "SELECT count(*) FROM auth_methods")

    # #216 leaves the dropped + remapped VEKN-less participants UNSEEDED (allocated
    # ones stay live); see KNOWN_DROP / KNOWN_REMAP in migrate_from_archon.py.
    veknless_unseeded = len(KNOWN_DROP) + len(KNOWN_REMAP)
    check(
        "live users == members (minus #216 dropped/remapped)",
        new_live_users == old_members - veknless_unseeded,
        f"{new_live_users} vs {old_members} - {veknless_unseeded}",
    )
    check(
        "deleted-user shells <= member_deletions",
        new_del_users <= old_deletions,
        f"{new_del_users} vs {old_deletions}",
        hard=False,
    )
    check(
        "leagues match", new_leagues == old_leagues, f"{new_leagues} vs {old_leagues}"
    )
    check(
        "tournaments match",
        new_tournaments == old_tournaments,
        f"{new_tournaments} vs {old_tournaments}",
    )

    # sanctions: old union of member-embedded ∪ tournament-embedded, deduped by uid
    old_sanctions = await scalar(
        old,
        """
        SELECT count(DISTINCT uid) FROM (
            SELECT s->>'uid' AS uid FROM members m, jsonb_array_elements(m.data->'sanctions') s
            UNION ALL
            SELECT s->>'uid' FROM tournaments t,
                   jsonb_each(t.data->'sanctions') ts, jsonb_array_elements(ts.value) s
        ) x WHERE uid IS NOT NULL""",
    )
    check(
        "sanctions == old union",
        new_sanctions == old_sanctions,
        f"{new_sanctions} vs {old_sanctions}",
    )

    # decks: old monodeck (player.deck) + multideck seat decks
    old_decks = await scalar(
        old,
        """
        SELECT
          (SELECT count(*) FROM tournaments t, jsonb_each(t.data->'players') p
             WHERE jsonb_typeof(p.value->'deck')='object')
        + (SELECT count(*) FROM tournaments t,
             jsonb_array_elements(t.data->'rounds') rd, jsonb_array_elements(rd->'tables') tb,
             jsonb_array_elements(tb->'seating') s
             WHERE (t.data->>'multideck')::bool AND jsonb_typeof(s->'deck')='object')""",
    )
    check(
        "decks == old mono+multi", new_decks == old_decks, f"{new_decks} vs {old_decks}"
    )
    print(f"  (info) auth_methods={new_auth}")

    print("== orphan reference scan ==")
    orphans = {
        "tournament.players[].user_uid → user": """
            SELECT count(*) FROM objects t, jsonb_array_elements(t."full"->'players') p
            WHERE t.type='tournament'
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = p->>'user_uid')""",
        # rounds[][].seating[] player/judge refs (the most-likely-missed remap sites)
        # — judge_uid is optional so empty strings are skipped.
        "tournament.rounds[].seating[].player_uid → user": """
            SELECT count(*) FROM objects t,
                 jsonb_array_elements(t."full"->'rounds') rd,
                 jsonb_array_elements(rd) tb, jsonb_array_elements(tb->'seating') s
            WHERE t.type='tournament'
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = s->>'player_uid')""",
        "tournament.rounds[].seating[].judge_uid → user": """
            SELECT count(*) FROM objects t,
                 jsonb_array_elements(t."full"->'rounds') rd,
                 jsonb_array_elements(rd) tb, jsonb_array_elements(tb->'seating') s
            WHERE t.type='tournament' AND COALESCE(s->>'judge_uid','') <> ''
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = s->>'judge_uid')""",
        "tournament.finals.seating[].player_uid → user": """
            SELECT count(*) FROM objects t,
                 jsonb_array_elements(t."full"->'finals'->'seating') s
            WHERE t.type='tournament' AND t."full"->'finals' IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = s->>'player_uid')""",
        "tournament.finals.seating[].judge_uid → user": """
            SELECT count(*) FROM objects t,
                 jsonb_array_elements(t."full"->'finals'->'seating') s
            WHERE t.type='tournament' AND t."full"->'finals' IS NOT NULL
              AND COALESCE(s->>'judge_uid','') <> ''
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = s->>'judge_uid')""",
        "tournament.finals.seed_order[] → user": """
            SELECT count(*) FROM objects t,
                 jsonb_array_elements_text(t."full"->'finals'->'seed_order') so
            WHERE t.type='tournament' AND t."full"->'finals' IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = so)""",
        "tournament.standings[].user_uid → user": """
            SELECT count(*) FROM objects t, jsonb_array_elements(t."full"->'standings') st
            WHERE t.type='tournament'
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = st->>'user_uid')""",
        "tournament.organizers_uids[] → user": """
            SELECT count(*) FROM objects t,
                 jsonb_array_elements_text(t."full"->'organizers_uids') o
            WHERE t.type='tournament'
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = o)""",
        # #216 invariant: no participant ref resolves to a VEKN-less member. This
        # JOIN only catches an EXISTING one; a NON-existent ref is caught above.
        "tournament participant ref → VEKN-less member": """
            WITH refs AS (
                SELECT p->>'user_uid' u FROM objects t,
                     jsonb_array_elements(t."full"->'players') p WHERE t.type='tournament'
                UNION
                SELECT s->>'player_uid' FROM objects t,
                     jsonb_array_elements(t."full"->'rounds') rd, jsonb_array_elements(rd) tb,
                     jsonb_array_elements(tb->'seating') s WHERE t.type='tournament'
            )
            SELECT count(*) FROM refs JOIN objects u
              ON u.type='user' AND u.uid = refs.u
            WHERE COALESCE(u."full"->>'vekn_id','') = ''""",
        # every member-uid across ALL play data must also be a player — catches a
        # partial remap splitting one tournament across old/live uid spaces.
        "play-data uids ⊆ players[].user_uid (no uid split)": """
            WITH pdata AS (
                SELECT t.uid AS tuid, s->>'player_uid' AS u FROM objects t,
                     jsonb_array_elements(t."full"->'rounds') rd,
                     jsonb_array_elements(rd) tb, jsonb_array_elements(tb->'seating') s
                  WHERE t.type='tournament'
                UNION ALL
                SELECT t.uid, s->>'player_uid' FROM objects t,
                     jsonb_array_elements(t."full"->'finals'->'seating') s
                  WHERE t.type='tournament' AND t."full"->'finals' IS NOT NULL
                UNION ALL
                SELECT t.uid, so FROM objects t,
                     jsonb_array_elements_text(t."full"->'finals'->'seed_order') so
                  WHERE t.type='tournament' AND t."full"->'finals' IS NOT NULL
                UNION ALL
                SELECT t.uid, st->>'user_uid' FROM objects t,
                     jsonb_array_elements(t."full"->'standings') st
                  WHERE t.type='tournament'
            )
            SELECT count(*) FROM pdata
            WHERE NOT EXISTS (SELECT 1 FROM objects t2,
                     jsonb_array_elements(t2."full"->'players') p
                  WHERE t2.uid = pdata.tuid AND p->>'user_uid' = pdata.u)""",
        "tournament.winner → user": """
            SELECT count(*) FROM objects t
            WHERE t.type='tournament' AND COALESCE(t."full"->>'winner','') <> ''
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = t."full"->>'winner')""",
        "sanction.user_uid → user": """
            SELECT count(*) FROM objects s
            WHERE s.type='sanction'
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = s."full"->>'user_uid')""",
        "sanction.issued_by_uid → user": """
            SELECT count(*) FROM objects s
            WHERE s.type='sanction'
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = s."full"->>'issued_by_uid')""",
        "sanction.tournament_uid → tournament": """
            SELECT count(*) FROM objects s
            WHERE s.type='sanction' AND s."full"->>'tournament_uid' IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM objects t WHERE t.type='tournament' AND t.uid = s."full"->>'tournament_uid')""",
        "deck.user_uid → user": """
            SELECT count(*) FROM objects d
            WHERE d.type='deck'
              AND NOT EXISTS (SELECT 1 FROM objects u WHERE u.type='user' AND u.uid = d."full"->>'user_uid')""",
        "deck.tournament_uid → tournament": """
            SELECT count(*) FROM objects d
            WHERE d.type='deck'
              AND NOT EXISTS (SELECT 1 FROM objects t WHERE t.type='tournament' AND t.uid = d."full"->>'tournament_uid')""",
    }
    for label, q in orphans.items():
        n = await scalar(new, q)
        check(label, n == 0, f"{n} orphans")

    print("== projection sanity ==")
    null_full = await scalar(new, 'SELECT count(*) FROM objects WHERE "full" IS NULL')
    check('every object has a "full" projection', null_full == 0, f"{null_full} null")

    print("== semantic invariants ==")
    # standings are PRELIM-ONLY: standings VP == sum of seat VP over the stored
    # rounds (new `rounds` excludes finals; finals lives in `finals`).
    bad_prelim = await scalar(
        new,
        """
        SELECT count(*) FROM objects t WHERE t.type='tournament'
          AND jsonb_array_length(COALESCE(t."full"->'rounds','[]'::jsonb)) > 0
          AND abs(
                COALESCE((SELECT SUM((st->>'vp')::numeric) FROM jsonb_array_elements(t."full"->'standings') st),0)
              - COALESCE((SELECT SUM((s->'result'->>'vp')::numeric)
                          FROM jsonb_array_elements(t."full"->'rounds') rd,
                               jsonb_array_elements(rd) tb,
                               jsonb_array_elements(tb->'seating') s),0)
              ) > 0.01""",
    )
    check(
        "standings VP == prelim seat VP (finals excluded)",
        bad_prelim == 0,
        f"{bad_prelim} tournaments off",
    )

    # GW rule on prelim seats: gw=1 ⟺ vp≥2 ∧ sole table max. Recompute the rule in
    # SQL over every stored (prelim) table seat; any violation is a scoring bug.
    gw_violations = await scalar(
        new,
        """
        WITH seat AS (
            SELECT (s->'result'->>'vp')::numeric vp, (s->'result'->>'gw')::numeric gw,
                   (SELECT max((s2->'result'->>'vp')::numeric) FROM jsonb_array_elements(tb->'seating') s2) mx,
                   (SELECT count(*) FROM jsonb_array_elements(tb->'seating') s2
                      WHERE (s2->'result'->>'vp')::numeric =
                            (SELECT max((s3->'result'->>'vp')::numeric) FROM jsonb_array_elements(tb->'seating') s3)) max_cnt
            FROM objects t, jsonb_array_elements(t."full"->'rounds') rd,
                 jsonb_array_elements(rd) tb, jsonb_array_elements(tb->'seating') s
            WHERE t.type='tournament'
        )
        SELECT count(*) FROM seat
        WHERE (gw=1 AND NOT (vp>=2 AND vp=mx AND max_cnt=1)) OR (gw=0 AND vp>=2 AND vp=mx AND max_cnt=1)""",
    )
    check(
        "prelim GW obeys engine rule (vp≥2 ∧ sole max)",
        gw_violations == 0,
        f"{gw_violations} seats",
    )

    # deck visibility: no deck is public for a non-finished tournament
    bad_public = await scalar(
        new,
        """
        SELECT count(*) FROM objects d JOIN objects t ON t.uid = d."full"->>'tournament_uid'
        WHERE d.type='deck' AND (d."full"->>'public')::bool AND t."full"->>'state' <> 'Finished'""",
    )
    check(
        "no public deck on a non-finished tournament",
        bad_public == 0,
        f"{bad_public} decks",
    )

    # config-mode preservation: non-default modes must survive the migration
    for field, default in (("decklists_mode", "Winner"), ("standings_mode", "Private")):
        old_nondefault = await scalar(
            old,
            f"""
            SELECT count(*) FROM tournaments
            WHERE COALESCE(NULLIF(data->>'{field}',''), '{default}') <> '{default}'""",
        )
        new_nondefault = await scalar(
            new,
            f"""
            SELECT count(*) FROM objects
            WHERE type='tournament' AND "full"->>'{field}' <> '{default}'""",
        )
        check(
            f"{field} non-default preserved",
            new_nondefault == old_nondefault,
            f"{new_nondefault} vs {old_nondefault}",
        )

    print(f"== spot-check {args.samples} random tournaments ==")
    sample = await (
        await old.execute(
            "SELECT uid FROM tournaments ORDER BY random() LIMIT %s", (args.samples,)
        )
    ).fetchall()
    mismatches = 0
    for r in sample:
        uid = str(r["uid"])
        o = (
            await (
                await old.execute("SELECT data FROM tournaments WHERE uid=%s", (uid,))
            ).fetchone()
        )["data"]
        nrow = await (
            await new.execute('SELECT "full" AS f FROM objects WHERE uid=%s', (uid,))
        ).fetchone()
        if not nrow:
            print(f"  [{FAIL}] {uid} missing in new DB")
            mismatches += 1
            continue
        nf = nrow["f"]
        o_players = len(o.get("players") or {})
        n_players = len(nf.get("players") or [])
        o_winner = o.get("winner") or ""
        n_winner = nf.get("winner") or ""
        # finals.seed_order only exists for tournaments with round detail, so
        # compare the invariant that survives both: # of seeded finalists.
        o_seeds = len(o.get("finals_seeds") or [])
        n_finalists = sum(1 for p in (nf.get("players") or []) if p.get("finalist"))

        # Player.result is the prelim+finals aggregate on both sides — it must be
        # conserved exactly (old archon's stored aggregate == sum of preserved seats).
        def _sum(players, field):
            return round(
                sum(float((p.get("result") or {}).get(field, 0) or 0) for p in players),
                1,
            )

        old_players = list((o.get("players") or {}).values())
        new_players = nf.get("players") or []
        problems = []
        if o_players != n_players:
            problems.append(f"players {o_players}≠{n_players}")
        if o_winner != n_winner:
            problems.append(f"winner {o_winner!r}≠{n_winner!r}")
        if o_seeds != n_finalists:
            problems.append(f"finalists {o_seeds}≠{n_finalists}")
        for fld in ("vp", "gw", "tp"):
            if abs(_sum(old_players, fld) - _sum(new_players, fld)) > 0.01:
                problems.append(
                    f"total_{fld} {_sum(old_players, fld)}≠{_sum(new_players, fld)}"
                )
        if problems:
            print(
                f"  [{WARN}] {uid[:8]} {o.get('name', '')[:30]}: {', '.join(problems)}"
            )
            mismatches += 1
    check(
        f"spot-checks clean ({args.samples} sampled)",
        mismatches == 0,
        f"{mismatches} with diffs",
        hard=False,
    )

    await old.close()
    await new.close()
    print(
        f"\n{'PASSED' if hard_failures == 0 else 'FAILED'} — {hard_failures} hard failure(s)"
    )
    return 1 if hard_failures else 0


def parse_args():
    p = argparse.ArgumentParser(description="Validate archon → archon-vibe ETL output")
    p.add_argument("--old-dsn", default=os.getenv("OLD_DATABASE_URL"))
    p.add_argument(
        "--new-dsn", default=os.getenv("NEW_DATABASE_URL") or os.getenv("DATABASE_URL")
    )
    p.add_argument("--samples", type=int, default=10)
    a = p.parse_args()
    if not a.old_dsn or not a.new_dsn:
        p.error("OLD_DATABASE_URL and NEW_DATABASE_URL (or DATABASE_URL) required")
    return a


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
