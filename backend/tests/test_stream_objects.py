"""Keyset pagination invariant for db.stream_objects_new.

The catch-up/snapshot streamer pages by (modified_at, uid) with a LIMIT instead
of one fetchall, to bound app heap. The risk is the batch seam: a run of rows
split by the LIMIT must be neither skipped nor duplicated. This drives the
400-user fixture through a small batch_size so the keyset-continuation branch
actually fires, and asserts full, in-order, duplicate-free coverage.
"""

import msgspec
import pytest
from src.db import stream_objects_new
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
