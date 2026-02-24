#!/usr/bin/env python3
"""One-time migration: backfill the unified objects table from old per-type tables.

NOTE: This script was used during the migration from per-type tables to the
unified objects table. The old tables (users, sanctions, tournaments, ratings,
leagues) no longer exist. This script is kept for reference only.

Usage (historical):
    python3 -m backend.scripts.backfill_objects [--dry-run]
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime

import msgspec

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Ensure backend/src is importable
sys.path.insert(0, ".")

from backend.src.access_levels import compute_full, compute_member, compute_public
from backend.src.db import (
    close_db,
    get_connection,
    init_db,
    stream_objects,
)
from backend.src.models import League, Rating, Sanction, Tournament, User

_encoder = msgspec.json.Encoder()

_UPSERT_SQL = (
    'INSERT INTO objects (uid, type, deleted_at, "public", "member", "full")'
    " VALUES (%s, %s, %s::timestamp, %s::jsonb, %s::jsonb, %s::jsonb)"
    " ON CONFLICT (uid) DO UPDATE SET type=EXCLUDED.type, deleted_at=EXCLUDED.deleted_at,"
    ' "public"=EXCLUDED."public", "member"=EXCLUDED."member", "full"=EXCLUDED."full"'
)


def _to_dict(obj: msgspec.Struct) -> dict:
    return msgspec.to_builtins(obj)


def _json_str(d: dict | None) -> str | None:
    if d is None:
        return None
    return _encoder.encode(d).decode("utf-8")


async def backfill(dry_run: bool = False) -> None:
    await init_db()
    try:
        stats: dict[str, int] = {}

        # --- Users ---
        count = 0
        async for batch, _ in stream_objects("users", User, batch_size=500):
            if dry_run:
                count += len(batch)
                continue
            async with get_connection() as conn:
                for user in batch:
                    d = _to_dict(user)
                    pub = compute_public("user", d)
                    mem = compute_member("user", d)
                    full = compute_full("user", d)
                    deleted_at = d.get("deleted_at")
                    await conn.execute(
                        _UPSERT_SQL,
                        (
                            user.uid,
                            "user",
                            deleted_at,
                            _json_str(pub),
                            _json_str(mem),
                            _json_str(full),
                        ),
                    )
                    count += 1
        stats["users"] = count
        logger.info(f"Users: {count}")

        # --- Embed ratings into users ---
        rating_count = 0
        async for batch, _ in stream_objects("ratings", Rating, batch_size=500):
            if dry_run:
                rating_count += len(batch)
                continue
            async with get_connection() as conn:
                for rating in batch:
                    # Read existing user from objects table
                    row = await (
                        await conn.execute(
                            "SELECT \"full\" FROM objects WHERE uid = %s AND type = 'user'",
                            (rating.user_uid,),
                        )
                    ).fetchone()
                    if not row:
                        logger.warning(
                            f"Rating {rating.uid}: user {rating.user_uid} not found"
                        )
                        continue

                    user_data = (
                        row[0]
                        if isinstance(row[0], dict)
                        else msgspec.json.decode(row[0])
                    )

                    # Embed rating fields
                    rd = _to_dict(rating)
                    for field in (
                        "constructed_online",
                        "constructed_offline",
                        "limited_online",
                        "limited_offline",
                        "wins",
                    ):
                        if rd.get(field) is not None:
                            user_data[field] = rd[field]

                    # Recompute projections
                    pub = compute_public("user", user_data)
                    mem = compute_member("user", user_data)
                    full = compute_full("user", user_data)
                    await conn.execute(
                        """UPDATE objects SET "public"=%s::jsonb, "member"=%s::jsonb, "full"=%s::jsonb
                           WHERE uid = %s""",
                        (
                            _json_str(pub),
                            _json_str(mem),
                            _json_str(full),
                            rating.user_uid,
                        ),
                    )
                    rating_count += 1
        stats["ratings_embedded"] = rating_count
        logger.info(f"Ratings embedded: {rating_count}")

        # --- Sanctions ---
        count = 0
        async for batch, _ in stream_objects("sanctions", Sanction, batch_size=500):
            if dry_run:
                count += len(batch)
                continue
            async with get_connection() as conn:
                for s in batch:
                    d = _to_dict(s)
                    pub = compute_public("sanction", d)
                    mem = compute_member("sanction", d)
                    full = compute_full("sanction", d)
                    deleted_at = d.get("deleted_at")
                    await conn.execute(
                        _UPSERT_SQL,
                        (
                            s.uid,
                            "sanction",
                            deleted_at,
                            _json_str(pub),
                            _json_str(mem),
                            _json_str(full),
                        ),
                    )
                    count += 1
        stats["sanctions"] = count
        logger.info(f"Sanctions: {count}")

        # --- Tournaments + Deck extraction ---
        t_count = 0
        d_count = 0
        async for batch, _ in stream_objects("tournaments", Tournament, batch_size=100):
            if dry_run:
                t_count += len(batch)
                continue
            async with get_connection() as conn:
                for t in batch:
                    td = _to_dict(t)

                    # Extract decks as separate DeckObjects
                    decks_dict = td.pop("decks", {})
                    # Also remove my_tables (deprecated)
                    td.pop("my_tables", None)

                    pub = compute_public("tournament", td)
                    mem = compute_member("tournament", td)
                    full = compute_full("tournament", td)
                    deleted_at = td.get("deleted_at")
                    await conn.execute(
                        _UPSERT_SQL,
                        (
                            t.uid,
                            "tournament",
                            deleted_at,
                            _json_str(pub),
                            _json_str(mem),
                            _json_str(full),
                        ),
                    )
                    t_count += 1

                    # Create DeckObject rows from tournament.decks
                    from uuid6 import uuid7

                    for user_uid, deck_list in decks_dict.items():
                        if not isinstance(deck_list, list):
                            continue
                        for deck_data in deck_list:
                            if not isinstance(deck_data, dict):
                                continue
                            deck_uid = str(uuid7())
                            deck_obj = {
                                "uid": deck_uid,
                                "modified": datetime.now(UTC).isoformat(),
                                "deleted_at": None,
                                "tournament_uid": t.uid,
                                "user_uid": user_uid,
                                "round": deck_data.get("round"),
                                "name": deck_data.get("name", ""),
                                "author": deck_data.get("author", ""),
                                "comments": deck_data.get("comments", ""),
                                "cards": deck_data.get("cards", {}),
                                "attribution": deck_data.get("attribution"),
                            }
                            dpub = compute_public("deck", deck_obj)
                            dmem = compute_member("deck", deck_obj)
                            dfull = compute_full("deck", deck_obj)
                            await conn.execute(
                                """INSERT INTO objects (uid, type, deleted_at, "public", "member", "full")
                                   VALUES (%s, 'deck', NULL, %s::jsonb, %s::jsonb, %s::jsonb)
                                   ON CONFLICT (uid) DO NOTHING""",
                                (
                                    deck_uid,
                                    _json_str(dpub),
                                    _json_str(dmem),
                                    _json_str(dfull),
                                ),
                            )
                            d_count += 1

        stats["tournaments"] = t_count
        stats["decks_extracted"] = d_count
        logger.info(f"Tournaments: {t_count}, Decks extracted: {d_count}")

        # --- Leagues ---
        count = 0
        async for batch, _ in stream_objects("leagues", League, batch_size=500):
            if dry_run:
                count += len(batch)
                continue
            async with get_connection() as conn:
                for lg in batch:
                    d = _to_dict(lg)
                    pub = compute_public("league", d)
                    mem = compute_member("league", d)
                    full = compute_full("league", d)
                    deleted_at = d.get("deleted_at")
                    await conn.execute(
                        _UPSERT_SQL,
                        (
                            lg.uid,
                            "league",
                            deleted_at,
                            _json_str(pub),
                            _json_str(mem),
                            _json_str(full),
                        ),
                    )
                    count += 1
        stats["leagues"] = count
        logger.info(f"Leagues: {count}")

        logger.info(f"Backfill complete: {stats}")

    finally:
        await close_db()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        logger.info("DRY RUN — no writes will be performed")
    asyncio.run(backfill(dry_run=dry_run))
