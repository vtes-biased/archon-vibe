"""VEKN push sync — push tournaments and members to vekn.net."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from .broadcast import broadcast_precomputed
from .db import (
    get_connection,
    get_sanctions_for_tournament,
    get_user_by_uid,
    save_tournament,
    save_user,
)
from .models import (
    ObjectType,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)
from .ratings import _compute_entry_sync
from .vekn_api import VEKNAPIClient, VEKNAPIError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def vekn_push_client() -> AsyncIterator[VEKNAPIClient | None]:
    """Yield a VEKNAPIClient when VEKN_PUSH is enabled (else None); always closes it.

    Folds the env-gate + construct + try/finally-close dance shared by every push
    call site. Callers keep their own try/except for site-specific log messages.
    """
    if os.getenv("VEKN_PUSH", "").lower() != "true":
        yield None
        return
    client = VEKNAPIClient()
    try:
        yield client
    finally:
        await client.close()


# Reverse map: (format, rank) → VEKN event type ID
# We pick the most common type for each combination
FORMAT_RANK_TO_VEKN_TYPE: dict[tuple[TournamentFormat, TournamentRank], int] = {
    (TournamentFormat.Standard, TournamentRank.BASIC): 2,  # Standard Constructed
    (TournamentFormat.Standard, TournamentRank.NC): 8,  # National Championship
    (TournamentFormat.Standard, TournamentRank.CC): 6,  # Continental Championship
    (TournamentFormat.Limited, TournamentRank.BASIC): 3,  # Limited
    (TournamentFormat.V5, TournamentRank.BASIC): 16,  # V5 Constructed
}


def tournament_to_vekn_type(fmt: TournamentFormat, rank: TournamentRank) -> int:
    """Map tournament format+rank to VEKN event type ID."""
    return FORMAT_RANK_TO_VEKN_TYPE.get((fmt, rank), 2)  # default: Standard Constructed


def generate_archondata(
    tournament: Tournament,
    users_by_uid: dict[str, User],
    sanctions: list | None = None,
) -> str:
    """Generate VEKN archondata string from tournament standings.

    Format: {nrounds}¤{rank}§{first}§{last}§{city}§{vekn}§{gw}§{vp}§{vpf}§{tp}§{toss}§{rtp}§...
    """
    nrounds = len(tournament.rounds) + (1 if tournament.finals else 0)

    # Pre-compute finals VP for finalists
    finals_vp: dict[str, float] = {}
    if tournament.finals:
        for seat in tournament.finals.seating:
            finals_vp[seat.player_uid] = seat.result.vp

    # Sanctions feed the rating-point (rtp) calculation so the SA penalty is
    # reflected in the pushed rating; the {vp} field below reads standing.vp,
    # which the engine already SA-adjusts.
    parts: list[str] = []
    for rank_idx, standing in enumerate(tournament.standings, 1):
        user = users_by_uid.get(standing.user_uid)
        if not user:
            continue

        # Split name into first/last
        name_parts = (user.name or "").split(maxsplit=1)
        first = name_parts[0] if name_parts else ""
        last = name_parts[1] if len(name_parts) > 1 else ""
        city = user.city or ""
        vekn_id = user.vekn_id or ""

        # GW: standings are prelim-only (engine compute_standings sums rounds only)
        gw = standing.gw

        vpf = finals_vp.get(standing.user_uid, 0.0)

        # Rating points
        entry = _compute_entry_sync(tournament, standing.user_uid, sanctions)
        rtp = entry.points

        parts.append(
            f"{rank_idx}§{first}§{last}§{city}§{vekn_id}§"
            f"{int(gw)}§{standing.vp}§{vpf}§{standing.tp}§{standing.toss}§{rtp}§"
        )

    return f"{nrounds}¤" + "".join(parts)


async def push_tournament_event(
    client: VEKNAPIClient,
    tournament: Tournament,
) -> str | None:
    """Create a VEKN calendar entry for a tournament. Returns event_id or None."""
    if not os.getenv("VEKN_PUSH", "").lower() == "true":
        return None

    # Validate requirements
    if not tournament.name or len(tournament.name) < 3:
        logger.warning(f"Tournament {tournament.uid}: name too short for VEKN")
        return None
    if not tournament.organizers_uids:
        logger.warning(f"Tournament {tournament.uid}: no organizers")
        return None

    # Get organizer's VEKN ID for impersonation
    organizer = await get_user_by_uid(tournament.organizers_uids[0])
    if not organizer or not organizer.vekn_id:
        logger.warning(f"Tournament {tournament.uid}: organizer has no VEKN ID")
        return None

    # Map to VEKN event type
    event_type = tournament_to_vekn_type(tournament.format, tournament.rank)

    # Determine rounds
    rounds = (
        tournament.max_rounds if tournament.max_rounds >= 2 else len(tournament.rounds)
    )
    if rounds < 2:
        rounds = 2  # VEKN minimum

    # Dates
    start_date = ""
    end_date = ""
    start_time = ""
    end_time = ""
    if tournament.start:
        if isinstance(tournament.start, str):
            dt = datetime.fromisoformat(tournament.start)
        else:
            dt = tournament.start
        start_date = dt.strftime("%Y-%m-%d")
        start_time = dt.strftime("%H:%M")
    if tournament.finish:
        if isinstance(tournament.finish, str):
            dt = datetime.fromisoformat(tournament.finish)
        else:
            dt = tournament.finish
        end_date = dt.strftime("%Y-%m-%d")
        end_time = dt.strftime("%H:%M")

    if not start_date:
        logger.warning(f"Tournament {tournament.uid}: no start date")
        return None
    if not end_date:
        end_date = start_date  # Same day

    has_finals = 1 if tournament.finals or tournament.max_rounds > 0 else 0

    try:
        event_id = await client.create_event(
            name=tournament.name[:120],
            event_type=event_type,
            startdate=f"{start_date} {start_time}" if start_time else start_date,
            enddate=f"{end_date} {end_time}" if end_time else end_date,
            rounds=rounds,
            final=has_finals,
            organizer_vekn_id=organizer.vekn_id,
            online=tournament.online,
            multideck=tournament.multideck,
            proxies=tournament.proxies,
            description=tournament.description[:500] if tournament.description else "",
        )
    except VEKNAPIError as e:
        logger.error(f"Failed to create VEKN event for {tournament.uid}: {e}")
        return None

    # Store the VEKN event ID
    tournament.external_ids["vekn"] = event_id
    tournament.modified = datetime.now(UTC)
    bd = await save_tournament(tournament)
    broadcast_precomputed(bd)
    logger.info(f"Tournament {tournament.uid} → VEKN event {event_id}")
    return event_id


async def push_tournament_results(
    client: VEKNAPIClient,
    tournament: Tournament,
) -> bool:
    """Upload archondata for a finished tournament. Returns True on success."""
    if not os.getenv("VEKN_PUSH", "").lower() == "true":
        return False

    if tournament.state != TournamentState.FINISHED:
        logger.warning(f"Tournament {tournament.uid}: not finished")
        return False
    if not tournament.standings:
        logger.warning(f"Tournament {tournament.uid}: no standings")
        return False

    # Ensure all players have VEKN IDs
    users_by_uid: dict[str, User] = {}
    for standing in tournament.standings:
        user = await get_user_by_uid(standing.user_uid)
        if not user or not user.vekn_id:
            logger.warning(
                f"Tournament {tournament.uid}: player {standing.user_uid} has no VEKN ID, skipping push"
            )
            return False
        users_by_uid[standing.user_uid] = user

    # Ensure VEKN event exists
    vekn_event_id = tournament.external_ids.get("vekn")
    if not vekn_event_id:
        vekn_event_id = await push_tournament_event(client, tournament)
        if not vekn_event_id:
            logger.error(f"Tournament {tournament.uid}: cannot create VEKN event")
            return False

    # Generate and upload archondata (sanctions feed the SA-adjusted rating points)
    sanctions = await get_sanctions_for_tournament(tournament.uid)
    archondata = generate_archondata(tournament, users_by_uid, sanctions)

    try:
        await client.upload_results(vekn_event_id, archondata)
    except VEKNAPIError as e:
        logger.error(f"Failed to upload results for {tournament.uid}: {e}")
        return False

    # Mark as pushed
    tournament.vekn_pushed_at = datetime.now(UTC)
    tournament.modified = datetime.now(UTC)
    bd = await save_tournament(tournament)
    broadcast_precomputed(bd)
    logger.info(
        f"Tournament {tournament.uid} results pushed to VEKN event {vekn_event_id}"
    )
    return True


async def push_member(
    client: VEKNAPIClient,
    user: User,
) -> bool:
    """Push a locally-created member to VEKN registry. Returns True on success."""
    if not os.getenv("VEKN_PUSH", "").lower() == "true":
        return False

    if not user.vekn_id:
        return False

    # Split name into first/last
    name_parts = (user.name or "").split(maxsplit=1)
    firstname = name_parts[0] if name_parts else "Unknown"
    lastname = name_parts[1] if len(name_parts) > 1 else "Unknown"

    email = user.contact_email or f"{user.vekn_id}@placeholder.vekn.net"
    country = user.country or ""

    try:
        await client.create_member(
            veknid=user.vekn_id,
            firstname=firstname,
            lastname=lastname,
            email=email,
            country=country,
            state=user.state or "",
            city=user.city or "",
        )
    except VEKNAPIError as e:
        logger.error(f"Failed to push member {user.vekn_id}: {e}")
        return False

    user.vekn_synced = True
    user.vekn_synced_at = datetime.now(UTC)
    user.modified = datetime.now(UTC)
    bd = await save_user(user)
    broadcast_precomputed(bd)
    logger.info(f"Member {user.vekn_id} pushed to VEKN")
    return True


async def push_member_background(user: User) -> None:
    """push_member with its own client and swallowed errors, for asyncio.create_task.

    Failures are log-only by design: the user is saved with vekn_synced=false
    before this runs, so the hourly batch_push retries until VEKN accepts.
    """
    try:
        async with vekn_push_client() as client:
            if client is not None:
                await push_member(client, user)
    except Exception:
        logger.exception(f"Failed to push member {user.vekn_id} to VEKN")


# batch_push step 3 selection. The rounds guard keeps tournaments whose results
# did not originate here (VEKN imports, ETL-migrated history — standings but no
# play data) out of the push set even if their vekn_pushed_at was never stamped:
# re-pushing them would send wrong numbers (their standings fold finals in;
# archondata assumes prelim-only). Guard covered by test_vekn_push_batch.py.
UNPUSHED_RESULTS_QUERY = """
    SELECT "full" FROM objects
    WHERE type = %s
      AND "full"->>'state' = 'Finished'
      AND deleted_at IS NULL
      AND "full"->>'vekn_pushed_at' IS NULL
      AND ("full"->'external_ids'->>'vekn') IS NOT NULL
      AND jsonb_array_length(COALESCE("full"->'rounds', '[]'::jsonb)) > 0
"""


async def batch_push(client: VEKNAPIClient) -> dict:
    """Push all unpushed tournaments and members. Returns stats dict."""
    from .db import decode_json

    stats = {"events_created": 0, "results_pushed": 0, "members_pushed": 0, "errors": 0}

    if not os.getenv("VEKN_PUSH", "").lower() == "true":
        return stats

    # 1. Push unsynced members (must come before results so VEKN knows the IDs)
    async with get_connection() as conn:
        result = await conn.execute(
            """
            SELECT "full" FROM objects
            WHERE type = %s
              AND "full"->>'vekn_id' IS NOT NULL
              AND ("full"->>'vekn_synced')::boolean = false
            """,
            (ObjectType.USER,),
        )
        rows = await result.fetchall()

    for row in rows:
        u = decode_json(row[0], User)
        try:
            if await push_member(client, u):
                stats["members_pushed"] += 1
        except Exception:
            logger.exception(f"Error pushing member {u.vekn_id}")
            stats["errors"] += 1

    # 2. Push calendar events for tournaments without external_ids.vekn
    async with get_connection() as conn:
        result = await conn.execute(
            """
            SELECT "full" FROM objects
            WHERE type = %s
              AND "full"->>'state' != 'Planned'
              AND deleted_at IS NULL
              AND ("full"->'external_ids'->>'vekn') IS NULL
              AND "full"->>'name' IS NOT NULL
              AND "full"->>'start' IS NOT NULL
            """,
            (ObjectType.TOURNAMENT,),
        )
        rows = await result.fetchall()

    for row in rows:
        t = decode_json(row[0], Tournament)
        try:
            event_id = await push_tournament_event(client, t)
            if event_id:
                stats["events_created"] += 1
        except Exception:
            logger.exception(f"Error pushing event for {t.uid}")
            stats["errors"] += 1

    # 3. Push results for finished tournaments without vekn_pushed_at.
    async with get_connection() as conn:
        result = await conn.execute(
            UNPUSHED_RESULTS_QUERY,
            (ObjectType.TOURNAMENT,),
        )
        rows = await result.fetchall()

    for row in rows:
        t = decode_json(row[0], Tournament)
        try:
            if await push_tournament_results(client, t):
                stats["results_pushed"] += 1
        except Exception:
            logger.exception(f"Error pushing results for {t.uid}")
            stats["errors"] += 1

    logger.info(f"Batch push complete: {stats}")
    return stats
