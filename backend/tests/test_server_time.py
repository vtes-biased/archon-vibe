"""/api/time wire contract for the frontend's mini-NTP offset sync: the round
timer depends on `server_time` being the CURRENT server wall clock in
MICROSECONDS and never cached — a stale or wrong-unit value silently breaks the
offset (untested by svelte-check, unit tests, or the e2e timer flow).
"""

import time

import pytest


@pytest.mark.asyncio
async def test_server_time_is_current_microseconds_and_uncacheable(test_client):
    before = time.time_ns() // 1000
    resp = await test_client.get("/api/time")
    after = time.time_ns() // 1000

    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"

    server_time = resp.json()["server_time"]
    # Read strictly between the two host samples ⇒ pins both recency and the
    # microsecond unit in one bracket.
    assert before <= server_time <= after
