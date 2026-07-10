"""VEKN tournament synchronization service."""

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import uuid7
from zoneinfo import ZoneInfo

import msgspec

from .broadcast import broadcast_precomputed
from .data.timezones import CITY_TZ_OVERRIDES, COUNTRY_TIMEZONE
from .db import (
    decode_json,
    get_connection,
    get_tournament_by_external_id,
    save_tournament,
    tournament_transaction,
)
from .models import (
    FinalsTable,
    ObjectType,
    PaymentStatus,
    Player,
    PlayerState,
    Score,
    Seat,
    Standing,
    TableState,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)
from .vekn_api import VEKNAPIClient

logger = logging.getLogger(__name__)

# VEKN event type → (format, rank)
EVENT_TYPE_MAP: dict[int, tuple[TournamentFormat, TournamentRank]] = {
    1: (TournamentFormat.Limited, TournamentRank.BASIC),  # Demo
    2: (TournamentFormat.Standard, TournamentRank.BASIC),  # Standard Constructed
    3: (TournamentFormat.Limited, TournamentRank.BASIC),  # Limited
    4: (TournamentFormat.Standard, TournamentRank.BASIC),  # Mini Qualifier
    5: (TournamentFormat.Standard, TournamentRank.BASIC),  # Continental Qualifier
    6: (TournamentFormat.Standard, TournamentRank.CC),  # Continental Championship
    7: (TournamentFormat.Standard, TournamentRank.BASIC),  # National Qualifier
    8: (TournamentFormat.Standard, TournamentRank.NC),  # National Championship
    9: (TournamentFormat.Limited, TournamentRank.BASIC),  # Storyline
    10: (TournamentFormat.Limited, TournamentRank.BASIC),  # Launch Event
    11: (TournamentFormat.Limited, TournamentRank.BASIC),  # BYOS
    12: (TournamentFormat.Limited, TournamentRank.BASIC),  # Unsanctioned
    13: (TournamentFormat.Limited, TournamentRank.BASIC),  # Limited NC
    14: (TournamentFormat.Limited, TournamentRank.BASIC),  # Limited CC
    15: (TournamentFormat.Standard, TournamentRank.BASIC),  # Grand Prix
    16: (TournamentFormat.V5, TournamentRank.BASIC),  # V5 Constructed
}


def _guess_timezone(
    country: str | None, venue_city: str = "", address: str = ""
) -> str:
    """Best-effort IANA timezone from country code and venue location."""
    if not country:
        return "UTC"
    country = country.upper()
    # Check city overrides for multi-timezone countries
    location = f"{venue_city} {address}".lower()
    for cc, city, tz in CITY_TZ_OVERRIDES:
        if cc == country and city.lower() in location:
            return tz
    return COUNTRY_TIMEZONE.get(country, "UTC")


def _parse_rounds(raw: Any) -> int:
    """VEKN event 'rounds' field → preliminary round count (the app's "number of
    rounds").

    VEKN encodes it as a string like "3R+F" — the leading integer is the number
    of preliminary rounds; the trailing "+F" just marks that a final is played
    (the app tracks finals separately, so it isn't counted here). A plain int
    or junk both degrade to the leading-digits read (→ 0 when absent).
    """
    m = re.match(r"\s*(\d+)", str(raw))
    return int(m.group(1)) if m else 0


def _parse_date(
    date_str: str | None, time_str: str | None = None, tz_name: str = "UTC"
) -> datetime | None:
    """Parse date and optional time strings from VEKN API as local time, convert to UTC.

    date_str: "YYYY-MM-DD", time_str: "HH:MM:SS" or "HH:MM"
    tz_name: IANA timezone name (times are interpreted as local to this zone)
    """
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if time_str:
            fmt = "%H:%M:%S" if len(time_str) > 5 else "%H:%M"
            t = datetime.strptime(time_str, fmt)
            dt = dt.replace(hour=t.hour, minute=t.minute, second=t.second)
        tz = ZoneInfo(tz_name)
        return dt.replace(tzinfo=tz).astimezone(UTC)
    except (ValueError, TypeError, KeyError):
        return None


def _map_vekn_to_tournament(
    data: dict[str, Any],
    users_by_vekn_id: dict[str, User],
    venue_data: dict[str, str] | None = None,
) -> Tournament | None:
    """Map VEKN event data to a Tournament object.

    VEKN event fields:
      event_id, event_name, event_startdate, event_starttime,
      event_enddate, event_endtime, event_isonline, eventtype_id, rounds,
      venue_name, venue_city, venue_country, venue_id,
      players[{pos, veknid, gw, vp, tp, tie, vpf, ...}]
    venue_data (from separate /venue/<id> call):
      name, address, city, country, website, zip, phone, email, lat, lng
    """
    event_id = data.get("event_id")
    if not event_id:
        return None

    venue_data = venue_data or {}

    # Event type mapping
    event_type = int(data.get("eventtype_id", 0) or 0)
    fmt, rank = EVENT_TYPE_MAP.get(
        event_type, (TournamentFormat.Standard, TournamentRank.BASIC)
    )

    name = data.get("event_name") or f"VEKN Event {event_id}"
    country = data.get("venue_country") or None

    # Online detection
    online = str(data.get("event_isonline", "0")) == "1"

    # Venue info: name from event, address/website from venue details
    venue = data.get("venue_name") or ""
    address = venue_data.get("address") or ""

    # Guess timezone from venue location (VEKN times are local)
    venue_city = venue_data.get("city") or data.get("venue_city") or ""
    tz_name = "UTC" if online else _guess_timezone(country, venue_city, address)
    start = _parse_date(
        data.get("event_startdate"), data.get("event_starttime"), tz_name
    )
    finish = _parse_date(data.get("event_enddate"), data.get("event_endtime"), tz_name)
    if address and venue_data.get("city"):
        address += f", {venue_data['city']}"
    elif not address:
        address = data.get("venue_city") or ""
    venue_url = venue_data.get("website") or ""

    # Build map URL: prefer coordinates from VEKN venue data, fall back to text search
    map_url = ""
    if not online:
        lat = venue_data.get("lat")
        lng = venue_data.get("lng")
        try:
            lat_f, lng_f = float(lat), float(lng)  # type: ignore[arg-type]
            if lat_f != 0 or lng_f != 0:
                map_url = (
                    f"https://www.google.com/maps/search/?api=1&query={lat_f},{lng_f}"
                )
        except (TypeError, ValueError):
            pass
        if not map_url and address:
            parts = [p for p in [venue, address, country] if p]
            map_url = f"https://www.google.com/maps/search/?api=1&query={quote(' '.join(parts))}"

    # Organizer
    organizer_vekn = str(data.get("organizer_veknid") or "")
    organizer_user = users_by_vekn_id.get(organizer_vekn)
    organizers_uids = [organizer_user.uid] if organizer_user else []

    # Number of preliminary rounds (the app's "round count" field).
    max_rounds = _parse_rounds(data.get("rounds"))

    # Players
    vekn_players = data.get("players", [])
    now = datetime.now(UTC)

    if vekn_players:
        # Finished tournament with results
        state = TournamentState.FINISHED
        players: list[Player] = []
        standings: list[Standing] = []
        winner_uid = ""
        # Finalists for a reconstructed finals object: (user_uid, pos, vpf).
        finalists: list[tuple[str, int, float]] = []

        for vp_data in vekn_players:
            vekn_id = str(vp_data.get("veknid") or "")
            user = users_by_vekn_id.get(vekn_id)
            if not user:
                continue

            # VEKN reports prelim GW/VP, separate finals VP (vpf), and a final
            # placement (pos 1..5); pos==1 is the tournament winner.
            prelim_gw = int(vp_data.get("gw", 0) or 0)
            pos = str(vp_data.get("pos") or "")
            is_finalist = pos in ("1", "2", "3", "4", "5")
            vp_prelim = float(vp_data.get("vp", 0) or 0)
            vp_finals = float(vp_data.get("vpf", 0) or 0)
            tp = int(vp_data.get("tp", 0) or 0)
            toss = int(vp_data.get("tie", 0) or 0)
            if pos == "1":
                winner_uid = user.uid
            if is_finalist:
                finalists.append((user.uid, int(pos), vp_finals))

            # Player.result is the full aggregate (prelim + finals win), like every
            # other importer. Standings stay PRELIM-ONLY (the contract): finals live
            # in the reconstructed finals object below; rating/league add them on top.
            players.append(
                Player(
                    user_uid=user.uid,
                    state=PlayerState.FINISHED,
                    payment_status=PaymentStatus.PAID,
                    toss=toss,
                    result=Score(
                        gw=prelim_gw + (1 if pos == "1" else 0),
                        vp=vp_prelim + vp_finals,
                        tp=tp,
                    ),
                    finalist=is_finalist,
                )
            )
            standings.append(
                Standing(
                    user_uid=user.uid,
                    gw=float(prelim_gw),
                    vp=vp_prelim,
                    tp=tp,
                    toss=toss,
                    finalist=is_finalist,
                )
            )

        if not players:
            return None  # All players unknown

        # Reconstruct a finals object iff a final was actually played (some vpf > 0).
        # VEKN gives no finals seating, so seats are ordered by final placement
        # (synthetic seed_order, display/record only — nothing computes off it; the
        # winner + per-seat vpf are known). Winner gets the +1 GW, vp = their vpf,
        # tp = 0 (no seat order to derive a real table-point from; keeps the league
        # RTP/GP displayed TP at prelim levels, unchanged from before this fix).
        finals: FinalsTable | None = None
        if sum(vpf for _, _, vpf in finalists) > 0:
            finalists.sort(key=lambda f: f[1])  # by final placement (pos 1..5)
            finals = FinalsTable(
                seating=[
                    Seat(
                        player_uid=uid,
                        result=Score(gw=1 if pos == 1 else 0, vp=vpf, tp=0),
                    )
                    for uid, pos, vpf in finalists
                ],
                seed_order=[uid for uid, _, _ in finalists],
                state=TableState.FINISHED,
            )

        # Sort standings: GW desc, VP desc, TP desc, toss desc, then user_uid asc as
        # a total-order tiebreak. Without it, tied rows keep VEKN's API order, which
        # can differ across syncs → the standings-equality check below (self-heal)
        # would see a spurious diff and re-import/re-broadcast on every run.
        standings.sort(key=lambda s: (-s.gw, -s.vp, -s.tp, -s.toss, s.user_uid))

        return Tournament(
            uid=str(uuid7()),
            modified=now,
            name=name,
            format=fmt,
            rank=rank,
            online=online,
            start=start,
            finish=finish or start,
            timezone=tz_name,
            country=country,
            state=state,
            venue=venue,
            venue_url=venue_url,
            address=address,
            map_url=map_url,
            external_ids={"vekn": str(event_id)},
            organizers_uids=organizers_uids,
            max_rounds=max_rounds,
            players=players,
            winner=winner_uid,
            standings=standings,
            finals=finals,
            # Results came FROM vekn.net — stamp so batch_push never re-uploads them
            # (round-tripping our own import back to the source of record is pointless
            # and the synthetic finals seating carries no info VEKN didn't already have).
            vekn_pushed_at=now,
        )
    else:
        # Future planned tournament (no players yet)
        return Tournament(
            uid=str(uuid7()),
            modified=now,
            name=name,
            format=fmt,
            rank=rank,
            online=online,
            start=start,
            finish=finish,
            timezone=tz_name,
            country=country,
            state=TournamentState.PLANNED,
            venue=venue,
            venue_url=venue_url,
            address=address,
            map_url=map_url,
            external_ids={"vekn": str(event_id)},
            organizers_uids=organizers_uids,
            max_rounds=max_rounds,
        )


async def _build_users_by_vekn_id() -> dict[str, User]:
    """Build a lookup dict of User by VEKN ID from the database."""
    result_map: dict[str, User] = {}
    async with get_connection() as conn:
        cursor = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = %s AND "full"->>'vekn_id' IS NOT NULL AND "full"->>'vekn_id' != ''""",
            (ObjectType.USER,),
        )
        rows = await cursor.fetchall()
        for row in rows:
            user = decode_json(row[0], User)
            if user.vekn_id:
                result_map[user.vekn_id] = user
    return result_map


async def sync_all_tournaments(client: VEKNAPIClient) -> dict[str, int]:
    """Sync all VEKN tournaments.

    Returns stats: {created, updated, unchanged, errors, skipped, total}.
    """
    logger.info("Starting VEKN tournament sync")
    stats = {
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": 0,
        "skipped": 0,
        "total": 0,
    }

    users_by_vekn_id = await _build_users_by_vekn_id()
    logger.info(f"Loaded {len(users_by_vekn_id)} users by VEKN ID")

    # Cache venue data to avoid repeated API calls for the same venue
    venue_cache: dict[str, dict[str, str]] = {}

    async for event_data in client.fetch_all_events():
        stats["total"] += 1
        event_id = event_data.get("event_id", "?")

        try:
            # Fetch full venue details (cached per venue_id)
            venue_id = str(event_data.get("venue_id") or "")
            if venue_id and venue_id not in venue_cache:
                venue_cache[venue_id] = await client.fetch_venue(venue_id)
            venue_data = venue_cache.get(venue_id, {})

            tournament = _map_vekn_to_tournament(
                event_data, users_by_vekn_id, venue_data
            )
            if not tournament:
                stats["skipped"] += 1
                continue

            # Check if already exists (unlocked lookup by external id → uid)
            existing_ref = await get_tournament_by_external_id("vekn", str(event_id))
            if existing_ref:
                bd = None
                # Re-read the row under a FOR UPDATE lock so this wholesale overwrite
                # serializes against any concurrent /action commit rather than
                # clobbering it (the meta path replaces onto the LOCKED row, so live
                # play data added mid-sync survives).
                async with tournament_transaction(existing_ref.uid) as (
                    existing,
                    tx_conn,
                ):
                    existing = existing or existing_ref  # hard-deleted between reads
                    merged_organizers = list(
                        dict.fromkeys(
                            existing.organizers_uids + tournament.organizers_uids
                        )
                    )
                    if existing.rounds:
                        # Tournament was run in-app (it has per-round play data). VEKN.net
                        # is NOT authoritative for its rounds/finals/standings/players/
                        # winner/state — only for descriptive event metadata. Refresh
                        # metadata only and NEVER overwrite the play data (doing so would
                        # silently wipe rounds and corrupt standings/ratings). Gate on
                        # `rounds` only: a re-imported VEKN event now carries a
                        # reconstructed finals object, but VEKN stays authoritative for
                        # it (a final implies prelim rounds, so this never misses in-app).
                        meta_changed = (
                            existing.name != tournament.name
                            or existing.format != tournament.format
                            or existing.rank != tournament.rank
                            or existing.start != tournament.start
                            or existing.finish != tournament.finish
                            or existing.timezone != tournament.timezone
                            or existing.country != tournament.country
                            or existing.online != tournament.online
                            or existing.venue != tournament.venue
                            or existing.address != tournament.address
                            or existing.venue_url != tournament.venue_url
                            or existing.map_url != tournament.map_url
                            or merged_organizers != existing.organizers_uids
                        )
                        if meta_changed:
                            updated = msgspec.structs.replace(
                                existing,
                                modified=datetime.now(UTC),
                                name=tournament.name,
                                format=tournament.format,
                                rank=tournament.rank,
                                online=tournament.online,
                                start=tournament.start,
                                finish=tournament.finish,
                                timezone=tournament.timezone,
                                country=tournament.country,
                                venue=tournament.venue,
                                venue_url=tournament.venue_url,
                                address=tournament.address,
                                map_url=tournament.map_url,
                                organizers_uids=merged_organizers,
                            )
                            bd = await save_tournament(updated, conn=tx_conn)
                            stats["updated"] += 1
                        else:
                            stats["unchanged"] += 1
                    else:
                        # vekn-origin import (no play data): VEKN.net is authoritative for
                        # everything, including players/standings/winner.
                        changed = (
                            existing.state != tournament.state
                            or existing.name != tournament.name
                            or existing.format != tournament.format
                            or existing.rank != tournament.rank
                            or existing.start != tournament.start
                            or existing.finish != tournament.finish
                            or existing.timezone != tournament.timezone
                            or existing.country != tournament.country
                            or existing.online != tournament.online
                            or existing.winner != tournament.winner
                            or existing.venue != tournament.venue
                            or existing.address != tournament.address
                            or existing.venue_url != tournament.venue_url
                            or existing.map_url != tournament.map_url
                            or len(existing.players) != len(tournament.players)
                            # Compare the authoritative play data so a VEKN-side score
                            # correction is picked up — and so legacy folded imports (old
                            # standings = prelim+finals, finals=None) self-heal to the
                            # prelim-only + reconstructed-finals shape on the next sync.
                            # Deterministic mapping ⇒ a migrated import compares equal and
                            # won't thrash.
                            or existing.standings != tournament.standings
                            or existing.finals != tournament.finals
                        )
                        if changed:
                            tournament = Tournament(
                                uid=existing.uid,
                                modified=datetime.now(UTC),
                                name=tournament.name,
                                format=tournament.format,
                                rank=tournament.rank,
                                online=tournament.online,
                                start=tournament.start,
                                finish=tournament.finish,
                                timezone=tournament.timezone,
                                country=tournament.country,
                                state=tournament.state,
                                venue=tournament.venue,
                                venue_url=tournament.venue_url,
                                address=tournament.address,
                                map_url=tournament.map_url,
                                external_ids=tournament.external_ids,
                                organizers_uids=merged_organizers,
                                max_rounds=tournament.max_rounds,
                                players=tournament.players,
                                winner=tournament.winner,
                                standings=tournament.standings,
                                finals=tournament.finals,
                                vekn_pushed_at=tournament.vekn_pushed_at,
                                # Preserve the stored code — the freshly-built
                                # `tournament` carries a new default_factory random
                                # value that would break an already-printed QR.
                                checkin_code=existing.checkin_code,
                            )
                            bd = await save_tournament(tournament, conn=tx_conn)
                            stats["updated"] += 1
                        else:
                            stats["unchanged"] += 1
                if bd is not None:
                    broadcast_precomputed(bd)
            else:
                # Fresh vekn-origin import: no existing row to lock.
                async with get_connection() as conn:
                    bd = await save_tournament(tournament, conn=conn)
                broadcast_precomputed(bd)
                stats["created"] += 1

        except Exception as e:
            logger.error(f"Error syncing VEKN event {event_id}: {e}")
            stats["errors"] += 1

        # Progress log every 100 events
        total = (
            stats["created"]
            + stats["updated"]
            + stats["unchanged"]
            + stats["skipped"]
            + stats["errors"]
        )
        if total % 100 == 0:
            logger.info(
                f"VEKN tournament sync progress: {stats['created']} created, "
                f"{stats['updated']} updated, {stats['unchanged']} unchanged, "
                f"{stats['skipped']} skipped, {stats['errors']} errors"
            )

    logger.info(
        f"VEKN tournament sync completed: {stats['created']} created, "
        f"{stats['updated']} updated, {stats['unchanged']} unchanged, "
        f"{stats['skipped']} skipped, {stats['errors']} errors, {stats['total']} total"
    )
    return stats
