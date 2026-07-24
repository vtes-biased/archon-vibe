"""/api/time wire contract for the frontend's mini-NTP offset sync.

The round timer subtracts a server-stamped `started_at` from the client clock, so
the offset correction is only as good as this endpoint. The frontend reads
`server_time / 1000` to get milliseconds, i.e. it depends on `server_time` being
the CURRENT server wall clock in MICROSECONDS, and on the response never being
cached (a stale timestamp yields a wrong offset — the phantom-elapsed bug this
feature fixes, back but silent). Both failure modes are invisible to svelte-check,
have no frontend unit-test layer, and aren't exercised by the e2e timer flow, so
one interface test pins the wire contract here. The µs bracket also discriminates
the unit: a seconds/millis/nanos slip lands orders of magnitude outside it.
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
