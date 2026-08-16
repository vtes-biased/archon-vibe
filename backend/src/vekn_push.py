import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import msgspec

from .broadcast import broadcast_precomputed
from .db import (
    batch_read_connection,
    get_sanctions_for_tournament,
    get_tournament_by_uid,
    get_user_by_uid,
    save_tournament,
    save_user,
    tournament_transaction,
)
from .models import (
    ObjectType,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)
from .ratings import _compute_entry, _engine, _final_positions
from .vekn_api import VEKNAPIClient, VEKNAPIConnectionError, VEKNAPIError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def vekn_push_client() -> AsyncIterator[VEKNAPIClient | None]:
    """Yield a VEKNAPIClient when VEKN_PUSH is enabled (else None); always closes it."""
    if os.getenv("VEKN_PUSH", "").lower() != "true":
        yield None
        return
    client = VEKNAPIClient()
    try:
        yield client
    finally:
        await client.close()


# Reverse of EVENT_TYPE_MAP — lossy: several VEKN types map to the same
# (format, rank), so only the most common type per combination survives here.
FORMAT_RANK_TO_VEKN_TYPE: dict[tuple[TournamentFormat, TournamentRank], int] = {
    (TournamentFormat.Standard, TournamentRank.BASIC): 2,  # Standard Constructed
    (TournamentFormat.Standard, TournamentRank.NC): 8,  # National Championship
    (TournamentFormat.Standard, TournamentRank.CC): 6,  # Continental Championship
    (TournamentFormat.Limited, TournamentRank.BASIC): 3,  # Limited
    (TournamentFormat.Limited, TournamentRank.NC): 13,  # Limited NC
    (TournamentFormat.Limited, TournamentRank.CC): 14,  # Limited CC
    (TournamentFormat.V5, TournamentRank.BASIC): 16,  # V5 Constructed
}


def tournament_to_vekn_type(fmt: TournamentFormat, rank: TournamentRank) -> int | None:
    """Map tournament format+rank to VEKN event type ID, None when unmappable.

    No silent fallback: vekn.net rates off its own event type, so filing a
    championship as Standard Constructed costs every finalist their rank bonus.
    """
    return FORMAT_RANK_TO_VEKN_TYPE.get((fmt, rank))


def generate_archondata(
    tournament: Tournament,
    users_by_uid: dict[str, User],
    sanctions: list | None = None,
) -> str:
    nrounds = len(tournament.rounds) + (1 if tournament.finals else 0)

    finals_vp: dict[str, float] = {}
    if tournament.finals:
        for seat in tournament.finals.seating:
            finals_vp[seat.player_uid] = seat.result.vp

    # Hoisted out of the loop (avoids O(players) re-encodes); sanctions feed rtp so
    # the SA penalty reaches the pushed rating (standing.vp is already SA-adjusted).
    t_json = msgspec.json.encode(tournament).decode()
    sanctions_json = msgspec.json.encode(sanctions or []).decode()
    player_count = _engine.attested_player_count(t_json)
    positions = _final_positions(tournament)

    parts: list[str] = []
    # Iterate standings, not tournament.players — a registered no-show stays
    # out, keeping the pushed RTP field count matched to vekn's.
    for rank_idx, standing in enumerate(tournament.standings, 1):
        user = users_by_uid.get(standing.user_uid)
        if not user:
            continue
        # Proxies never push to VEKN; they sort last in standings so skipping
        # them doesn't disturb the leading competitors' rank_idx.
        if standing.non_competing:
            continue

        name_parts = (user.name or "").split(maxsplit=1)
        first = name_parts[0] if name_parts else ""
        last = name_parts[1] if len(name_parts) > 1 else ""
        city = user.city or ""
        vekn_id = user.vekn_id or ""

        gw = standing.gw

        vpf = finals_vp.get(standing.user_uid, 0.0)

        entry = _compute_entry(
            tournament,
            t_json,
            sanctions_json,
            standing.user_uid,
            player_count,
            positions,
        )
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

    if not tournament.name or len(tournament.name) < 3:
        logger.warning(f"Tournament {tournament.uid}: name too short for VEKN")
        return None
    if not tournament.organizers_uids:
        logger.warning(f"Tournament {tournament.uid}: no organizers")
        return None

    organizer = await get_user_by_uid(tournament.organizers_uids[0])
    if not organizer or not organizer.vekn_id:
        logger.warning(f"Tournament {tournament.uid}: organizer has no VEKN ID")
        return None

    event_type = tournament_to_vekn_type(tournament.format, tournament.rank)
    if event_type is None:
        logger.warning(
            f"Tournament {tournament.uid}: no VEKN event type for "
            f"{tournament.format.value}/{tournament.rank.value}"
        )
        return None

    # max_rounds is a per-player cap under open rounds, not the actual count —
    # report rounds run, falling back to the cap before any round exists.
    rounds = len(tournament.rounds) or tournament.max_rounds
    if rounds < 2:
        rounds = 2  # VEKN minimum

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
        end_date = start_date
    if not end_time:
        end_time = start_time  # VEKN requires a non-empty endtime

    # Derived from an actual finals object — max_rounds is a per-player cap,
    # not a finals signal.
    has_finals = 1 if tournament.finals else 0

    try:
        event_id = await client.create_event(
            name=tournament.name[:120],
            event_type=event_type,
            startdate=start_date,
            starttime=start_time,
            enddate=end_date,
            endtime=end_time,
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

    # Re-fetch under the row lock — batch_push loads rows minutes before saving,
    # so writing onto the CURRENT snapshot avoids clobbering interim /action edits.
    async with tournament_transaction(tournament.uid) as (fresh, tx_conn):
        fresh = fresh or tournament  # hard-deleted mid-push: fall back to re-create
        fresh.external_ids["vekn"] = event_id
        fresh.modified = datetime.now(UTC)
        bd = await save_tournament(fresh, conn=tx_conn)
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
    event-create too.
    """
    if not os.getenv("VEKN_PUSH", "").lower() == "true":
        return False

    if tournament.state != TournamentState.FINISHED:
        logger.warning(f"Tournament {tournament.uid}: not finished")
        return False
    if not tournament.standings:
        logger.warning(f"Tournament {tournament.uid}: no standings")
        return False

    users_by_uid: dict[str, User] = {}
    for standing in tournament.standings:
        user = await get_user_by_uid(standing.user_uid)
        if not user or not user.vekn_id:
            logger.warning(
                f"Tournament {tournament.uid}: player {standing.user_uid} has no VEKN ID, skipping push"
            )
            return False
        users_by_uid[standing.user_uid] = user

    vekn_event_id = tournament.external_ids.get("vekn")
    if not vekn_event_id:
        vekn_event_id = await push_tournament_event(
            client, tournament, raise_api_errors=raise_api_errors
        )
        if not vekn_event_id:
            logger.error(f"Tournament {tournament.uid}: cannot create VEKN event")
            return False

    # sanctions feed the SA-adjusted rating points in the archondata
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

    # Re-fetch under the row lock — the archondata snapshot may be minutes
    # stale; this also picks up external_ids.vekn if create_event just set it.
    async with tournament_transaction(tournament.uid) as (fresh, tx_conn):
        fresh = fresh or tournament  # hard-deleted mid-push: fall back to re-create
        fresh.vekn_pushed_at = datetime.now(UTC)
        fresh.modified = datetime.now(UTC)
        bd = await save_tournament(fresh, conn=tx_conn)
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

    # Re-fetch — batch_push may have loaded this user minutes ago; write only
    # the vekn-sync flags so interim profile edits aren't clobbered.
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

    Failures are log-only — vekn_synced stays false, so batch_push retries hourly.
    """
    try:
        async with vekn_push_client() as client:
            if client is not None:
                await push_member(client, user)
    except Exception:
        logger.exception(f"Failed to push member {user.vekn_id} to VEKN")


# Planned drafts included on purpose (create() pushes regardless of state; this
# retries failures). open_rounds/self_organized_rounds are non-VEKN — never pushed.
UNCREATED_EVENTS_QUERY = """
    SELECT "full" FROM objects
    WHERE type = %s
      AND deleted_at IS NULL
      AND ("full"->'external_ids'->>'vekn') IS NULL
      AND "full"->>'vekn_pushed_at' IS NULL
      AND "full"->>'name' IS NOT NULL
      AND "full"->>'start' IS NOT NULL
      AND ("full"->>'open_rounds') IS DISTINCT FROM 'true'
      AND ("full"->>'self_organized_rounds') IS DISTINCT FROM 'true'
      -- Archive reconstructions carry no vekn id by design, so without this the
      -- push would happily create 2005 calendar entries on vekn.net.
      AND ("full"->'external_ids'->>'twda') IS NULL
"""

# The rounds guard excludes results that didn't originate here (VEKN imports, ETL
# history — standings but no round data) even when vekn_pushed_at was never stamped.
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
    Fail-fast: the first VEKNAPIConnectionError aborts the whole batch rather than
    re-timing-out every remaining item serially; per-item data errors just skip that item."""
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
        async with batch_read_connection() as conn:
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
        async with batch_read_connection() as conn:
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
        async with batch_read_connection() as conn:
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
                    # Retries the TWDA submission for events finished offline that
                    # never saw it. Late import: routes.tournaments imports this module.
                    from .routes.tournaments import maybe_submit_twda

                    # Re-fetch: the push just rewrote the row.
                    fresh = await get_tournament_by_uid(t.uid)
                    if fresh:
                        await maybe_submit_twda(fresh)
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
