"""Archon API client for the Discord bot."""

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
    """Result of an API call — either data or an error message."""

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
    """HTTP client for Archon backend. Uses OAuth tokens for all requests."""

    def __init__(self, store: TokenStore):
        self._store = store
        self._session: aiohttp.ClientSession | None = None
        # Single-flight refresh: one lock per discord_id so concurrent refreshers
        # (SSE loop + a slash command both hitting 401 at once) serialize instead
        # of both replaying the same stored refresh token. Replaying a rotated-out
        # token trips the backend's reuse-detection, which revokes the whole token
        # chain and logs the organizer out. The map is unbounded but keyed by the
        # small, bounded set of linked organizers — negligible. (#11)
        self._refresh_locks: dict[str, asyncio.Lock] = {}

    async def init(self) -> None:
        self._session = aiohttp.ClientSession(base_url=config.ARCHON_URL)

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    # --- Token refresh ---

    def _refresh_lock_for(self, discord_id: str) -> asyncio.Lock:
        """Get-or-create the per-organizer refresh lock (atomic under asyncio)."""
        lock = self._refresh_locks.get(discord_id)
        if lock is None:
            lock = asyncio.Lock()
            self._refresh_locks[discord_id] = lock
        return lock

    async def refresh_tokens(
        self, discord_id: str, *, stale_access_token: str | None = None
    ) -> dict | None:
        """Public wrapper to refresh tokens (for SSE listener reconnect)."""
        return await self._refresh_tokens(
            discord_id, stale_access_token=stale_access_token
        )

    async def _refresh_tokens(
        self, discord_id: str, *, stale_access_token: str | None = None
    ) -> dict | None:
        """Refresh expired access token using refresh token.

        Single-flight per ``discord_id``. ``stale_access_token`` is the access
        token whose request 401'd; if another caller already refreshed while we
        waited for the lock, the stored access token will differ from it and we
        return the fresh tokens instead of replaying our now-rotated-out refresh
        token (which would trip backend reuse-detection). (#11)
        """
        async with self._refresh_lock_for(discord_id):
            tokens = await self._store.get_tokens(discord_id)
            if not tokens:
                return None

            # A concurrent refresher beat us to it: the stored access token is no
            # longer the one we tried to use, so a fresh pair already exists.
            if (
                stale_access_token is not None
                and tokens["access_token"] != stale_access_token
            ):
                return tokens

            return await self._do_refresh(discord_id, tokens)

    async def _do_refresh(self, discord_id: str, tokens: dict) -> dict | None:
        """POST the refresh grant and persist the rotated pair. Lock held."""
        assert self._session
        async with self._session.post(
            "/oauth/token",
            json={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": config.OAUTH_CLIENT_ID,
                "client_secret": config.OAUTH_CLIENT_SECRET,
            },
        ) as resp:
            if resp.status != 200:
                logger.warning("Token refresh failed for discord_id=%s", discord_id)
                await self._store.remove_tokens(discord_id)
                return None
            data = await resp.json()

        await self._store.store_tokens(
            discord_id=discord_id,
            archon_uid=tokens["archon_uid"],
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
        )
        return {
            "archon_uid": tokens["archon_uid"],
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
        }

    async def _get_stored_token(self, discord_id: str) -> str | None:
        """Get stored access token (may be expired; caller handles 401 refresh)."""
        tokens = await self._store.get_tokens(discord_id)
        if not tokens:
            return None
        return tokens["access_token"]

    @staticmethod
    def _extract_error(status: int, text: str) -> str:
        """Extract a human-readable error from an API response."""
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
        json_body: dict | None = None,
    ) -> ApiResult:
        """Make an authenticated request, auto-refreshing on 401."""
        token = await self._get_stored_token(discord_id)
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
                    discord_id, stale_access_token=token
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

    # --- Public API methods ---

    async def get_userinfo(self, discord_id: str) -> ApiResult:
        """Get user profile via /oauth/userinfo."""
        return await self._request("GET", "/oauth/userinfo", discord_id)

    async def tournament_action(
        self, discord_id: str, tournament_uid: str, action: str, **kwargs: object
    ) -> ApiResult:
        """Send a tournament action via POST /{uid}/action."""
        payload = {"type": action, **kwargs}
        return await self._request(
            "POST",
            f"/api/tournaments/{tournament_uid}/action",
            discord_id,
            json_body=payload,
        )

    async def claim_vekn_id(self, discord_id: str, vekn_id: str) -> ApiResult:
        """Claim a VEKN ID via POST /vekn/claim."""
        return await self._request(
            "POST", "/api/vekn/claim", discord_id, json_body={"vekn_id": vekn_id}
        )

    async def sponsor_player(
        self, organizer_discord_id: str, player_uid: str, country: str, city: str = ""
    ) -> ApiResult:
        """Sponsor a new VEKN member via POST /vekn/sponsor."""
        payload: dict = {"user_uid": player_uid, "country": country}
        if city:
            payload["city"] = city
        return await self._request(
            "POST", "/api/vekn/sponsor", organizer_discord_id, json_body=payload
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
        """Create a sanction via POST /sanctions/."""
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
            "POST", "/api/sanctions/", discord_id, json_body=payload
        )

    async def exchange_code(self, code: str, code_verifier: str) -> dict | None:
        """Exchange authorization code for tokens."""
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
