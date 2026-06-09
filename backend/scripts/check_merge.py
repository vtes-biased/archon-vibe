"""Verify the ETL → VEKN-sync merge didn't corrupt migrated data.

Run with --snapshot BEFORE the VEKN sync (records ETL-only baseline), then with
--check AFTER the sync (asserts invariants + compares to the baseline).

    DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_new \\
    uv run python scripts/check_merge.py --snapshot
    # … run scripts/run_vekn_sync.py …
    DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_new \\
    uv run python scripts/check_merge.py --check
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import psycopg

SNAP = Path("/tmp/merge_baseline.json")
FAIL, OK, WARN = "\033[31mFAIL\033[0m", "\033[32mok\033[0m", "\033[33mwarn\033[0m"

# Roles VEKN sync cannot derive (it only knows Prince/NC/IC/static-judges); these
# must survive the sync on migrated users.
PROTECTED_ROLES = ("Judge", "Judgekin", "Ethics", "Rulemonger", "PTC", "PT", "DEV")

METRICS = {
    "users": "SELECT count(*) FROM objects WHERE type='user' AND deleted_at IS NULL",
    "users_with_vekn_id": "SELECT count(*) FROM objects WHERE type='user' AND COALESCE(\"full\"->>'vekn_id','')<>''",
    "distinct_vekn_ids": "SELECT count(DISTINCT \"full\"->>'vekn_id') FROM objects WHERE type='user' AND COALESCE(\"full\"->>'vekn_id','')<>''",
    "tournaments": "SELECT count(*) FROM objects WHERE type='tournament'",
    "tournaments_with_rounds": "SELECT count(*) FROM objects WHERE type='tournament' AND jsonb_array_length(COALESCE(\"full\"->'rounds','[]'::jsonb))>0",
    "distinct_vekn_event_ids": "SELECT count(DISTINCT \"full\"->'external_ids'->>'vekn') FROM objects WHERE type='tournament' AND \"full\"->'external_ids'->>'vekn' IS NOT NULL",
    "tournaments_with_vekn_event_id": "SELECT count(*) FROM objects WHERE type='tournament' AND \"full\"->'external_ids'->>'vekn' IS NOT NULL",
    "discord_auth": "SELECT count(*) FROM auth_methods WHERE data->>'method_type'='discord'",
    "users_with_protected_role": f"SELECT count(*) FROM objects WHERE type='user' AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(\"full\"->'roles') r WHERE r IN {PROTECTED_ROLES})",
    "vekn_synced": "SELECT count(*) FROM objects WHERE type='user' AND (\"full\"->>'vekn_synced')::bool",
}


async def gather(conn) -> dict[str, int]:
    out = {}
    for name, q in METRICS.items():
        out[name] = (await (await conn.execute(q)).fetchone())[0]
    return out


async def main(args) -> int:
    conn = await psycopg.AsyncConnection.connect(args.dsn, autocommit=True)
    m = await gather(conn)
    await conn.close()

    if args.snapshot:
        SNAP.write_text(json.dumps(m, indent=2))
        print(f"baseline written to {SNAP}:")
        for k, v in m.items():
            print(f"  {k:34s} {v}")
        return 0

    base = json.loads(SNAP.read_text()) if SNAP.exists() else {}
    fails = 0

    def check(label, ok, detail="", hard=True):
        nonlocal fails
        print(f"  [{OK if ok else (FAIL if hard else WARN)}] {label} — {detail}")
        if not ok and hard:
            fails += 1

    print("== absolute invariants ==")
    check(
        "no duplicate vekn_id (1 user per vekn member)",
        m["users_with_vekn_id"] == m["distinct_vekn_ids"],
        f"{m['users_with_vekn_id']} users / {m['distinct_vekn_ids']} distinct",
    )
    # old archon already has some tournaments sharing a vekn event id; assert the
    # sync didn't ADD duplicates (gap must not grow vs the ETL baseline).
    gap = m["tournaments_with_vekn_event_id"] - m["distinct_vekn_event_ids"]
    base_gap = base.get("tournaments_with_vekn_event_id", 0) - base.get(
        "distinct_vekn_event_ids", 0
    )
    check(
        "sync added no duplicate vekn event id",
        gap <= base_gap,
        f"dup gap {gap} vs baseline {base_gap}",
    )

    print("== preserved vs ETL baseline ==")
    check(
        "rich tournaments' rounds preserved (not wiped)",
        m["tournaments_with_rounds"] == base.get("tournaments_with_rounds"),
        f"{m['tournaments_with_rounds']} vs {base.get('tournaments_with_rounds')}",
    )
    check(
        "discord auth methods untouched",
        m["discord_auth"] == base.get("discord_auth"),
        f"{m['discord_auth']} vs {base.get('discord_auth')}",
    )
    check(
        "archon protected roles intact",
        m["users_with_protected_role"] == base.get("users_with_protected_role"),
        f"{m['users_with_protected_role']} vs {base.get('users_with_protected_role')}",
    )

    print("== sync activity (info) ==")
    print(
        f"  users {base.get('users')} → {m['users']} (+{m['users'] - base.get('users', 0)} created)"
    )
    print(
        f"  tournaments {base.get('tournaments')} → {m['tournaments']} (+{m['tournaments'] - base.get('tournaments', 0)})"
    )
    print(f"  vekn_synced users: {m['vekn_synced']}")

    print(f"\n{'PASSED' if fails == 0 else 'FAILED'} — {fails} hard failure(s)")
    return 1 if fails else 0


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--dsn", default=os.getenv("DATABASE_URL") or os.getenv("NEW_DATABASE_URL")
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--snapshot", action="store_true")
    g.add_argument("--check", action="store_true")
    a = p.parse_args()
    if not a.dsn:
        p.error("DATABASE_URL required")
    return a


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
