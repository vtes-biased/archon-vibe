import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from . import http_client

logger = logging.getLogger(__name__)

# VEKN API error messages translation (from Joomla language files)
VEKN_MESSAGES = {
    "PLG_API_VEKN_BAD_REQUEST_MESSAGE": "Bad request",
    "PLG_API_VEKN_REQUIRED_DATA_EMPTY_MESSAGE": "Required data is empty",
    "PLG_API_VEKN_REQUIRED_FILTER_MESSAGE": "Filter cannot be empty",
    "PLG_API_VEKN_ACCOUNT_CREATED_SUCCESSFULLY_MESSAGE": "Congratulations! Your account has been created successfully",
    "PLG_API_VEKN_PROFILE_CREATED_SUCCESSFULLY_MESSAGE": "profile created successfully",
    "PLG_API_VEKN_UNABLE_CREATE_PROFILE_MESSAGE": "Unable to create profile",
    "PLG_API_VEKN_EASYSOCIAL_NOT_INSTALL_MESSAGE": "Easysocial is not installed properly",
    "PLG_API_VEKN_GET_METHOD_NOT_ALLOWED_MESSAGE": "Get method not allowed, Use post method",
    "PLG_API_VEKN_USER_NOT_FOUND_MESSAGE": "User not found",
    "PLG_API_VEKN_IN_DELETE_FUNCTION_MESSAGE": "in delete function",
    "PLG_API_VEKN_LOGIN_INVALID_USER_MESSAGE": "Invalid user",
    "PLG_API_VEKN_LOGIN_INVALID_PASSWORD_MESSAGE": "Invalid password",
    "PLG_API_VEKN_REGISTRY_NOT_AUTHORIZED_MESSAGE": "Not authorized",
    "PLG_API_VEKN_REGISTRY_INVALID_VEKNID_MESSAGE": "Invalid VEKN Id",
    "PLG_API_VEKN_REGISTRY_VEKNID_ALREADY_ASSIGNED_MESSAGE": "VEKN Id already assigned",
    "PLG_API_VEKN_REGISTRY_PLAYER_ALREADY_EXISTS_MESSAGE": "A player with the same name or email already exists",
    "PLG_API_VEKN_UNSUPPORTED_METHOD": "Unsupported method,please use post method",
    "PLG_API_VEKN_UNSUPPORTED_METHOD_POST": "Unsupported method,please use get method",
}


class VEKNAPIError(Exception):
    """VEKN API error (default: a per-item/data error — bad VEKN id, parse error)."""


class VEKNAPIConnectionError(VEKNAPIError):
    """VEKN is unreachable or won't authenticate — distinguished from plain
    VEKNAPIError so batch_push can fail-fast and abort the whole batch.
    """


class VEKNAPIClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("VEKN_API_BASE_URL", "https://www.vekn.net/api")
        self.username = os.getenv("VEKN_API_USERNAME")
        self.password = os.getenv("VEKN_API_PASSWORD")
        self._auth_token: str | None = None

    async def _authenticate(self) -> None:
        # All failures here are batch-fatal (bad/missing creds, transport down)
        # — raise the connection-class error so batch_push aborts.
        if (
            not self.username
            or not self.password
            or not self.username.strip()
            or not self.password.strip()
        ):
            raise VEKNAPIConnectionError(
                "VEKN_API_USERNAME and VEKN_API_PASSWORD must be set in environment"
            )

        try:
            session = http_client.session()
            async with session.post(
                f"{self.base_url}/index.php",
                params={"app": "vekn", "resource": "login", "format": "raw"},
                data={"username": self.username, "password": self.password},
            ) as response:
                response.raise_for_status()
                data = await response.json()

                inner_data = data.get("data", {})
                self._check_vekn_error(
                    inner_data, "Authentication failed", exc=VEKNAPIConnectionError
                )
                self._auth_token = inner_data.get("auth")
                if not self._auth_token:
                    raise VEKNAPIConnectionError(f"No auth token in response: {data}")

                logger.info("Successfully authenticated with VEKN API")

        except (aiohttp.ClientError, TimeoutError) as e:
            raise VEKNAPIConnectionError(
                f"HTTP error during authentication: {e}"
            ) from e

    def _check_vekn_error(
        self,
        data: dict[str, Any],
        context: str = "",
        exc: type[VEKNAPIError] = VEKNAPIError,
    ) -> None:
        """Raises exc (VEKNAPIConnectionError for batch-fatal contexts like auth)
        on a non-200 VEKN response code."""
        code = data.get("code", 200)
        # Normalize code to int (API returns string "200" or int 200)
        if isinstance(code, str):
            code = int(code) if code.isdigit() else 0
        if code not in (200,):
            message = data.get("message", "Unknown error")
            message = VEKN_MESSAGES.get(message, message)
            prefix = f"{context}: " if context else ""
            raise exc(f"{prefix}{message} (code: {code})")

    async def _ensure_authenticated(self) -> None:
        if not self._auth_token:
            await self._authenticate()

    async def search_players(self, filter_str: str) -> list[dict[str, Any]]:
        await self._ensure_authenticated()

        try:
            params = {
                "app": "vekn",
                "resource": "registry",
                "format": "raw",
                "filter": filter_str,
            }
            if self._auth_token:
                params["key"] = self._auth_token

            session = http_client.session()
            async with session.get(
                f"{self.base_url}/index.php",
                params=params,
            ) as response:
                response.raise_for_status()

                content = await response.read()
                if not content or not content.strip():
                    logger.warning(f"Empty response for filter: {filter_str}")
                    return []

                try:
                    data = await response.json()
                except Exception as e:
                    text = await response.text()
                    logger.error(
                        f"Invalid JSON response for filter {filter_str}: {text[:200]}"
                    )
                    raise VEKNAPIError(f"Invalid JSON from API: {e}") from e

                inner_data = data.get("data", {})
                # Some endpoints omit 'code' entirely on success.
                if "code" in inner_data:
                    self._check_vekn_error(
                        inner_data, f"Search failed for '{filter_str}'"
                    )

                if "players" not in inner_data:
                    logger.warning(f"No players found for filter: {filter_str}")
                    return []

                return inner_data["players"]

        # asyncio.TimeoutError isn't a ClientError — must be caught here too, or
        # fetch_all_members dies instead of skipping this prefix and continuing.
        except (aiohttp.ClientError, TimeoutError) as e:
            raise VEKNAPIError(f"HTTP error searching players: {e}") from e

    async def create_member(
        self,
        *,
        veknid: str,
        firstname: str,
        lastname: str,
        email: str,
        country: str,
        state: str = "",
        city: str = "",
    ) -> None:
        await self._ensure_authenticated()
        session = http_client.session()

        headers: dict[str, str] = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        form_data = {
            "veknid": veknid,
            "firstname": firstname,
            "lastname": lastname,
            "email": email,
            "country": country,
            "state": state,
            "city": city,
        }

        try:
            async with session.post(
                f"{self.base_url}/index.php",
                params={"app": "vekn", "resource": "registry", "format": "raw"},
                data=form_data,
                headers=headers,
            ) as response:
                response.raise_for_status()
                data = await response.json()
                inner = data.get("data", {})
                duplicate = inner.get("veknid")
                self._check_vekn_error(
                    inner,
                    f"Create member failed (duplicate of {duplicate} on vekn.net)"
                    if duplicate
                    else "Create member failed",
                )
                logger.info(f"Created VEKN member {veknid}: {firstname} {lastname}")
        except (aiohttp.ClientError, TimeoutError) as e:
            raise VEKNAPIConnectionError(f"HTTP error creating member: {e}") from e

    async def _fetch_by_prefix(
        self, prefix: str, seen_ids: set[str], depth: int = 0
    ) -> list[dict[str, Any]]:
        """Recursively fetch players by prefix, subdividing at the API's 100-result cap."""
        players = await self.search_players(prefix)

        unique_players = []
        for player in players:
            vekn_id = str(player.get("veknid", ""))
            if vekn_id and vekn_id not in seen_ids:
                seen_ids.add(vekn_id)
                unique_players.append(player)

        if len(players) >= 100:
            for digit in range(10):
                sub_prefix = f"{prefix}{digit}"
                sub_players = await self._fetch_by_prefix(
                    sub_prefix, seen_ids, depth + 1
                )
                unique_players.extend(sub_players)

        return unique_players

    async def fetch_all_members(self) -> AsyncIterator[dict[str, Any]]:
        """Fetch all VEKN members: 7-digit IDs (0000000-9999999), 100 results max
        per query — search by prefix, subdividing recursively for full coverage.
        """
        await self._ensure_authenticated()

        seen_ids: set[str] = set()

        # API pads 2-digit prefixes into ranges: "00"->0000000-0099999.
        for prefix in range(100):
            prefix_str = f"{prefix:02d}"
            try:
                players = await self._fetch_by_prefix(prefix_str, seen_ids)
            except VEKNAPIError as e:
                logger.error(f"Error fetching players for prefix {prefix_str}: {e}")
                continue
            for player in players:
                yield player

        logger.info(f"Total unique players fetched: {len(seen_ids)}")
