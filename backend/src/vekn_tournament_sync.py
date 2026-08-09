"""VEKN tournament synchronization service."""

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import uuid7

import msgspec

from .broadcast import broadcast_precomputed
from .data.timezones import CITY_TZ_OVERRIDES, COUNTRY_TIMEZONE
from .db import (
    decode_json,
    find_duplicate_tournament_groups,
    find_same_event_tournaments,
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
    # vekn.net gives these the championship coefficient — dropping the rank here
    # under-rates every finalist.
    13: (TournamentFormat.Limited, TournamentRank.NC),  # Limited NC
    14: (TournamentFormat.Limited, TournamentRank.CC),  # Limited CC
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


def _parse_date(date_str: str | None, time_str: str | None = None) -> datetime | None:
    """Parse VEKN date/time strings into a NAIVE wall-clock datetime.

    date_str: "YYYY-MM-DD", time_str: "HH:MM:SS" or "HH:MM"

    VEKN event times are wall clock at the venue, which is exactly how
    Tournament.start/finish are stored: naive, paired with Tournament.timezone
    (see calendar._as_utc, frontend utils.zonedDate). Converting to UTC here
    stored the instant twice over — readers that anchor the naive value in the
    tournament timezone then shifted it by the venue's offset.
    """
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if time_str:
            fmt = "%H:%M:%S" if len(time_str) > 5 else "%H:%M"
            t = datetime.strptime(time_str, fmt)
            dt = dt.replace(hour=t.hour, minute=t.minute, second=t.second)
        return dt
    except (ValueError, TypeError):
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

    # VEKN 'proxies_allowed' is "0"/"1". Championship ranks forbid proxies by rule
    # (engine validate_rank_legality), so rank wins over a mis-set calendar flag —
    # a few NC events on vekn.net do carry proxies_allowed=1, and importing that
    # combo would leave the tournament unable to save any config edit.
    proxies = (
        str(data.get("proxies_allowed", "0")) == "1" and rank == TournamentRank.BASIC
    )

    # Venue info: name from event, address/website from venue details
    venue = data.get("venue_name") or ""
    address = venue_data.get("address") or ""

    # Guess the venue timezone the wall-clock times belong to (online events have
    # no venue — their times ride the UTC default).
    venue_city = venue_data.get("city") or data.get("venue_city") or ""
    tz_name = "UTC" if online else _guess_timezone(country, venue_city, address)
    start = _parse_date(data.get("event_startdate"), data.get("event_starttime"))
    finish = _parse_date(data.get("event_enddate"), data.get("event_endtime"))
    # VEKN writes event_endtime "00:00:00" for an unset end time, and a handful of
    # events are simply inverted upstream (11025: 10:00 -> 08:30 same day). Either
    # way a finish before its start is not a finish — keep it unknown instead of
    # importing a negative duration. Events that genuinely ran past midnight carry
    # the next day in event_enddate (11096: 13th 22:00 -> 14th 06:00), so they
    # never reach this and need no date arithmetic from us.
    if finish and start and finish < start:
        finish = None
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
            proxies=proxies,
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
            proxies=proxies,
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


async def _adopt_same_event(tournament: Tournament, event_id: Any) -> Tournament | None:
    """Link a vekn-less local copy of this event to `event_id`, or return None.

    Without this, an event whose only local copy came in through the legacy-archon
    merge without a vekn id gets a SECOND copy created here — the #520 duplicate
    class, and (because the orphaned copy keeps retrying an event-create that
    vekn.net rejects as already existing) the standing hourly push error.

    Refuses to guess. Name+start-day is only evidence of identity where it is
    UNIQUE in the corpus, so any other same-name/same-day copy already carrying a
    vekn id proves the key doesn't discriminate here (legacy placeholder names
    like "Imported VTES Event" cover dozens of distinct events per day) and the
    match is abandoned. What remains must be a single vekn-less candidate.
    """
    if tournament.start is None:
        return None
    candidates = await find_same_event_tournaments(
        tournament.name, tournament.start, country=tournament.country
    )
    taken = [c for c in candidates if c.external_ids.get("vekn")]
    if taken:
        logger.warning(
            f"VEKN event {event_id} '{tournament.name}': same-day copies "
            f"{[c.uid for c in taken]} already hold vekn ids — name+day is not "
            f"unique here, not adopting"
        )
        return None
    if len(candidates) != 1:
        if candidates:
            logger.warning(
                f"VEKN event {event_id} '{tournament.name}': {len(candidates)} "
                f"vekn-less same-day copies {[c.uid for c in candidates]} — "
                f"ambiguous, not adopting"
            )
        return None

    adopted = candidates[0]
    # Adopting hands the row to the caller's existing-row paths, and the round-less
    # one treats vekn.net as authoritative for players/standings. Safe when the copy
    # has rounds (rich-guard → metadata only) or no players (nothing to lose); a
    # registration list with no rounds yet would be overwritten, so leave it alone.
    if adopted.players and not adopted.rounds:
        logger.warning(
            f"VEKN event {event_id} '{tournament.name}': same-day copy {adopted.uid} "
            f"holds {len(adopted.players)} registered players but no rounds — not "
            f"adopting (would overwrite the registration list); resolve manually"
        )
        return None
    adopted.external_ids["vekn"] = str(event_id)
    adopted.modified = datetime.now(UTC)
    async with get_connection() as conn:
        bd = await save_tournament(adopted, conn=conn)
    broadcast_precomputed(bd)
    logger.info(
        f"VEKN event {event_id} adopted by existing tournament {adopted.uid} "
        f"'{adopted.name}' (was vekn-less) instead of creating a duplicate"
    )
    return adopted


async def sync_all_tournaments(client: VEKNAPIClient) -> dict[str, int]:
    """Sync all VEKN tournaments.

    Returns stats: {created, adopted, updated, unchanged, errors, skipped, total}.
    """
    logger.info("Starting VEKN tournament sync")
    stats = {
        "created": 0,
        "adopted": 0,
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
            if existing_ref is None:
                existing_ref = await _adopt_same_event(tournament, event_id)
                if existing_ref is not None:
                    stats["adopted"] += 1
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
                    if existing.rounds or not tournament.players:
                        # Tournament was run in-app (it has per-round play data). VEKN.net
                        # is NOT authoritative for its rounds/finals/standings/players/
                        # winner/state — only for descriptive event metadata. Refresh
                        # metadata only and NEVER overwrite the play data (doing so would
                        # silently wipe rounds and corrupt standings/ratings). Gate on
                        # `rounds` only: a re-imported VEKN event now carries a
                        # reconstructed finals object, but VEKN stays authoritative for
                        # it (a final implies prelim rounds, so this never misses in-app).
                        #
                        # Round-less events take this path too when VEKN reports NO
                        # players: authority follows content, and an empty calendar entry
                        # has nothing to be authoritative about. Without this, the branch
                        # below rebuilt the row from that empty entry — resetting an
                        # in-app event still taking registrations to Planned and
                        # discarding everyone registered so far, every sync, until its
                        # first round started.
                        # `proxies` refreshes here like the rest of the descriptive
                        # metadata: the calendar entry is write-once (no update
                        # endpoint), so vekn.net is where the flag is changed and the
                        # app config field is frozen once an event has a vekn id.
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
                            or existing.proxies != tournament.proxies
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
                                proxies=tournament.proxies,
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
                            or existing.proxies != tournament.proxies
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
                                proxies=tournament.proxies,
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
                                # Local-only bookkeeping: not derivable from VEKN
                                twda_status=existing.twda_status,
                                # League membership is archon-only knowledge —
                                # dropping it here nulled the league link on
                                # every rebuild of a round-less event.
                                league_uid=existing.league_uid,
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
        f"{stats['adopted']} adopted, {stats['updated']} updated, "
        f"{stats['unchanged']} unchanged, {stats['skipped']} skipped, "
        f"{stats['errors']} errors, {stats['total']} total"
    )

    # One grouped query, after the fact: the adoption guards above decline every
    # ambiguous case, so duplicates still accumulate silently otherwise. Stays loud
    # until an operator resolves them (scripts/dedup_tournaments.py).
    for group in await find_duplicate_tournament_groups():
        logger.warning(
            f"Duplicate live tournaments: '{group['name']}' on {group['day']} — "
            f"{group['uids']} ({group['with_vekn']} with a vekn id)"
        )
    return stats
