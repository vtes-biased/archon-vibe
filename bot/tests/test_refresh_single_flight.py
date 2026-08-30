"""Reproduces the backend's refresh-token rotation + reuse-detection in a fake
backend, so concurrent refreshers can't double-spend the grant and self-revoke
the organizer's whole token chain."""

from __future__ import annotations

import asyncio
import os
import unittest

# config.py reads these at import time.
os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot.archon_api import ArchonAPI  # noqa: E402

DISCORD_ID = "discord-1"
TOURNAMENT_UID = "tournament-1"
ARCHON_UID = "archon-1"


class FakeStore:
    """In-memory stand-in for TokenStore, keyed by grant like the real one."""

    def __init__(self, tokens: dict) -> None:
        self._data: dict[tuple[str, str], dict] = {
            (DISCORD_ID, TOURNAMENT_UID): dict(tokens)
        }

    async def get_tokens(self, discord_id: str, tournament_uid: str) -> dict | None:
        await asyncio.sleep(0)  # behave like a real awaitable I/O call
        t = self._data.get((discord_id, tournament_uid))
        return dict(t) if t else None

    async def store_tokens(
        self,
        discord_id: str,
        tournament_uid: str,
        archon_uid: str,
        access_token: str,
        refresh_token: str,
    ) -> None:
        self._data[(discord_id, tournament_uid)] = {
            "archon_uid": archon_uid,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    async def remove_tokens(self, discord_id: str, tournament_uid: str) -> None:
        self._data.pop((discord_id, tournament_uid), None)


class _Resp:
    def __init__(self, status: int, payload: dict) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> _Resp:
        await asyncio.sleep(0)  # force a real yield so coroutines interleave
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def json(self) -> dict:
        return self._payload


class FakeBackend:
    """Models /oauth/token refresh: rotation + reuse-detection chain revocation."""

    def __init__(
        self, initial_refresh: str, *, fail_all: bool = False, fail_status: int = 400
    ) -> None:
        self._current_refresh = initial_refresh
        self._revoked: set[str] = set()
        self._fail_all = fail_all
        self._fail_status = fail_status
        self.chain_revoked = False
        self.post_count = 0
        self._seq = 0

    def post(self, path: str, json: dict) -> _Resp:
        self.post_count += 1
        token = json["refresh_token"]

        if self._fail_all:
            return _Resp(self._fail_status, {"detail": "Refresh token expired"})

        # Replay of a rotated-out token → backend nukes the entire chain.
        if token in self._revoked:
            self.chain_revoked = True
            self._current_refresh = "<<dead>>"
            return _Resp(400, {"detail": "Refresh token has been revoked"})

        if self.chain_revoked or token != self._current_refresh:
            return _Resp(400, {"detail": "Invalid refresh token"})

        # Rotate: revoke the presented token, issue a fresh pair.
        self._revoked.add(token)
        self._seq += 1
        new_access, new_refresh = f"access-{self._seq}", f"refresh-{self._seq}"
        self._current_refresh = new_refresh
        return _Resp(200, {"access_token": new_access, "refresh_token": new_refresh})


def _make_api(backend: FakeBackend, store: FakeStore) -> ArchonAPI:
    api = ArchonAPI(store)  # type: ignore[arg-type]
    api._session = backend  # type: ignore[assignment]
    return api


class SingleFlightRefreshTest(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_refresh_is_single_flight(self) -> None:
        """Two refreshers sharing the same stale token → one POST, chain alive."""
        store = FakeStore(
            {
                "archon_uid": ARCHON_UID,
                "access_token": "access-0",
                "refresh_token": "refresh-0",
            }
        )
        backend = FakeBackend("refresh-0")
        api = _make_api(backend, store)

        # Both callers captured the same (now-expiring) access token.
        results = await asyncio.gather(
            api._refresh_tokens(
                DISCORD_ID, TOURNAMENT_UID, stale_access_token="access-0"
            ),
            api._refresh_tokens(
                DISCORD_ID, TOURNAMENT_UID, stale_access_token="access-0"
            ),
        )

        self.assertEqual(backend.post_count, 1, "second refresher must not re-POST")
        self.assertFalse(backend.chain_revoked, "chain must survive")
        for r in results:
            self.assertIsNotNone(r)
            self.assertEqual(r["access_token"], "access-1")
            self.assertEqual(r["refresh_token"], "refresh-1")
        self.assertEqual(
            (await store.get_tokens(DISCORD_ID, TOURNAMENT_UID))["refresh_token"],
            "refresh-1",
        )

    async def test_high_concurrency_single_flight(self) -> None:
        """N simultaneous refreshers still rotate the grant exactly once."""
        store = FakeStore(
            {
                "archon_uid": ARCHON_UID,
                "access_token": "access-0",
                "refresh_token": "refresh-0",
            }
        )
        backend = FakeBackend("refresh-0")
        api = _make_api(backend, store)

        results = await asyncio.gather(
            *(
                api._refresh_tokens(
                    DISCORD_ID, TOURNAMENT_UID, stale_access_token="access-0"
                )
                for _ in range(8)
            )
        )

        self.assertEqual(backend.post_count, 1)
        self.assertFalse(backend.chain_revoked)
        self.assertTrue(all(r and r["access_token"] == "access-1" for r in results))

    async def test_fake_backend_models_the_bug(self) -> None:
        """Guard proving the fake faithfully reproduces the vulnerability, so
        the tests above are meaningful regression coverage."""
        store = FakeStore(
            {
                "archon_uid": ARCHON_UID,
                "access_token": "access-0",
                "refresh_token": "refresh-0",
            }
        )
        backend = FakeBackend("refresh-0")
        api = _make_api(backend, store)
        stale = await store.get_tokens(DISCORD_ID, TOURNAMENT_UID)

        # Bypass the lock: two raw refreshes both replaying refresh-0.
        await api._do_refresh(DISCORD_ID, TOURNAMENT_UID, dict(stale))
        await api._do_refresh(DISCORD_ID, TOURNAMENT_UID, dict(stale))

        self.assertEqual(backend.post_count, 2)
        self.assertTrue(backend.chain_revoked, "replay must trip reuse-detection")

    async def test_genuine_expiry_clears_tokens(self) -> None:
        """A real refresh failure removes tokens and returns None for all waiters."""
        store = FakeStore(
            {
                "archon_uid": ARCHON_UID,
                "access_token": "access-0",
                "refresh_token": "refresh-0",
            }
        )
        backend = FakeBackend("refresh-0", fail_all=True)
        api = _make_api(backend, store)

        results = await asyncio.gather(
            api._refresh_tokens(
                DISCORD_ID, TOURNAMENT_UID, stale_access_token="access-0"
            ),
            api._refresh_tokens(
                DISCORD_ID, TOURNAMENT_UID, stale_access_token="access-0"
            ),
        )

        self.assertTrue(all(r is None for r in results))
        self.assertIsNone(await store.get_tokens(DISCORD_ID, TOURNAMENT_UID))
        # First POST fails+clears under the lock; the second waiter then finds no
        # tokens and returns without a second POST.
        self.assertEqual(backend.post_count, 1)

    async def test_transient_failure_keeps_tokens(self) -> None:
        """A 5xx must NOT destroy the stored pair — invalid-grant is signalled
        exclusively via 400."""
        store = FakeStore(
            {
                "archon_uid": ARCHON_UID,
                "access_token": "access-0",
                "refresh_token": "refresh-0",
            }
        )
        backend = FakeBackend("refresh-0", fail_all=True, fail_status=503)
        api = _make_api(backend, store)

        result = await api._refresh_tokens(
            DISCORD_ID, TOURNAMENT_UID, stale_access_token="access-0"
        )

        self.assertIsNone(result)
        stored = await store.get_tokens(DISCORD_ID, TOURNAMENT_UID)
        self.assertIsNotNone(stored, "5xx must keep the stored pair")
        self.assertEqual(stored["refresh_token"], "refresh-0")

    async def test_locks_are_per_grant(self) -> None:
        """Every grant gets its own lock: a second organizer, and the same
        organizer's second tournament."""
        store = FakeStore(
            {
                "archon_uid": ARCHON_UID,
                "access_token": "access-0",
                "refresh_token": "refresh-0",
            }
        )
        store._data[("discord-2", TOURNAMENT_UID)] = {
            "archon_uid": "archon-2",
            "access_token": "b-access-0",
            "refresh_token": "b-refresh-0",
        }
        backend = FakeBackend("refresh-0")
        # Second organizer needs its own backend grant universe; reuse store but
        # a single fake backend only tracks one chain, so assert via the lock map.
        api = _make_api(backend, store)

        await api._refresh_tokens(
            DISCORD_ID, TOURNAMENT_UID, stale_access_token="access-0"
        )
        self.assertIn((DISCORD_ID, TOURNAMENT_UID), api._refresh_locks)
        own = api._refresh_lock_for(DISCORD_ID, TOURNAMENT_UID)
        self.assertIsInstance(own, asyncio.Lock)
        self.assertIsNot(own, api._refresh_lock_for("discord-2", TOURNAMENT_UID))
        self.assertIsNot(own, api._refresh_lock_for(DISCORD_ID, "tournament-2"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
