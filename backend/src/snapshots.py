"""Snapshot generation for the new sync architecture.

Generates one gzip-compressed JSONL (line-delimited JSON) file per access level,
holding every non-deleted object the level can see. Line-delimited rather than one
big array so the client can ingest it as a stream — parse a line, write it, drop it —
instead of holding the compressed bytes, the decompressed text and the parsed object
graph in memory at once.

Format (one JSON object per line):

    {"type":"header","version":2,"timestamp":"...","generated_at":"..."}
    {"type":"user","data":{...}}
    ...
    {"type":"eof","count":30216}

Rows are NOT grouped by type — one unordered pass interleaves them, which is exactly
what makes the single-scan read possible, so each line carries its own type tag. The
`eof` trailer is load-bearing: a streaming client has already written rows to storage
by the time it could notice a truncated file, so completeness must be explicit.
"""

import gzip
import io
import logging
import os
import tempfile
import time
from contextlib import aclosing
from pathlib import Path

logger = logging.getLogger(__name__)

# Directory for snapshot files
SNAPSHOT_DIR = Path(os.getenv("SNAPSHOT_DIR", "/tmp/archon_snapshots"))

# Bumped when the file format changes in a way an older client can't read. The client
# checks it on the header line and refuses the file rather than mis-parsing it.
SNAPSHOT_FORMAT_VERSION = 2

# Column order of the projections in a stream_objects_snapshot row, after `type`.
_LEVELS = ("public", "member", "full")


def _snapshot_path(level: str) -> Path:
    """Get the path for a snapshot file at a given level."""
    return SNAPSHOT_DIR / f"{level}.jsonl.gz"


async def generate_snapshots() -> dict[str, int]:
    """Generate the snapshot file for every access level in ONE pass over `objects`.

    Returns dict of {level: object_count}.
    Reads the {level}::text columns directly — no Python deserialization.
    """
    from .db import _pool, batch_read_connection, stream_objects_snapshot

    if not _pool:
        raise RuntimeError("Database not initialized")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    counts = dict.fromkeys(_LEVELS, 0)

    # Relaxed-timeout session for the whole generation (see batch_read_connection).
    async with batch_read_connection() as conn:
        # DB-clock instant this generation started, taken BEFORE any row is read — it
        # is both the freshness signal the client echoes on /stream (so the staleness
        # guard measures real client-away time) and the `since` cursor it resumes from.
        # Load-bearing that it precedes the read: any row modified after it is either
        # already in the file (harmless re-delivery) or caught by the since-delta. A
        # max(modified_at) over the rows read would need its own whole-heap scan to be
        # any safer, and a max over rows read at DIFFERENT instants is not safe at all
        # — it can exceed the modified_at of a row the file missed, which is silent
        # permanent staleness (and, for a tombstone, a ghost the 30-day purge
        # eventually makes unrepairable). `::timestamp` keeps it naive, in the same
        # clock/format as modified_at, so the server compares without tz skew.
        gen_row = await (await conn.execute("SELECT now()::timestamp")).fetchone()
        generated_at = gen_row[0].isoformat()

        # All three files are written from ONE pass, so they must all be open at once.
        # Temp file + atomic rename per level, as before: a failed generation leaves
        # the previous complete snapshot in place rather than publishing a partial one.
        tmp_paths: dict[str, str] = {}
        writers: dict[str, io.TextIOWrapper] = {}
        try:
            for level in _LEVELS:
                fd, tmp_paths[level] = tempfile.mkstemp(dir=SNAPSHOT_DIR, suffix=".tmp")
                os.close(fd)
                writers[level] = gzip.open(
                    tmp_paths[level], "wt", encoding="utf-8", compresslevel=6
                )
                writers[level].write(
                    f'{{"type":"header","version":{SNAPSHOT_FORMAT_VERSION},'
                    f'"timestamp":"{generated_at}","generated_at":"{generated_at}"}}\n'
                )

            # aclosing: a write failure mid-iteration must unwind the streamer's
            # cursor+transaction NOW (before batch_read_connection releases the conn),
            # not at GC on an already-reborrowed conn.
            async with aclosing(stream_objects_snapshot(conn=conn)) as batches:
                async for rows in batches:
                    for obj_type, *projections in rows:
                        # `{"type":"x","data":` + the raw column + `}` — string concat
                        # around the stored JSON, so no row is ever deserialized here.
                        prefix = f'{{"type":"{obj_type}","data":'
                        for level, projection in zip(_LEVELS, projections, strict=True):
                            # NULL = this level can't see the object at all.
                            if projection is None:
                                continue
                            writers[level].write(f"{prefix}{projection}}}\n")
                            counts[level] += 1

            for level in _LEVELS:
                writers[level].write(f'{{"type":"eof","count":{counts[level]}}}\n')
                writers[level].close()
                os.rename(tmp_paths[level], _snapshot_path(level))
        except BaseException:
            for level, path in tmp_paths.items():
                writer = writers.get(level)
                if writer is not None:
                    try:
                        writer.close()
                    except OSError:
                        pass
                try:
                    os.unlink(path)
                except OSError:
                    pass
            raise

    elapsed = time.time() - start
    sizes = {lvl: _snapshot_path(lvl).stat().st_size / 1024 for lvl in _LEVELS}
    logger.info(
        "Snapshots in one pass, %.2fs: %s",
        elapsed,
        ", ".join(
            f"{lvl} {counts[lvl]} objects/{sizes[lvl]:.1f} KB" for lvl in _LEVELS
        ),
    )
    return counts


def get_snapshot_path(level: str) -> Path | None:
    """Get the path for a snapshot file, or None if it doesn't exist."""
    path = _snapshot_path(level)
    return path if path.exists() else None
