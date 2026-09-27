#!/usr/bin/env python3
"""Fail the build when an upgraded database would hold different indexes than a fresh one.

Run: just index-drift
"""

import os
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "backend/src/schema.sql"

ADMIN_URL = os.environ.get(
    "INDEX_DRIFT_DATABASE_URL",
    "postgresql://archon:archon_dev_password@localhost:5433/postgres",
)
UPGRADED = "archon_index_drift_upgraded"
FRESH = "archon_index_drift_fresh"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout


def previous_release() -> str:
    return git("describe", "--tags", "--abbrev=0", "--match", "v*", "HEAD^").strip()


def recreate(name: str) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def drop(name: str) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))


def indexes(name: str, *schemas: str) -> dict[str, str]:
    url = make_conninfo(ADMIN_URL, dbname=name)
    with psycopg.connect(url, autocommit=True) as conn:
        for schema in schemas:
            conn.execute(schema)  # ty: ignore[no-matching-overload]
        rows = conn.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'"
        ).fetchall()
    return dict(rows)


def main() -> int:
    tag = previous_release()
    old = git("show", f"{tag}:{SCHEMA}")
    new = (ROOT / SCHEMA).read_text(encoding="utf-8")
    try:
        recreate(UPGRADED)
        recreate(FRESH)
        upgraded = indexes(UPGRADED, old, new)
        fresh = indexes(FRESH, new)
    finally:
        drop(UPGRADED)
        drop(FRESH)

    violations = []
    for name in sorted(upgraded.keys() | fresh.keys()):
        before, after = upgraded.get(name), fresh.get(name)
        if before == after:
            continue
        if after is None:
            violations.append(f"  {name}: left behind from {tag}, never dropped")
        elif before is None:
            violations.append(f"  {name}: missing after applying over {tag}")
        else:
            violations.append(
                f"  {name}: edited since {tag} without a drop\n"
                f"    live:  {before}\n    fresh: {after}"
            )

    if violations:
        print(
            f"Index drift: {SCHEMA} applied over {tag} does not match a fresh "
            "database. Give a changed index a new name and DROP INDEX IF EXISTS "
            "the old one (wiki/hazards.md).\n" + "\n".join(violations)
        )
        return 1
    print(f"index-drift: ok ({len(fresh)} indexes, over {tag})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
