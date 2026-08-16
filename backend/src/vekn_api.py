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
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # Must complete under nginx's 60s proxy_read_timeout — the manual
            # push-vekn route runs these calls inline on the request.
            timeout = aiohttp.ClientTimeout(total=20, connect=10, sock_read=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

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
            session = self._get_session()
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

            session = self._get_session()
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

    async def create_event(
        self,
        *,
        name: str,
        event_type: int,
        startdate: str,
        starttime: str,
        enddate: str,
        endtime: str,
        rounds: int,
        final: int,
        organizer_vekn_id: str,
        online: bool = False,
        venueid: int = 0,
        timelimit: int = 120,
        multideck: bool = False,
        proxies: bool = False,
        website: str = "",
        description: str = "",
    ) -> str:
        """Create a VEKN calendar event; returns the event ID.

        VEKN's event.php requires four separate, non-empty date/time fields
        ("Y-m-d"/"H:i") — a combined value leaves two empty and 400s.
        """
        await self._ensure_authenticated()
        session = self._get_session()

        form_data = {
            "name": name,
            "type": event_type,
            "startdate": startdate,
            "starttime": starttime,
            "enddate": enddate,
            "endtime": endtime,
            "rounds": rounds,
            "final": final,
            "online": 1 if online else 0,
            "timelimit": timelimit,
            "multideck": 1 if multideck else 0,
            "proxies": 1 if proxies else 0,
        }
        if venueid:
            form_data["venueid"] = venueid
        if website:
            form_data["website"] = website
        if description:
            form_data["description"] = description

        headers: dict[str, str] = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        headers["Vekn-Id"] = organizer_vekn_id  # impersonates the organizer

        try:
            async with session.post(
                f"{self.base_url}/index.php",
                params={"app": "vekn", "resource": "event", "format": "raw"},
                data=form_data,
                headers=headers,
            ) as response:
                response.raise_for_status()
                data = await response.json()
                inner = data.get("data", {})
                self._check_vekn_error(inner, "Create event failed")
                event_id = inner.get("id")
                if not event_id:
                    raise VEKNAPIError(f"No event ID in response: {data}")
                logger.info(f"Created VEKN event {event_id}: {name}")
                return str(event_id)
        except (aiohttp.ClientError, TimeoutError) as e:
            raise VEKNAPIConnectionError(f"HTTP error creating event: {e}") from e

    async def upload_results(self, vekn_event_id: str, archondata: str) -> None:
        await self._ensure_authenticated()
        session = self._get_session()

        headers: dict[str, str] = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        try:
            async with session.post(
                f"{self.base_url}/index.php",
                params={
                    "app": "vekn",
                    "resource": "archon",
                    "format": "raw",
                    "id": vekn_event_id,
                },
                data={"archondata": archondata},
                headers=headers,
            ) as response:
                response.raise_for_status()
                data = await response.json()
                inner = data.get("data", {})
                self._check_vekn_error(inner, "Upload results failed")
                logger.info(f"Uploaded archon data for VEKN event {vekn_event_id}")
        except (aiohttp.ClientError, TimeoutError) as e:
            raise VEKNAPIConnectionError(f"HTTP error uploading results: {e}") from e

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
        session = self._get_session()

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
                self._check_vekn_error(inner, "Create member failed")
                logger.info(f"Created VEKN member {veknid}: {firstname} {lastname}")
        except (aiohttp.ClientError, TimeoutError) as e:
            raise VEKNAPIConnectionError(f"HTTP error creating member: {e}") from e

    async def fetch_venue(self, venue_id: str) -> dict[str, str]:
        """Fetch venue details by ID, or {} when absent.

        VEKN API shape: data.venues = [{name, address, city, country, ...}].
        """
        if not venue_id or venue_id == "0":
            return {}
        await self._ensure_authenticated()
        try:
            session = self._get_session()
            headers: dict[str, str] = {}
            if self._auth_token:
                headers["Authorization"] = f"Bearer {self._auth_token}"
            async with session.get(
                f"{self.base_url}/vekn/venue/{venue_id}",
                headers=headers,
            ) as response:
                if response.status != 200:
                    return {}
                data = await response.json()
                inner = data.get("data", {})
                venues = inner.get("venues", [])
                if not venues:
                    logger.warning(f"No data for venue #{venue_id}")
                    return {}
                return venues[0] or {}
        except (aiohttp.ClientError, TimeoutError, ValueError) as e:
            logger.warning(f"Error fetching venue #{venue_id}: {e}")
            return {}

    async def fetch_event(self, event_id: int) -> dict | None:
        """Fetch a single event, or None when the API confirms no event. Raises
        VEKNAPIConnectionError on a transient failure instead of returning None,
        so fetch_all_events doesn't mistake an outage for the end of the scan."""
        await self._ensure_authenticated()
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
                except Exception as e:
                    # Unparseable 200 = transient garble, not a confirmed no-event.
                    raise VEKNAPIConnectionError(
                        f"Unparseable event response for id {event_id}"
                    ) from e
                # Auth rejection is a top-level err envelope with empty data — parsed
                # naively it reads as "no events", ending the scan early on an expired token.
                err = data.get("err_code")
                if err not in (None, 0, "0", ""):
                    raise VEKNAPIConnectionError(
                        f"VEKN API error for event {event_id}: "
                        f"{data.get('err_msg')} (err_code: {err})"
                    )
                inner = data.get("data", {})
                if "code" in inner:
                    code = inner.get("code", 200)
                    if isinstance(code, str):
                        code = int(code) if code.isdigit() else 0
                    if code != 200:
                        return None
                events = inner.get("events", [])
                if not events:
                    return None
                return events[0]
        except (aiohttp.ClientError, TimeoutError) as e:
            # Transient (network / 5xx): raise vs return None so the scan doesn't
            # count an outage as the end of the ID space.
            raise VEKNAPIConnectionError(
                f"Transient error fetching event {event_id}: {e}"
            ) from e

    async def fetch_all_events(
        self,
        batch_size: int = 10,
        empty_run_limit: int = 200,
        transient_limit: int = 200,
    ) -> AsyncIterator[dict]:
        """Probe IDs upward until `empty_run_limit` consecutive confirmed-no-event
        IDs; `transient_limit` consecutive transient failures aborts the scan instead."""
        import asyncio
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        await self._ensure_authenticated()

        found = 0
        consecutive_empty = 0
        consecutive_transient = 0
        start = 1
        while consecutive_empty < empty_run_limit:
            end = start + batch_size
            tasks = [self.fetch_event(eid) for eid in range(start, end)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for event_data in results:
                if isinstance(event_data, BaseException):
                    # Must not count as empty — an outage would otherwise end
                    # the scan; abort instead if the API stays down.
                    consecutive_transient += 1
                    if consecutive_transient >= transient_limit:
                        raise VEKNAPIError(
                            f"VEKN event scan aborted near ID {start}: "
                            f"{consecutive_transient} consecutive transient failures "
                            f"(API unavailable)"
                        )
                    continue

                consecutive_transient = 0  # API reachable (event or confirmed-empty)

                if event_data is None:
                    consecutive_empty += 1
                    continue

                consecutive_empty = 0

                players = event_data.get("players", [])
                start_date_str = event_data.get("event_startdate", "")
                is_future = False
                if start_date_str:
                    try:
                        sd = datetime.strptime(start_date_str, "%Y-%m-%d").replace(
                            tzinfo=UTC
                        )
                        is_future = sd > now
                    except (ValueError, TypeError):
                        pass

                if not players and not is_future:
                    continue

                found += 1
                yield event_data

            if start % 1000 == 1:
                logger.info(
                    f"VEKN event scan: checked IDs {start}-{end - 1}, "
                    f"{found} events found, run of {consecutive_empty} empty IDs"
                )

            start = end

        # Distinguishes "reached end of ID space" from a premature abort.
        logger.info(
            f"VEKN event scan complete: stopped at ID {start - 1} after "
            f"{consecutive_empty} consecutive empty IDs, {found} events found"
        )

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

    async def fetch_all_members(self) -> list[dict[str, Any]]:
        """Fetch all VEKN members: 7-digit IDs (0000000-9999999), 100 results max
        per query — search by prefix, subdividing recursively for full coverage.
        """
        await self._ensure_authenticated()

        all_players: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        # API pads 2-digit prefixes into ranges: "00"->0000000-0099999.
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
