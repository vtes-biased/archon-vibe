"""VEKN tournament synchronization service."""

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from uuid6 import uuid7

from .db import (
    decode_json,
    get_connection,
    get_tournament_by_external_id,
    insert_tournament,
    update_tournament,
)
from .models import (
    ObjectType,
    PaymentStatus,
    Player,
    PlayerState,
    Score,
    Standing,
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


def _parse_date(s: str | None) -> datetime | None:
    """Parse a YYYY-MM-DD date string from VEKN API."""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def _map_vekn_to_tournament(
    data: dict[str, Any],
    users_by_vekn_id: dict[str, User],
    venue_data: dict[str, str] | None = None,
) -> Tournament | None:
    """Map VEKN event data to a Tournament object.

    VEKN event fields:
      event_id, event_name, event_startdate, event_enddate,
      event_isonline, eventtype_id, venue_name, venue_city,
      venue_country, venue_id, players[{pos, veknid, gw, vp, tp, tie, vpf, ...}]
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
    start = _parse_date(data.get("event_startdate"))
    finish = _parse_date(data.get("event_enddate"))
    country = data.get("venue_country") or None

    # Online detection
    online = str(data.get("event_isonline", "0")) == "1"

    # Venue info: name from event, address/website from venue details
    venue = data.get("venue_name") or ""
    address = venue_data.get("address") or ""
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
                map_url = f"https://www.google.com/maps/search/?api=1&query={lat_f},{lng_f}"
        except (TypeError, ValueError):
            pass
        if not map_url and address:
            parts = [p for p in [venue, address, country] if p]
            map_url = (
                f"https://www.google.com/maps/search/?api=1&query={quote(' '.join(parts))}"
            )

    # Organizer
    organizer_vekn = str(data.get("organizer_veknid") or "")
    organizer_user = users_by_vekn_id.get(organizer_vekn)
    organizers_uids = [organizer_user.uid] if organizer_user else []

    # Players
    vekn_players = data.get("players", [])
    now = datetime.now(UTC)

    if vekn_players:
        # Finished tournament with results
        state = TournamentState.FINISHED
        players: list[Player] = []
        standings: list[Standing] = []
        winner_uid = ""

        for vp_data in vekn_players:
            vekn_id = str(vp_data.get("veknid") or "")
            user = users_by_vekn_id.get(vekn_id)
            if not user:
                continue

            # Parse scores
            gw = int(vp_data.get("gw", 0) or 0)
            pos = str(vp_data.get("pos") or "")
            is_finalist = pos in ("1", "2", "3", "4", "5")
            if pos == "1":
                gw += 1  # Finals win
                winner_uid = user.uid

            vp_prelim = float(vp_data.get("vp", 0) or 0)
            vp_finals = float(vp_data.get("vpf", 0) or 0)
            vp = vp_prelim + vp_finals
            tp = int(vp_data.get("tp", 0) or 0)
            toss = int(vp_data.get("tie", 0) or 0)

            players.append(
                Player(
                    user_uid=user.uid,
                    state=PlayerState.FINISHED,
                    payment_status=PaymentStatus.PAID,
                    toss=toss,
                    result=Score(gw=gw, vp=vp, tp=tp),
                    finalist=is_finalist,
                )
            )
            standings.append(
                Standing(
                    user_uid=user.uid,
                    gw=float(gw),
                    vp=vp,
                    tp=tp,
                    toss=toss,
                    finalist=is_finalist,
                )
            )

        if not players:
            return None  # All players unknown

        # Sort standings: GW desc, VP desc, TP desc, toss desc
        standings.sort(key=lambda s: (-s.gw, -s.vp, -s.tp, -s.toss))

        return Tournament(
            uid=str(uuid7()),
            modified=now,
            name=name,
            format=fmt,
            rank=rank,
            online=online,
            start=start,
            finish=finish or start,
            country=country,
            state=state,
            venue=venue,
            venue_url=venue_url,
            address=address,
            map_url=map_url,
            external_ids={"vekn": str(event_id)},
            organizers_uids=organizers_uids,
            players=players,
            winner=winner_uid,
            standings=standings,
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
            country=country,
            state=TournamentState.PLANNED,
            venue=venue,
            venue_url=venue_url,
            address=address,
            map_url=map_url,
            external_ids={"vekn": str(event_id)},
            organizers_uids=organizers_uids,
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

            # Check if already exists
            existing = await get_tournament_by_external_id("vekn", str(event_id))
            if existing:
                # Only update if data actually changed
                changed = (
                    existing.state != tournament.state
                    or existing.name != tournament.name
                    or existing.format != tournament.format
                    or existing.rank != tournament.rank
                    or existing.start != tournament.start
                    or existing.finish != tournament.finish
                    or existing.country != tournament.country
                    or existing.online != tournament.online
                    or existing.winner != tournament.winner
                    or existing.venue != tournament.venue
                    or existing.address != tournament.address
                    or existing.venue_url != tournament.venue_url
                    or existing.map_url != tournament.map_url
                    or len(existing.players) != len(tournament.players)
                )
                if changed:
                    # Merge organizers: keep existing + add VEKN organizer
                    merged_organizers = list(
                        dict.fromkeys(
                            existing.organizers_uids + tournament.organizers_uids
                        )
                    )
                    tournament = Tournament(
                        uid=existing.uid,
                        modified=datetime.now(UTC),
                        name=tournament.name,
                        format=tournament.format,
                        rank=tournament.rank,
                        online=tournament.online,
                        start=tournament.start,
                        finish=tournament.finish,
                        country=tournament.country,
                        state=tournament.state,
                        venue=tournament.venue,
                        venue_url=tournament.venue_url,
                        address=tournament.address,
                        external_ids=tournament.external_ids,
                        organizers_uids=merged_organizers,
                        players=tournament.players,
                        winner=tournament.winner,
                        standings=tournament.standings,
                    )
                    await update_tournament(tournament)
                    stats["updated"] += 1
                else:
                    stats["unchanged"] += 1
            else:
                await insert_tournament(tournament)
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
