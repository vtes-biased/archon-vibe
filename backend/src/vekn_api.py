"""VEKN API client for fetching member and event data."""

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

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
    "PLG_API_VEKN_ARCHON_INVALID_PARAMETER_MESSAGE": "Invalid parameter",
    "PLG_API_VEKN_ARCHON_EVENT_NOT_FOUND_MESSAGE": "Event not found",
    "PLG_API_VEKN_ARCHON_WRONG_USER_MESSAGE": "The connected user does not match the event creator.",
    "PLG_API_VEKN_ARCHON_ARCHON_ALREADY_SUBMITTED_MESSAGE": "An archon has already been submitted for this event.",
    "PLG_API_VEKN_ARCHON_MISSING_VEKN_NUMBER_MESSAGE": "Some players do not have a VEKN number, or there are some duplicates.",
    "PLG_API_VEKN_ARCHON_ARCHON_PARSE_ERROR_MESSAGE": "An error occurred while parsing the archon data",
    "PLG_API_VEKN_ARCHON_ROUNDS_MISMATCH_MESSAGE": "The provided number of rounds do not match the expected number of rounds from the calendar.",
    "PLG_API_VEKN_ARCHON_TABLE_ROUNDS_MISMATCH_MESSAGE": "The number of rounds covered by the tables do not match the expected number of rounds.",
    "PLG_API_VEKN_ARCHON_TABLE_VEKN_NUMBERS_MISMATCH_MESSAGE": "The VEKN numbers of the players in the tables do not match the VEKN numbers of the ranking.",
    "PLG_API_VEKN_ARCHON_TABLE_DUPLICATE_VEKN_ID_ON_ROUND": "Duplicate VEKN id on a table",
    "PLG_API_VEKN_ARCHON_TABLE_MORE_THAN_ONE_FINAL_TABLE": "More than one final table was found.",
    "PLG_API_VEKN_START_DATE_BEFORE_END_DATE_MESSAGE": "Start date must be before end date.",
    "PLG_API_VEKN_EVENT_NAME_LENGTH_MESSAGE": "Event name must be between 3 and 120 characters.",
    "PLG_API_VEKN_INVALID_ROUNDS_MESSAGE": "Invalid numbers of rounds, must be between 2, 3 or 4.",
    "PLG_API_VEKN_INVALID_EVENT_TYPE_MESSAGE": "Invalid event type.",
    "PLG_API_VEKN_NOT_A_PRINCE_MESSAGE": "You are not a prince.",
    "PLG_API_VEKN_INVALID_VENUE_MESSAGE": "Invalid venue.",
    "PLG_API_TOO_MANY_EVENTS_MESSAGE": "You have created too many events over the past month.",
    "PLG_API_VEKN_EVENT_ALREADY_EXISTS_MESSAGE": "An event with the same name already exists for this date.",
    "PLG_API_VEKN_ORGANIZER_VEKN_ID_INVALID_MESSAGE": "Invalid VEKN ID: organizer",
    "PLG_API_VEKN_UNSUPPORTED_METHOD": "Unsupported method,please use post method",
    "PLG_API_VEKN_UNSUPPORTED_METHOD_POST": "Unsupported method,please use get method",
}


class VEKNAPIError(Exception):
    """VEKN API error."""


class VEKNAPIClient:
    """Client for VEKN API."""

    def __init__(self) -> None:
        """Initialize VEKN API client."""
        self.base_url = os.getenv("VEKN_API_BASE_URL", "https://www.vekn.net/api")
        self.username = os.getenv("VEKN_API_USERNAME")
        self.password = os.getenv("VEKN_API_PASSWORD")
        self._auth_token: str | None = None
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            # Use longer timeout for VEKN API operations (can be slow)
            timeout = aiohttp.ClientTimeout(total=120, connect=30, sock_read=60)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _authenticate(self) -> None:
        """Authenticate with VEKN API and get auth token."""
        if (
            not self.username
            or not self.password
            or not self.username.strip()
            or not self.password.strip()
        ):
            raise VEKNAPIError(
                "VEKN_API_USERNAME and VEKN_API_PASSWORD must be set in environment"
            )

        try:
            session = self._get_session()
            async with session.post(
                f"{self.base_url}/index.php",
                params={"app": "vekn", "resource": "login", "format": "raw"},
                data={"username": self.username, "password": self.password},
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # VEKN API nests the actual data inside a 'data' field
                inner_data = data.get("data", {})
                self._check_vekn_error(inner_data, "Authentication failed")
                self._auth_token = inner_data.get("auth")
                if not self._auth_token:
                    raise VEKNAPIError(f"No auth token in response: {data}")

                logger.info("Successfully authenticated with VEKN API")

        except aiohttp.ClientError as e:
            raise VEKNAPIError(f"HTTP error during authentication: {e}") from e

    def _check_vekn_error(self, data: dict[str, Any], context: str = "") -> None:
        """Check VEKN response for error codes and raise appropriate exception."""
        code = data.get("code", 200)
        # Normalize code to int (API returns string "200" or int 200)
        if isinstance(code, str):
            code = int(code) if code.isdigit() else 0
        if code not in (200,):
            message = data.get("message", "Unknown error")
            message = VEKN_MESSAGES.get(message, message)
            prefix = f"{context}: " if context else ""
            raise VEKNAPIError(f"{prefix}{message} (code: {code})")

    async def _ensure_authenticated(self) -> None:
        """Ensure we have a valid auth token."""
        if not self._auth_token:
            await self._authenticate()

    async def search_players(self, filter_str: str) -> list[dict[str, Any]]:
        """
        Search for players in the VEKN registry.

        Args:
            filter_str: Search filter (name or VEKN ID)

        Returns:
            List of player dictionaries
        """
        await self._ensure_authenticated()

        try:
            # Build params with auth key
            params = {
                "app": "vekn",
                "resource": "registry",
                "format": "raw",
                "filter": filter_str,
            }
            if self._auth_token:
                params["key"] = self._auth_token

            session = self._get_session()
            async with session.get(
                f"{self.base_url}/index.php",
                params=params,
            ) as response:
                response.raise_for_status()

                # Check for empty response
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

                # VEKN API nests data inside 'data' field
                inner_data = data.get("data", {})
                # Check for errors (some endpoints don't return code on success)
                if "code" in inner_data:
                    self._check_vekn_error(
                        inner_data, f"Search failed for '{filter_str}'"
                    )

                if "players" not in inner_data:
                    logger.warning(f"No players found for filter: {filter_str}")
                    return []

                return inner_data["players"]

        except aiohttp.ClientError as e:
            raise VEKNAPIError(f"HTTP error searching players: {e}") from e

    async def fetch_event(self, event_id: int) -> dict | None:
        """Fetch a single event by ID. Returns event dict or None if not found.

        VEKN API returns: data.events = [{...}] for valid events.
        """
        try:
            params = {
                "app": "vekn",
                "resource": "event",
                "format": "raw",
                "id": str(event_id),
            }
            if self._auth_token:
                params["key"] = self._auth_token

            session = self._get_session()
            async with session.get(
                f"{self.base_url}/index.php", params=params
            ) as response:
                if response.status == 404:
                    return None
                response.raise_for_status()
                content = await response.read()
                if not content or not content.strip():
                    return None
                try:
                    data = await response.json()
                except Exception:
                    return None
                inner = data.get("data", {})
                if "code" in inner:
                    code = inner.get("code", 200)
                    if isinstance(code, str):
                        code = int(code) if code.isdigit() else 0
                    if code != 200:
                        return None
                # Extract first event from the events list
                events = inner.get("events", [])
                if not events:
                    return None
                return events[0]
        except aiohttp.ClientError:
            return None

    async def fetch_all_events(
        self, max_id: int = 14000, batch_size: int = 10
    ) -> AsyncIterator[dict]:
        """Enumerate event IDs 1..max_id in parallel batches.

        Yields event dicts (venue info is embedded in the event response).
        Filters: events with players OR future events without players.
        """
        import asyncio
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        await self._ensure_authenticated()

        found = 0
        for start in range(1, max_id + 1, batch_size):
            end = min(start + batch_size, max_id + 1)
            tasks = [self.fetch_event(eid) for eid in range(start, end)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for event_data in results:
                if isinstance(event_data, Exception) or event_data is None:
                    continue

                players = event_data.get("players", [])
                # Check if future event
                start_date_str = event_data.get("event_startdate", "")
                is_future = False
                if start_date_str:
                    try:
                        sd = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                        is_future = sd > now
                    except (ValueError, TypeError):
                        pass

                # Filter: has players (finished) OR is future (planned)
                if not players and not is_future:
                    continue

                found += 1
                yield event_data

            # Progress log every 100 batches (1000 IDs)
            if start % 1000 == 1:
                logger.info(
                    f"VEKN event scan: checked IDs {start}-{end - 1}, "
                    f"{found} events found so far"
                )

    async def _fetch_by_prefix(
        self, prefix: str, seen_ids: set[str], depth: int = 0
    ) -> list[dict[str, Any]]:
        """
        Recursively fetch players by prefix, subdividing when hitting the 100-result limit.

        Args:
            prefix: Current search prefix (e.g., "10", "100", "1001")
            seen_ids: Set of already-seen VEKN IDs for deduplication
            depth: Recursion depth (for logging)

        Returns:
            List of unique players for this prefix
        """
        players = await self.search_players(prefix)

        # Deduplicate
        unique_players = []
        for player in players:
            vekn_id = str(player.get("veknid", ""))
            if vekn_id and vekn_id not in seen_ids:
                seen_ids.add(vekn_id)
                unique_players.append(player)

        # If we hit the limit, subdivide with next digit (0-9)
        if len(players) >= 100:
            for digit in range(10):
                sub_prefix = f"{prefix}{digit}"
                sub_players = await self._fetch_by_prefix(
                    sub_prefix, seen_ids, depth + 1
                )
                unique_players.extend(sub_players)

        return unique_players

    async def fetch_all_members(self) -> list[dict[str, Any]]:
        """
        Fetch all VEKN members by searching with ranges.

        VEKN IDs are 7 digits (0000000-9999999). The API returns max 100 results
        per query. We search by prefixes and recursively subdivide when hitting
        the limit to ensure full coverage.

        Returns:
            List of all player dictionaries
        """
        await self._ensure_authenticated()

        all_players: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # Search by 2-digit prefixes (00-99)
        # API pads these to ranges: "00" -> 0000000-0099999, "10" -> 1000000-1099999
        for prefix in range(100):
            prefix_str = f"{prefix:02d}"
            try:
                players = await self._fetch_by_prefix(prefix_str, seen_ids)
                all_players.extend(players)
            except VEKNAPIError as e:
                logger.error(f"Error fetching players for prefix {prefix_str}: {e}")
                continue

        logger.info(f"Total unique players fetched: {len(all_players)}")
        return all_players
