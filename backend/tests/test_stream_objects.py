"""Streaming invariants for the two object streamers and the snapshot artifact.

`stream_objects_new` pages by (modified_at, uid) with a LIMIT instead of one
fetchall, to bound app heap. The risk is the batch seam: a run of rows split by
the LIMIT must be neither skipped nor duplicated. The 400-user fixture drives a
small batch_size so the keyset-continuation branch actually fires.

The snapshot test asserts the *shipped file*, not the streamer: the JSONL
bootstrap is the one path where a malformed byte means clients cannot load at
all, and the client relies on the eof trailer to tell complete from truncated.
"""

import gzip
import json

import msgspec
import pytest
from src import db, snapshots
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


@pytest.mark.asyncio
async def test_snapshot_files_are_complete_wellformed_jsonl(
    populated_db, tmp_path, monkeypatch
):
    """The generated snapshot must be readable exactly the way the client reads it:
    a header line, one tagged object per line, an eof trailer whose count matches
    the object lines actually present, soft-deleted rows excluded, and each level
    file carrying only what that projection can see."""
    # Soft-delete two users; a snapshot that leaked them fails the exclusion assert.
    for user in populated_db[:2]:
        await db.soft_delete_user(user.uid)

    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path)
    counts = await snapshots.generate_snapshots()

    # Ground truth per level: every live row whose projection for that level exists.
    ground: dict[str, set[str]] = {}
    async with db.get_connection() as conn:
        for level in ("public", "member", "full"):
            rows = await (
                await conn.execute(
                    f'SELECT uid FROM objects WHERE deleted_at IS NULL AND "{level}" IS NOT NULL'  # noqa: S608
                )
            ).fetchall()
            ground[level] = {r[0] for r in rows}
    deleted_uids = {u.uid for u in populated_db[:2]}

    per_level: dict[str, set[str]] = {}
    for level in ("public", "member", "full"):
        path = snapshots.get_snapshot_path(level)
        assert path is not None, f"{level} snapshot not published"
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            lines = [json.loads(line) for line in fh]

        header, *body, trailer = lines
        assert header["type"] == "header"
        assert header["version"] == snapshots.SNAPSHOT_FORMAT_VERSION
        # Both meta fields carry the generation instant — the client's `since` cursor
        # must be that, never a max over the rows read (see wiki/sync.md).
        assert header["timestamp"] == header["generated_at"]

        assert trailer["type"] == "eof"
        assert trailer["count"] == len(body) == counts[level]

        uids = {line["data"]["uid"] for line in body}
        assert all(line["type"] for line in body)  # every line self-describes its type
        assert len(uids) == len(body)  # no fetchmany-seam duplicate
        assert not (uids & deleted_uids)  # tombstones never ship in a snapshot
        assert uids == ground[level]  # exactly what this projection can see
        per_level[level] = uids

    # A narrower projection can only ever see a subset — a NULL column is skipped
    # for that file, never emitted as a null-bodied line.
    assert per_level["public"] <= per_level["member"] <= per_level["full"]
