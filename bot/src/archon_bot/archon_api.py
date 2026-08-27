from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

import aiohttp

from . import config
from .token_store import TokenStore

logger = logging.getLogger(__name__)


@dataclass
class ApiResult:
    data: dict | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.data is not None

    @staticmethod
    def success(data: dict) -> ApiResult:
        return ApiResult(data=data)

    @staticmethod
    def fail(error: str) -> ApiResult:
        return ApiResult(error=error)


class ArchonAPI:
    def __init__(self, store: TokenStore):
        self._store = store
        self._session: aiohttp.ClientSession | None = None
        # One refresh lock per grant — (discord_id, tournament_uid): replaying a
        # rotated-out refresh token trips the backend's reuse-detection and
        # revokes the whole chain. (#11)
        self._refresh_locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def init(self) -> None:
        # total=30 (aiohttp defaults to 300s): a hung backend must surface as an
        # error, not wedge callers. The SSE stream uses its own unbounded session.
        self._session = aiohttp.ClientSession(
            base_url=config.ARCHON_URL, timeout=aiohttp.ClientTimeout(total=30)
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    def _refresh_lock_for(self, discord_id: str, tournament_uid: str) -> asyncio.Lock:
        """Get-or-create the per-grant refresh lock (atomic under asyncio)."""
        key = (discord_id, tournament_uid)
        lock = self._refresh_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._refresh_locks[key] = lock
        return lock

    async def refresh_tokens(
        self,
        discord_id: str,
        tournament_uid: str,
        *,
        stale_access_token: str | None = None,
    ) -> dict | None:
        return await self._refresh_tokens(
            discord_id, tournament_uid, stale_access_token=stale_access_token
        )

    async def _refresh_tokens(
        self,
        discord_id: str,
        tournament_uid: str,
        *,
        stale_access_token: str | None = None,
    ) -> dict | None:
        """Single-flight per grant; if the stored access token no longer matches
        ``stale_access_token``, another caller already refreshed. (#11)"""
        async with self._refresh_lock_for(discord_id, tournament_uid):
            tokens = await self._store.get_tokens(discord_id, tournament_uid)
            if not tokens:
                return None

            # A concurrent refresher beat us to it: the stored access token is no
            # longer the one we tried to use, so a fresh pair already exists.
            if (
                stale_access_token is not None
                and tokens["access_token"] != stale_access_token
            ):
                return tokens

            return await self._do_refresh(discord_id, tournament_uid, tokens)

    async def _do_refresh(
        self, discord_id: str, tournament_uid: str, tokens: dict
    ) -> dict | None:
        """POST the refresh grant and persist the rotated pair. Lock held."""
        assert self._session
        try:
            async with self._session.post(
                "/oauth/token",
                json={
                    "grant_type": "refresh_token",
                    "refresh_token": tokens["refresh_token"],
                    "client_id": config.OAUTH_CLIENT_ID,
                    "client_secret": config.OAUTH_CLIENT_SECRET,
                },
            ) as resp:
                if resp.status in (400, 401):
                    # Invalid-grant is signaled via 400 only (401 = bad client
                    # creds); only then is the stored pair genuinely dead.
                    logger.warning(
                        "Refresh token rejected (%s) for discord_id=%s tournament=%s",
                        resp.status,
                        discord_id,
                        tournament_uid,
                    )
                    await self._store.remove_tokens(discord_id, tournament_uid)
                    return None
                if resp.status != 200:
                    # 5xx / proxy blip (e.g. the backend's daily restart): the
                    # stored pair is still valid — keep it, let callers retry.
                    logger.warning(
                        "Transient token refresh failure (%s) for discord_id=%s; "
                        "keeping tokens",
                        resp.status,
                        discord_id,
                    )
                    return None
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as e:
            logger.warning(
                "Token refresh network failure for discord_id=%s: %s; keeping tokens",
                discord_id,
                e,
            )
            return None

        await self._store.store_tokens(
            discord_id=discord_id,
            tournament_uid=tournament_uid,
            archon_uid=tokens["archon_uid"],
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
        )
        return {
            "archon_uid": tokens["archon_uid"],
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
        }

    async def _get_stored_token(
        self, discord_id: str, tournament_uid: str
    ) -> str | None:
        """Get stored access token (may be expired; caller handles 401 refresh)."""
        tokens = await self._store.get_tokens(discord_id, tournament_uid)
        if not tokens:
            return None
        return tokens["access_token"]

    @staticmethod
    def _extract_error(status: int, text: str) -> str:
        try:
            body = json.loads(text)
            detail = body.get("detail", "")
            if isinstance(detail, str) and detail:
                return detail
            if isinstance(detail, list) and detail:
                # FastAPI validation errors
                return "; ".join(d.get("msg", str(d)) for d in detail)
        except (json.JSONDecodeError, AttributeError):
            pass
        if status == 403:
            return "Permission denied."
        if status == 404:
            return "Not found."
        if status == 409:
            return "Conflict — this may already exist."
        return f"Server error ({status})."

    async def _request(
        self,
        method: str,
        path: str,
        discord_id: str,
        tournament_uid: str,
        json_body: dict | None = None,
    ) -> ApiResult:
        token = await self._get_stored_token(discord_id, tournament_uid)
        if not token:
            return ApiResult.fail(
                "Your Archon session has expired. Run the command again to re-authenticate."
            )

        assert self._session
        headers = {"Authorization": f"Bearer {token}"}
        async with self._session.request(
            method, path, json=json_body, headers=headers
        ) as resp:
            if resp.status == 401:
                # Try refresh, passing the token that 401'd so a concurrent
                # refresh is detected instead of double-spending the grant.
                refreshed = await self._refresh_tokens(
                    discord_id, tournament_uid, stale_access_token=token
                )
                if not refreshed:
                    return ApiResult.fail(
                        "Your Archon session has expired. Run the command again to re-authenticate."
                    )
                headers["Authorization"] = f"Bearer {refreshed['access_token']}"
                async with self._session.request(
                    method, path, json=json_body, headers=headers
                ) as resp2:
                    if resp2.status >= 400:
                        text = await resp2.text()
                        logger.error(
                            "API error %s %s: %s %s", method, path, resp2.status, text
                        )
                        return ApiResult.fail(self._extract_error(resp2.status, text))
                    return ApiResult.success(await resp2.json())
            if resp.status >= 400:
                text = await resp.text()
                logger.error("API error %s %s: %s %s", method, path, resp.status, text)
                return ApiResult.fail(self._extract_error(resp.status, text))
            return ApiResult.success(await resp.json())

    async def get_userinfo(self, discord_id: str, tournament_uid: str) -> ApiResult:
        return await self._request("GET", "/oauth/userinfo", discord_id, tournament_uid)

    async def get_sanction_reference(self) -> dict:
        """Public, no-auth, engine-owned. Raises on failure; callers surface the
        error and retry on the next command."""
        assert self._session
        async with self._session.get("/sanctions/reference") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def tournament_action(
        self, discord_id: str, tournament_uid: str, action: str, **kwargs: object
    ) -> ApiResult:
        payload = {"type": action, **kwargs}
        return await self._request(
            "POST",
            f"/api/tournaments/{tournament_uid}/action",
            discord_id,
            tournament_uid,
            json_body=payload,
        )

    async def create_sanction(
        self,
        discord_id: str,
        user_uid: str,
        tournament_uid: str,
        level: str,
        category: str,
        description: str,
        subcategory: str | None = None,
        round_number: int | None = None,
    ) -> ApiResult:
        payload: dict = {
            "user_uid": user_uid,
            "tournament_uid": tournament_uid,
            "level": level,
            "category": category,
            "description": description,
        }
        if subcategory:
            payload["subcategory"] = subcategory
        if round_number is not None:
            payload["round_number"] = round_number
        return await self._request(
            "POST", "/sanctions/", discord_id, tournament_uid, json_body=payload
        )

    async def exchange_code(self, code: str, code_verifier: str) -> dict | None:
        assert self._session
        async with self._session.post(
            "/oauth/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.OAUTH_REDIRECT_URI,
                "code_verifier": code_verifier,
                "client_id": config.OAUTH_CLIENT_ID,
                "client_secret": config.OAUTH_CLIENT_SECRET,
            },
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error("Code exchange failed: %s %s", resp.status, text)
                return None
            return await resp.json()
