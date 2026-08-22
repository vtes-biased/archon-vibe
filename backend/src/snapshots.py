"""One gzip JSONL file per access level, generated in a single unordered pass so
each line self-describes its type. The `api` file is the public API's bulk
export; no app client is ever served it. The `eof` trailer is load-bearing: a streaming
client has already written rows by the time it could notice a truncated file."""

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
_LEVELS = ("public", "member", "api", "full")


def _snapshot_path(level: str) -> Path:
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

    async with batch_read_connection() as conn:
        # DB-clock instant taken BEFORE any row is read, so any row modified after
        # is either in the file or caught by since-delta — a post-read max could miss one.
        gen_row = await (await conn.execute("SELECT now()::timestamp")).fetchone()
        generated_at = gen_row[0].isoformat()

        # Every file comes from ONE pass, so all must be open at once. Temp file +
        # atomic rename per level: a failed generation leaves the previous snapshot in place.
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

            # aclosing: a write failure must unwind the streamer's cursor+transaction
            # NOW, before batch_read_connection releases the conn, not at GC.
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
