"""One gzip JSONL file per access level, generated in a single unordered pass so
each line self-describes its type. The `api` file is the public API's bulk
export; no app client is ever served it. The `eof` trailer is load-bearing: a streaming
client has already written rows by the time it could notice a truncated file."""

import gzip
import io
import json
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

# Corpus fingerprint the published files were built from. Process memory, never
# disk: a restart must rebuild.
_built_from: tuple[int, str | None] | None = None
_built_counts: dict[str, int] = {}


def _snapshot_path(level: str) -> Path:
    return SNAPSHOT_DIR / f"{level}.jsonl.gz"


async def generate_snapshots() -> dict[str, int]:
    """Generate the snapshot file for every access level in ONE pass over `objects`,
    unless the corpus has not moved since the files on disk were built.

    Returns dict of {level: object_count}.
    Reads the {level}::text columns directly — no Python deserialization.
    """
    global _built_from, _built_counts

    from .db import _pool, batch_read_connection, stream_objects_snapshot

    if not _pool:
        raise RuntimeError("Database not initialized")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    counts = dict.fromkeys(_LEVELS, 0)

    async with batch_read_connection() as conn:
        # now() is transaction-start, so the anchor precedes the corpus read and a
        # row modified after it is either in the file or caught by since-delta.
        gen_row = await (
            await conn.execute(
                "SELECT count(*), max(modified_at), now()::timestamp FROM objects"
            )
        ).fetchone()
        row_count, newest, generated = gen_row
        sentinel = (row_count, newest.isoformat() if newest else None)
        generated_at = generated.isoformat()

        if sentinel == _built_from and all(
            _snapshot_path(level).exists() for level in _LEVELS
        ):
            logger.info("Snapshots unchanged at %s objects, skipped", row_count)
            return _built_counts

        # Every file comes from ONE pass, so all must be open at once. Temp file +
        # atomic rename per level: a failed generation leaves the previous snapshot in place.
        tmp_paths: dict[str, str] = {}
        writers: dict[str, io.TextIOWrapper] = {}
        try:
            for level in _LEVELS:
                fd, tmp_paths[level] = tempfile.mkstemp(dir=SNAPSHOT_DIR, suffix=".tmp")
                # 0640, not mkstemp's 0600: production nginx reads these via
                # X-Accel-Redirect, through the dir's setgid-assigned group.
                os.fchmod(fd, 0o640)
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

    _built_from, _built_counts = sentinel, counts

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


def snapshot_generated_at(level: str) -> str | None:
    """The generation instant stamped in a published file's header line.

    Read off the file rather than tracked in memory: a generation that failed or
    was skipped leaves an older file published, and it is that file's stamp a
    client echoes back.
    """
    try:
        with gzip.open(_snapshot_path(level), "rt", encoding="utf-8") as fh:
            return json.loads(fh.readline()).get("generated_at")
    except (OSError, ValueError):
        return None
