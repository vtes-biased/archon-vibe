"""Ordered rewrites of stored documents, run from the lifespan before serving.

Report mode runs the same guards without the app:

    uv run python -m backend.src.migrations --dsn "$DATABASE_URL"
    uv run python -m backend.src.migrations --dsn "$DATABASE_URL" --apply
"""

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from . import db
from .models import ObjectType, Role

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Migration:
    name: str
    obj_type: ObjectType
    pending: str
    rewrite: Callable[[dict], None]


def _rename_judgekin_to_sheriff(full_data: dict) -> None:
    full_data["roles"] = [
        Role.SHERIFF if role == "Judgekin" else role
        for role in full_data.get("roles") or []
    ]


def _collapse_link_moderation(full_data: dict) -> None:
    for link in full_data.get("community_links") or []:
        moderation = link.get("moderation")
        if isinstance(moderation, dict):
            # A promotion with no scope was already read as unmoderated.
            link["moderation"] = (
                "hidden"
                if moderation["status"] == "hidden"
                else moderation.get("scope")
            )


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        name="rename-judgekin-to-sheriff",
        obj_type=ObjectType.USER,
        pending="""
            SELECT uid FROM objects
            WHERE type = 'user' AND "full"->'roles' ? 'Judgekin'
            ORDER BY uid
        """,
        rewrite=_rename_judgekin_to_sheriff,
    ),
    Migration(
        name="collapse-link-moderation",
        obj_type=ObjectType.USER,
        pending="""
            SELECT uid FROM objects
            WHERE type = 'user'
              AND jsonb_path_exists("full", '$.community_links[*].moderation.status')
            ORDER BY uid
        """,
        rewrite=_collapse_link_moderation,
    ),
)

_LOCK_ROW = 'SELECT "full", deleted_at FROM objects WHERE uid = %s FOR UPDATE'


async def run_migrations(*, apply: bool = True) -> dict[str, int]:
    """Rewrite every pending row, entry by entry, and return the counts."""
    counts: dict[str, int] = {}
    for migration in MIGRATIONS:
        async with db.get_connection() as conn:
            result = await conn.execute(migration.pending)
            uids = [row[0] for row in await result.fetchall()]
        if not uids:
            continue
        if not apply:
            counts[migration.name] = len(uids)
            continue

        rewritten = 0
        async with db.get_connection() as conn:
            for uid in uids:
                # One transaction PER ROW: a shared CURRENT_TIMESTAMP is what a
                # catch-up cursor's strict `modified_at > since` splits across.
                async with conn.transaction():
                    result = await conn.execute(_LOCK_ROW, (uid,))
                    row = await result.fetchone()
                    if row is None:
                        continue  # hard-deleted since the sweep began
                    full_data, deleted_at = row
                    migration.rewrite(full_data)
                    await db.save_object(
                        migration.obj_type,
                        uid,
                        full_data,
                        conn=conn,
                        deleted_at=deleted_at.isoformat() if deleted_at else None,
                    )
                    rewritten += 1
        counts[migration.name] = rewritten
        logger.info(f"Migration {migration.name}: rewrote {rewritten} row(s)")
    return counts


async def _report(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    await db.init_db()
    try:
        counts = await run_migrations(apply=args.apply)
    finally:
        await db.close_db()
    verb = "rewritten" if args.apply else "to rewrite (use --apply)"
    for migration in MIGRATIONS:
        print(f"{migration.name}: {counts.get(migration.name, 0)} row(s) {verb}.")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the stored-value migrations.")
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--apply", action="store_true", help="write the rewrites")
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(_report(parse_args())))
