"""Token-optional SSE endpoints must reject a supplied-but-invalid credential
(401) instead of silently serving the public projection — whether it arrives as
a `token=` query param (browser EventSource can't set headers) or an
`Authorization: Bearer` header (the bot). Only a wholly absent credential is
anonymous → public.
"""

import pytest


@pytest.mark.asyncio
async def test_stream_rejects_invalid_query_token(test_client):
    # The raise precedes the StreamingResponse, so this returns promptly.
    resp = await test_client.get("/stream?token=not-a-jwt")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_stream_rejects_invalid_bearer_header(test_client):
    resp = await test_client.get(
        "/stream", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_snapshot_rejects_invalid_token(test_client):
    resp = await test_client.get("/snapshot?token=not-a-jwt")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_snapshot_allows_anonymous(test_client):
    """No credential stays a first-class public viewer — never 401."""
    resp = await test_client.get("/snapshot")
    assert resp.status_code != 401
