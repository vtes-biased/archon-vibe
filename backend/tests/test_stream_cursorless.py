"""Snapshot-on-first-connect is server-enforced: a
cursorless /stream connect is answered with the resync directive instead of a
whole-corpus stream off a pooled connection — but only while a snapshot file
exists, because /snapshot 503s without one and the redirect would loop the
client. Both scenarios pass a valid `av`: an absent one already resyncs on the
fingerprint branch and would mask the guard under test.
"""

import asyncio

import pytest
from src import db, snapshots
from src.broadcast import _sse_connections


@pytest.mark.asyncio
async def test_cursorless_connect_gets_resync_when_snapshot_exists(
    test_client, tmp_path, monkeypatch
):
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path)
    (tmp_path / "public.jsonl.gz").write_bytes(b"")

    av = await db.compute_access_version(None)
    resp = await test_client.get(f"/stream?av={av}")
    assert resp.status_code == 200
    assert '"type":"resync"' in resp.text
    assert "sync_complete" not in resp.text


@pytest.mark.asyncio
async def test_cursorless_connect_streams_corpus_when_snapshot_absent(
    test_client, tmp_path, monkeypatch
):
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path)

    av = await db.compute_access_version(None)
    # ASGITransport buffers the whole body and the live phase never ends, so
    # end the stream through the queue-overflow flag the generator polls.
    task = asyncio.create_task(test_client.get(f"/stream?av={av}"))
    async with asyncio.timeout(30):
        while not task.done():
            for conn in list(_sse_connections):
                conn.closed = True
            await asyncio.sleep(0.1)
    resp = await task
    assert resp.status_code == 200
    assert '"type":"resync"' not in resp.text
    assert "sync_complete" in resp.text
