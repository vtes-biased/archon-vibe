import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import uuid7

import msgspec
from archon_engine import PyEngine

from .broadcast import broadcast_precomputed
from .data.timezones import CITY_TZ_OVERRIDES, COUNTRY_TIMEZONE
from .db import (
    decode_json,
    find_duplicate_tournament_groups,
    find_same_event_tournaments,
    find_vekn_absence_candidates,
    get_connection,
    get_tournament_by_external_id,
    resolve_event_code,
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
from .vekn_api import PLACEHOLDER_VENUE_ID, VEKNAPIClient

logger = logging.getLogger(__name__)
_engine = PyEngine()

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
    9: (TournamentFormat.Storyline, TournamentRank.BASIC),  # Storyline
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
    location = f"{venue_city} {address}".lower()
    for cc, city, tz in CITY_TZ_OVERRIDES:
        if cc == country and city.lower() in location:
            return tz
    return COUNTRY_TIMEZONE.get(country, "UTC")


def _parse_rounds(raw: Any) -> int:
    """VEKN's "rounds" field is like "3R+F" — leading integer is the prelim
    round count; "+F" ignored (finals tracked separately). Non-numeric -> 0."""
    m = re.match(r"\s*(\d+)", str(raw))
    return int(m.group(1)) if m else 0


def _parse_date(date_str: str | None, time_str: str | None = None) -> datetime | None:
    """Returns a NAIVE wall-clock datetime — do not convert to UTC, or
    paired-timezone readers will double-shift it."""
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
    """Map a VEKN event (+ optional venue_data from /venue/<id>) to a Tournament."""
    event_id = data.get("event_id")
    if not event_id:
        return None

    venue_data = venue_data or {}

    event_type = int(data.get("eventtype_id", 0) or 0)
    fmt, rank = EVENT_TYPE_MAP.get(
        event_type, (TournamentFormat.Standard, TournamentRank.BASIC)
    )

    name = data.get("event_name") or f"VEKN Event {event_id}"
    country = data.get("venue_country") or None

    online = str(data.get("event_isonline", "0")) == "1"

    # Championship ranks forbid proxies by rule; wins over a mis-set proxies_allowed=1.
    proxies = (
        str(data.get("proxies_allowed", "0")) == "1" and rank == TournamentRank.BASIC
    )

    venue = data.get("venue_name") or ""
    address = venue_data.get("address") or ""

    venue_city = venue_data.get("city") or data.get("venue_city") or ""
    tz_name = "UTC" if online else _guess_timezone(country, venue_city, address)
    start = _parse_date(data.get("event_startdate"), data.get("event_starttime"))
    finish = _parse_date(data.get("event_enddate"), data.get("event_endtime"))
    # VEKN sometimes writes an unset end time as "00:00:00" or inverts start/end;
    # treat finish < start as unknown, not a negative duration.
    if finish and start and finish < start:
        finish = None
    if address and venue_data.get("city"):
        address += f", {venue_data['city']}"
    elif not address:
        address = data.get("venue_city") or ""
    venue_url = venue_data.get("website") or ""

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

    organizer_vekn = str(data.get("organizer_veknid") or "")
    organizer_user = users_by_vekn_id.get(organizer_vekn)
    organizers_uids = [organizer_user.uid] if organizer_user else []

    max_rounds = _parse_rounds(data.get("rounds"))

    vekn_players = data.get("players", [])
    now = datetime.now(UTC)

    if vekn_players:
        state = TournamentState.FINISHED
        players: list[Player] = []
        standings: list[Standing] = []
        winner_uid = ""
        finalists: list[tuple[str, int, float]] = []  # (user_uid, pos, vpf)

        for vp_data in vekn_players:
            vekn_id = str(vp_data.get("veknid") or "")
            user = users_by_vekn_id.get(vekn_id)
            if not user:
                continue

            # `pos` on a dq'd or withdrawn row is the field size, not a placement,
            # so in a small field reading it as one crowns that player a finalist.
            disqualified = str(vp_data.get("dq") or "0") == "1"
            pos_is_field_size = disqualified or str(vp_data.get("wd") or "0") == "1"
            # pos 1..5 is final placement; pos == "1" is the tournament winner.
            prelim_gw = int(vp_data.get("gw", 0) or 0)
            pos = str(vp_data.get("pos") or "")
            is_finalist = not pos_is_field_size and pos in ("1", "2", "3", "4", "5")
            vp_prelim = float(vp_data.get("vp", 0) or 0)
            vp_finals = float(vp_data.get("vpf", 0) or 0)
            tp = int(vp_data.get("tp", 0) or 0)
            toss = int(vp_data.get("tie", 0) or 0)
            if disqualified:
                prelim_gw, vp_prelim, vp_finals, tp, toss = 0, 0.0, 0.0, 0, 0
            if is_finalist and pos == "1":
                winner_uid = user.uid
            if is_finalist:
                finalists.append((user.uid, int(pos), vp_finals))

            # result aggregates prelim+finals; standings stay prelim-only (the
            # finals object below carries the rest).
            players.append(
                Player(
                    user_uid=user.uid,
                    state=PlayerState.DISQUALIFIED
                    if disqualified
                    else PlayerState.FINISHED,
                    payment_status=PaymentStatus.PAID,
                    toss=toss,
                    result=Score(
                        gw=prelim_gw + (1 if is_finalist and pos == "1" else 0),
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
                    disqualified=disqualified,
                )
            )

        if not players:
            return None  # All players unknown

        # Reconstructed only when vpf>0 (final played). No VEKN seating exists:
        # seed_order is synthetic/display-only, tp=0 so league RTP/GP stays at prelim.
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

        # Sorted through the engine, whose terminal tiebreak is what keeps tied rows
        # off VEKN's API order — which varies across syncs and would spuriously trip
        # the equality check below.
        standings = msgspec.json.decode(
            _engine.sort_standings(msgspec.json.encode(standings).decode()),
            type=list[Standing],
        )

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
            # From vekn.net already — stamped so the push batch never re-uploads it.
            vekn_pushed_at=now,
        )
    else:
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
    """Adopts a vekn-less local copy instead of creating a duplicate. Matches
    only when name+start-day is unique in the corpus; ambiguous cases return None."""
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
    # A TWDA reconstruction has exactly this shape — winner-only roster, no
    # rounds — so the guard below would decline it and mint a duplicate. Adopt
    # instead: the full VEKN result set is strictly richer.
    if adopted.players and not adopted.rounds and not adopted.external_ids.get("twda"):
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


async def _record_vekn_absence(probed: dict[str, bool]) -> int:
    """Stamp or clear `vekn_event_absent_at` from the scan's per-id verdict."""
    absent = [event_id for event_id, answers in probed.items() if not answers]
    now = datetime.now(UTC)
    moved = 0

    for candidate in await find_vekn_absence_candidates(absent):
        answers = probed.get(candidate.external_ids.get("vekn", ""))
        # No verdict this run — transient, or above the scan's stop. Never "gone".
        if answers is None:
            continue
        flagged = candidate.vekn_event_absent_at is not None
        if answers and not flagged:
            continue
        if flagged and not answers:
            continue  # still gone: keep the instant it was first confirmed
        stamp = None if answers else now

        async with tournament_transaction(candidate.uid) as (existing, tx_conn):
            if existing is None:  # hard-deleted between the read and the lock
                continue
            updated = msgspec.structs.replace(
                existing, modified=now, vekn_event_absent_at=stamp
            )
            bd = await save_tournament(updated, conn=tx_conn)
        broadcast_precomputed(bd)
        moved += 1

    return moved


async def sync_all_tournaments(client: VEKNAPIClient) -> dict[str, int]:
    """Returns stats: {created, adopted, updated, unchanged, errors, skipped,
    absent, total}."""
    logger.info("Starting VEKN tournament sync")
    stats = {
        "created": 0,
        "adopted": 0,
        "updated": 0,
        "unchanged": 0,
        "errors": 0,
        "skipped": 0,
        "absent": 0,
        "total": 0,
    }

    users_by_vekn_id = await _build_users_by_vekn_id()
    logger.info(f"Loaded {len(users_by_vekn_id)} users by VEKN ID")

    venue_cache: dict[str, dict[str, str]] = {}

    probed: dict[str, bool] = {}
    async for event_data in client.fetch_all_events(probed=probed):
        stats["total"] += 1
        event_id = event_data.get("event_id", "?")

        try:
            venue_id = str(event_data.get("venue_id") or "")
            # An event we filed ourselves carries the placeholder venue, which
            # answers for no place: drop it so the app's own location stands.
            placeholder_venue = venue_id == str(PLACEHOLDER_VENUE_ID)
            if placeholder_venue:
                venue_id = ""
                event_data = {
                    **event_data,
                    "venue_name": "",
                    "venue_country": "",
                    "venue_city": "",
                }
            if venue_id and venue_id not in venue_cache:
                venue_cache[venue_id] = await client.fetch_venue(venue_id)
            venue_data = venue_cache.get(venue_id, {})

            tournament = _map_vekn_to_tournament(
                event_data, users_by_vekn_id, venue_data
            )
            if not tournament:
                stats["skipped"] += 1
                continue

            # Unlocked lookup — re-verified under the transaction below.
            existing_ref = await get_tournament_by_external_id("vekn", str(event_id))
            if existing_ref is None:
                existing_ref = await _adopt_same_event(tournament, event_id)
                if existing_ref is not None:
                    stats["adopted"] += 1
            if existing_ref:
                bd = None
                # Locked re-read serializes this overwrite against a concurrent
                # /action commit, so live play data added mid-sync survives.
                async with tournament_transaction(existing_ref.uid) as (
                    existing,
                    tx_conn,
                ):
                    existing = existing or existing_ref  # hard-deleted between reads
                    if placeholder_venue:
                        tournament = msgspec.structs.replace(
                            tournament,
                            country=existing.country,
                            timezone=existing.timezone,
                            venue=existing.venue,
                            venue_url=existing.venue_url,
                            address=existing.address,
                            map_url=existing.map_url,
                        )
                    merged_organizers = list(
                        dict.fromkeys(
                            existing.organizers_uids + tournament.organizers_uids
                        )
                    )
                    if existing.rounds or not tournament.players:
                        # Authority follows content: metadata-only refresh once local
                        # rounds exist, or the incoming event has no players to speak for.
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
                        # No local play data: VEKN is authoritative for everything,
                        # including players/standings/winner.
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
                            # Also compares play data, so a VEKN-side score correction
                            # is picked up and legacy folded imports self-heal.
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
                                # Merged, not replaced: the incoming map holds
                                # only `vekn`, and a replace drops the `twda`
                                # key the archive links a round-less row by.
                                external_ids={
                                    **existing.external_ids,
                                    **tournament.external_ids,
                                },
                                organizers_uids=merged_organizers,
                                max_rounds=tournament.max_rounds,
                                players=tournament.players,
                                winner=tournament.winner,
                                standings=tournament.standings,
                                finals=tournament.finals,
                                vekn_pushed_at=tournament.vekn_pushed_at,
                                vekn_event_absent_at=existing.vekn_event_absent_at,
                                # A fresh Tournament's default_factory code would
                                # break an already-printed QR.
                                checkin_code=existing.checkin_code,
                                # Written once by contract: a rebuild that let it
                                # default would orphan every published short link.
                                event_code=existing.event_code,
                                twda_status=existing.twda_status,  # not derivable from VEKN
                                # archon-only knowledge — dropping it nulls the league
                                # link on every rebuild of a round-less event.
                                league_uid=existing.league_uid,
                            )
                            bd = await save_tournament(tournament, conn=tx_conn)
                            stats["updated"] += 1
                        else:
                            stats["unchanged"] += 1
                if bd is not None:
                    broadcast_precomputed(bd)
            else:
                async with get_connection() as conn:
                    tournament.event_code = await resolve_event_code(tournament, conn)
                    bd = await save_tournament(tournament, conn=conn)
                broadcast_precomputed(bd)
                stats["created"] += 1

        except Exception as e:
            logger.error(f"Error syncing VEKN event {event_id}: {e}")
            stats["errors"] += 1

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

    stats["absent"] = await _record_vekn_absence(probed)

    logger.info(
        f"VEKN tournament sync completed: {stats['created']} created, "
        f"{stats['adopted']} adopted, {stats['updated']} updated, "
        f"{stats['unchanged']} unchanged, {stats['skipped']} skipped, "
        f"{stats['absent']} absence flags moved, "
        f"{stats['errors']} errors, {stats['total']} total"
    )

    # Reported, not repaired — the adoption guards above decline ambiguous cases,
    # so duplicates still accumulate; resolve with backend/scripts/dedup_tournaments.py.
    for group in await find_duplicate_tournament_groups():
        logger.warning(
            f"Duplicate live tournaments: '{group['name']}' on {group['day']} — "
            f"{group['uids']} ({group['with_vekn']} with a vekn id)"
        )
    return stats
