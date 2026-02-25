"""Snapshot generation for the new sync architecture.

Generates gzip-compressed JSON snapshots per access level.
Snapshots contain all non-deleted objects grouped by type.
Format: [{"type":"user","data":[...]}, ..., {"type":"meta","timestamp":"..."}]
"""

import gzip
import logging
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from .models import ObjectType

logger = logging.getLogger(__name__)

# Directory for snapshot files
SNAPSHOT_DIR = Path(os.getenv("SNAPSHOT_DIR", "/tmp/archon_snapshots"))
OBJECT_TYPES = list(ObjectType)


def _snapshot_path(level: str) -> Path:
    """Get the path for a snapshot file at a given level."""
    return SNAPSHOT_DIR / f"{level}.json.gz"


async def generate_snapshots() -> dict[str, int]:
    """Generate snapshot files for all access levels.

    Returns dict of {level: object_count}.
    Reads {level}::text column directly — no Python deserialization.
    """
    from .db import _pool

    if not _pool:
        raise RuntimeError("Database not initialized")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stats: dict[str, int] = {}

    for level in ("public", "member", "full"):
        start = time.time()
        count = 0
        timestamp: str | None = None

        # Write to temp file then atomic rename
        fd, tmp_path = tempfile.mkstemp(dir=SNAPSHOT_DIR, suffix=".tmp")
        os.close(fd)
        try:
            with gzip.open(tmp_path, "wt", encoding="utf-8", compresslevel=6) as gz:
                gz.write("[")
                first_type = True

                for obj_type in OBJECT_TYPES:
                    if not first_type:
                        gz.write(",")
                    first_type = False

                    gz.write(f'{{"type":"{obj_type}","data":[')

                    # Stream objects of this type, reading pre-computed column
                    col = f'"{level}"'
                    async with _pool.connection() as conn:
                        result = await conn.execute(
                            f"SELECT {col}::text, modified_at FROM objects "  # ty: ignore[invalid-argument-type]
                            f"WHERE type = %s AND deleted_at IS NULL AND {col} IS NOT NULL "
                            f"ORDER BY modified_at ASC",
                            (obj_type,),
                        )
                        first_obj = True
                        async for row in result:
                            json_str, mod_at = row[0], row[1]
                            if not first_obj:
                                gz.write(",")
                            first_obj = False
                            gz.write(json_str)
                            count += 1

                            mod_str = mod_at.isoformat()
                            if timestamp is None or mod_str > timestamp:
                                timestamp = mod_str

                    gz.write("]}")

                # Meta section with timestamp
                if timestamp is None:
                    timestamp = datetime.now(UTC).isoformat()
                gz.write(f',{{"type":"meta","timestamp":"{timestamp}"}}')
                gz.write("]")

            # Atomic rename
            dest = _snapshot_path(level)
            os.rename(tmp_path, dest)
            elapsed = time.time() - start
            stats[level] = count
            logger.info(
                f"Snapshot {level}: {count} objects, "
                f"{dest.stat().st_size / 1024:.1f} KB, {elapsed:.2f}s"
            )
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    return stats


def get_snapshot_path(level: str) -> Path | None:
    """Get the path for a snapshot file, or None if it doesn't exist."""
    path = _snapshot_path(level)
    return path if path.exists() else None
