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
    get_tournament_by_uid,
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
from .vekn_api import VEKNAPIClient, VEKNAPIConnectionError, VEKNAPIError

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
    # Guard: iterate standings (seating-derived), not tournament.players, so a
    # registered no-show stays out and our pushed RTP field size matches vekn's.
    for rank_idx, standing in enumerate(tournament.standings, 1):
        user = users_by_uid.get(standing.user_uid)
        if not user:
            continue
        # Proxy (non-competing official stood in): not a real competitor — never push
        # to VEKN (the system of record). They sort last in standings, so skipping
        # them doesn't disturb the leading competitors' rank_idx.
        if standing.non_competing:
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
    *,
    raise_api_errors: bool = False,
) -> str | None:
    """Create a VEKN calendar entry for a tournament. Returns event_id or None.

    raise_api_errors=True lets a VEKNAPIError propagate instead of being logged
    and swallowed — the manual on-demand push shows VEKN's actual message to the
    organizer ('event already exists for this date', 'not a prince', ...); the
    batch path keeps the log-and-skip default."""
    if not os.getenv("VEKN_PUSH", "").lower() == "true":
        return None

    # Non-VEKN house format — never pushed (the batch queries already exclude these;
    # this guards direct callers too).
    if tournament.open_rounds or tournament.self_organized_rounds:
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

    # Determine rounds. Open rounds: max_rounds is a per-player cap, so the event can run
    # more (or fewer) total rounds than it — report the actual rounds run, falling back to
    # the cap before any round exists (calendar push at creation).
    rounds = len(tournament.rounds) or tournament.max_rounds
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

    # Base on an actual finals (max_rounds is a per-player cap now, not a finals signal).
    has_finals = 1 if tournament.finals else 0

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
            # VEKN requires a venue for in-person events; 9999 is the generic
            # placeholder venue the VEKN admins provisioned for app-created events.
            venueid=0 if tournament.online else 9999,
            multideck=tournament.multideck,
            proxies=tournament.proxies,
            description=tournament.description[:500] if tournament.description else "",
        )
    except VEKNAPIConnectionError:
        raise  # batch-fatal: let batch_push abort and retry next cycle
    except VEKNAPIError as e:
        if raise_api_errors:
            raise
        logger.error(f"Failed to create VEKN event for {tournament.uid}: {e}")
        return None

    # Store the VEKN event ID. Re-fetch first: batch_push loads rows up
    # front but saves here minutes later — only the vekn fields are ours, so we
    # write them onto a fresh snapshot instead of clobbering interim edits.
    fresh = await get_tournament_by_uid(tournament.uid) or tournament
    fresh.external_ids["vekn"] = event_id
    fresh.modified = datetime.now(UTC)
    bd = await save_tournament(fresh)
    broadcast_precomputed(bd)
    logger.info(f"Tournament {tournament.uid} → VEKN event {event_id}")
    return event_id


async def push_tournament_results(
    client: VEKNAPIClient,
    tournament: Tournament,
    *,
    raise_api_errors: bool = False,
) -> bool:
    """Upload archondata for a finished tournament. Returns True on success.

    raise_api_errors: see push_tournament_event — propagated to the nested
    event-create too."""
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
        vekn_event_id = await push_tournament_event(
            client, tournament, raise_api_errors=raise_api_errors
        )
        if not vekn_event_id:
            logger.error(f"Tournament {tournament.uid}: cannot create VEKN event")
            return False

    # Generate and upload archondata (sanctions feed the SA-adjusted rating points)
    sanctions = await get_sanctions_for_tournament(tournament.uid)
    archondata = generate_archondata(tournament, users_by_uid, sanctions)

    try:
        await client.upload_results(vekn_event_id, archondata)
    except VEKNAPIConnectionError:
        raise  # batch-fatal: let batch_push abort and retry next cycle
    except VEKNAPIError as e:
        if raise_api_errors:
            raise
        logger.error(f"Failed to upload results for {tournament.uid}: {e}")
        return False

    # Mark as pushed. Re-fetch first: the snapshot we computed archondata
    # from may be minutes stale by now — write only the vekn fields onto a fresh
    # one so concurrent edits aren't clobbered. push_tournament_event above may
    # have already bumped external_ids.vekn; re-reading picks that up too.
    fresh = await get_tournament_by_uid(tournament.uid) or tournament
    fresh.vekn_pushed_at = datetime.now(UTC)
    fresh.modified = datetime.now(UTC)
    bd = await save_tournament(fresh)
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
    except VEKNAPIConnectionError:
        raise  # batch-fatal: let batch_push abort and retry next cycle
    except VEKNAPIError as e:
        logger.error(f"Failed to push member {user.vekn_id}: {e}")
        return False

    # Re-fetch before save: batch_push may have loaded this user minutes
    # ago — write only the vekn-sync flags onto a fresh snapshot so interim
    # profile edits (name, city, roles) aren't clobbered.
    fresh = await get_user_by_uid(user.uid) or user
    fresh.vekn_synced = True
    fresh.vekn_synced_at = datetime.now(UTC)
    fresh.modified = datetime.now(UTC)
    bd = await save_user(fresh)
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


# batch_push step 2 selection: tournaments needing a vekn.net calendar event.
# The vekn_pushed_at guard keeps imported history out — ETL-migrated finished
# tournaments without a vekn id are stamped at import (no push owed) and must
# not get calendar events created for them years after the fact.
# Guard covered by test_vekn_push_batch.py.
# open_rounds / self_organized_rounds events are the non-VEKN house format — never
# create a vekn.net calendar entry for them (IS DISTINCT FROM keeps legacy rows that
# predate the flag, where ->> is NULL, in the push set).
UNCREATED_EVENTS_QUERY = """
    SELECT "full" FROM objects
    WHERE type = %s
      AND "full"->>'state' != 'Planned'
      AND deleted_at IS NULL
      AND ("full"->'external_ids'->>'vekn') IS NULL
      AND "full"->>'vekn_pushed_at' IS NULL
      AND "full"->>'name' IS NOT NULL
      AND "full"->>'start' IS NOT NULL
      AND ("full"->>'open_rounds') IS DISTINCT FROM 'true'
      AND ("full"->>'self_organized_rounds') IS DISTINCT FROM 'true'
"""

# batch_push step 3 selection. The rounds guard keeps tournaments whose results
# did not originate here (VEKN imports, ETL-migrated history — standings but no
# per-round play data) out of the push set even if their vekn_pushed_at was never
# stamped: re-pushing the source of record is pointless and archondata needs the
# round detail an import never had. Guard covered by test_vekn_push_batch.py.
UNPUSHED_RESULTS_QUERY = """
    SELECT "full" FROM objects
    WHERE type = %s
      AND "full"->>'state' = 'Finished'
      AND deleted_at IS NULL
      AND "full"->>'vekn_pushed_at' IS NULL
      AND ("full"->'external_ids'->>'vekn') IS NOT NULL
      AND jsonb_array_length(COALESCE("full"->'rounds', '[]'::jsonb)) > 0
      AND ("full"->>'open_rounds') IS DISTINCT FROM 'true'
      AND ("full"->>'self_organized_rounds') IS DISTINCT FROM 'true'
"""


async def batch_push(client: VEKNAPIClient) -> dict:
    """Push all unpushed tournaments and members. Returns stats dict.

    Fail-fast: the first VEKNAPIConnectionError (transport down, timeout,
    auth failure) aborts the whole batch rather than letting every remaining
    item re-time-out serially (30-120s each) during an outage — it reruns next
    cycle anyway. Per-item data errors (bad VEKN id, parse error) still skip just
    that item and continue.
    """
    from .db import decode_json

    stats = {
        "events_created": 0,
        "results_pushed": 0,
        "members_pushed": 0,
        "errors": 0,
        "aborted": False,
    }

    if not os.getenv("VEKN_PUSH", "").lower() == "true":
        return stats

    try:
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
            except VEKNAPIConnectionError:
                raise
            except Exception:
                logger.exception(f"Error pushing member {u.vekn_id}")
                stats["errors"] += 1

        # 2. Push calendar events for tournaments without external_ids.vekn
        async with get_connection() as conn:
            result = await conn.execute(
                UNCREATED_EVENTS_QUERY,
                (ObjectType.TOURNAMENT,),
            )
            rows = await result.fetchall()

        for row in rows:
            t = decode_json(row[0], Tournament)
            try:
                event_id = await push_tournament_event(client, t)
                if event_id:
                    stats["events_created"] += 1
            except VEKNAPIConnectionError:
                raise
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
            except VEKNAPIConnectionError:
                raise
            except Exception:
                logger.exception(f"Error pushing results for {t.uid}")
                stats["errors"] += 1
    except VEKNAPIConnectionError as e:
        logger.warning(
            f"Batch push aborted — VEKN unreachable: {e}; retries next cycle"
        )
        stats["aborted"] = True

    logger.info(f"Batch push complete: {stats}")
    return stats
