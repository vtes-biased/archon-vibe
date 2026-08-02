"""The data export's zip envelope must be readable by an ordinary unzip.

`_iter_snapshot_zip` hand-streams the archive into a non-seekable sink (data
descriptors, central directory written on close), so a framing slip yields a file
that downloads fine and refuses to open — the one failure mode worth pinning.
"""

import gzip
import io
import zipfile
from pathlib import Path

from src.main import _iter_snapshot_zip


def test_export_zip_roundtrips_the_snapshot(tmp_path: Path) -> None:
    jsonl = b"".join(b'{"type":"user","data":{"n":%d}}\n' % i for i in range(50_000))
    snapshot = tmp_path / "full.jsonl.gz"
    with gzip.open(snapshot, "wb") as f:
        f.write(jsonl)

    # Chunked below the payload size so the drain-and-yield path is exercised.
    body = b"".join(
        _iter_snapshot_zip(
            snapshot, "export.jsonl", snapshot.stat().st_mtime, chunk_size=8192
        )
    )

    archive = zipfile.ZipFile(io.BytesIO(body))
    assert archive.testzip() is None
    assert archive.namelist() == ["export.jsonl"]
    assert archive.read("export.jsonl") == jsonl
