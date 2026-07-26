"""Keyset pagination invariant for db.stream_objects_new.

The catch-up/snapshot streamer pages by (modified_at, uid) with a LIMIT instead
of one fetchall, to bound app heap. The risk is the batch seam: a run of rows
split by the LIMIT must be neither skipped nor duplicated. This drives the
400-user fixture through a small batch_size so the keyset-continuation branch
actually fires, and asserts full, in-order, duplicate-free coverage.
"""

import msgspec
import pytest
from src import db
from src.db import stream_objects_new, stream_objects_snapshot
from src.models import ObjectType


@pytest.mark.asyncio
async def test_stream_objects_keyset_covers_all_rows_across_batches(populated_db):
    expected = {u.uid for u in populated_db}  # 400 users → ≥8 batches at size 50
    seen: list[str] = []
    last_max = ""
    async for json_strings, batch_max in stream_objects_new(
        obj_type=ObjectType.USER, level="full", batch_size=50
    ):
        seen.extend(msgspec.json.decode(js.encode())["uid"] for js in json_strings)
        assert batch_max >= last_max  # batches ascend by modified_at
        last_max = batch_max
    assert len(seen) == len(expected)  # every row returned (no skip at the seam)
    assert len(set(seen)) == len(seen)  # exactly once (no dup at the seam)
    assert set(seen) == expected


@pytest.mark.asyncio
async def test_stream_objects_snapshot_covers_live_rows(populated_db):
    """The unordered server-side-cursor snapshot path must return every non-deleted
    row exactly once across fetchmany batches, and exclude soft-deleted rows."""
    # Soft-delete two users; a snapshot that leaked them fails the first assertion.
    for user in populated_db[:2]:
        await db.soft_delete_user(user.uid)

    async with db.get_connection() as conn:
        ground = await (
            await conn.execute(
                "SELECT uid FROM objects "
                "WHERE type = 'user' AND deleted_at IS NULL AND \"full\" IS NOT NULL"
            )
        ).fetchall()
    expected_uids = {r[0] for r in ground}

    seen: list[str] = []
    async with db.get_connection() as conn:  # server-side cursor needs a held conn
        async for json_strings in stream_objects_snapshot(
            "user",
            "full",
            conn=conn,
            batch_size=50,  # 398 live rows → ≥8 batches
        ):
            seen.extend(msgspec.json.decode(js.encode())["uid"] for js in json_strings)

    assert set(seen) == expected_uids  # every live row, deleted excluded
    assert len(seen) == len(set(seen))  # exactly once (no fetchmany-seam dup)
