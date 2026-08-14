"""iCal calendar feed endpoint for tournament subscriptions."""

import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Response

from ..db import get_user_by_calendar_token
from ..geonames import get_countries_on_continent
from ..models import ObjectType, Tournament, TournamentState

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# How long a finished event stays in a PERSONAL feed (keyed on finish).
# Subscribed calendars reconcile on every poll: an event leaving the feed is
# DELETED from the subscriber's calendar, so a player's own history must not
# vanish the moment the event finishes. Discovery/league/public feeds stay
# upcoming-only.
FINISHED_WINDOW_DAYS = 90


def _escape_ical(text: str) -> str:
    """Escape text for iCal format."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _as_utc(dt: datetime, tz_name: str) -> datetime:
    """Anchor a naive wall-clock datetime in the tournament's timezone, then UTC.

    Tournament.start/finish are stored naive (wall-clock in Tournament.timezone).
    """
    if dt.tzinfo is None:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name or "UTC"))
        except (ZoneInfoNotFoundError, ValueError):
            dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _format_dt(dt: datetime | None, tz_name: str = "UTC") -> str:
    """Format datetime to iCal DTSTART/DTEND value."""
    if not dt:
        return ""
    return _as_utc(dt, tz_name).strftime("%Y%m%dT%H%M%SZ")


def _tournament_to_vevent(t: Tournament, now_str: str) -> str:
    """Convert a tournament to an iCal VEVENT string."""
    dtstart = _format_dt(t.start, t.timezone)
    if not dtstart:
        return ""

    # End time: finish or start + 8h default
    if t.finish:
        dtend = _format_dt(t.finish, t.timezone)
    else:
        assert t.start is not None
        dtend = (_as_utc(t.start, t.timezone) + timedelta(hours=8)).strftime(
            "%Y%m%dT%H%M%SZ"
        )

    # Build description
    parts = []
    if t.format:
        parts.append(f"{t.format} tournament")
    if t.rank:
        parts.append(f"({t.rank})")
    if t.venue:
        parts.append(f"\n{t.venue}")
    url = f"{FRONTEND_URL}/tournaments/{t.uid}"
    description = _escape_ical(" ".join(parts) if parts else t.name)

    # Location: venue/address render even in anonymous no-token feeds — they are
    # public-projection fields (the .ics is an advertising artifact mirroring
    # vekn.net's public event calendar; granularity is the organizer's
    # data-entry choice). See ARCHITECTURE.md "Calendar System".
    if t.online:
        location = "Online"
    elif t.venue or t.address:
        loc_parts = [p for p in [t.venue, t.address] if p]
        location = _escape_ical(", ".join(loc_parts))
    else:
        location = ""

    # Categories
    categories = [t.format] if t.format else []
    if t.rank:
        categories.append(t.rank)

    lines = [
        "BEGIN:VEVENT",
        f"UID:{t.uid}@archon.vekn.net",
        f"DTSTAMP:{now_str}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{_escape_ical(t.name)}",
        f"DESCRIPTION:{description}",
        f"URL;VALUE=URI:{url}",
    ]
    if location:
        lines.append(f"LOCATION:{location}")
    if categories:
        lines.append(f"CATEGORIES:{','.join(categories)}")
    lines.append("STATUS:CONFIRMED")
    lines.append("END:VEVENT")
    return "\r\n".join(lines)


def _matches_agenda(
    t: Tournament,
    user_uid: str,
    user_country: str | None,
    continent_countries: list[str],
    include_online: bool,
) -> bool:
    """Check if tournament matches the user's personal agenda criteria.

    include_online gates only the DISCOVERY branch below — events the user
    organizes or plays in always stay in their feed.
    """
    # User organizes it (any state; the feed SQL bounds Finished events to
    # the FINISHED_WINDOW_DAYS window before they reach this function)
    if t.organizers_uids and user_uid in t.organizers_uids:
        return True
    # User participates (any state, same window)
    if t.players and any(p.user_uid == user_uid for p in t.players):
        return True
    # Discovery below is upcoming-only: finished events never match by
    # geography/online — only the own-event branches above keep them.
    if t.state == TournamentState.FINISHED:
        return False
    # Discovery: online events are opt-out via ?online=false
    if t.online:
        return include_online
    # Same country
    if user_country and t.country == user_country:
        return True
    # NC/CC on same continent
    if continent_countries and t.country in continent_countries:
        if t.rank in ("National Championship", "Continental Championship"):
            return True
    return False


@router.get("/tournaments/{uid}.ics")
async def tournament_event_ics(uid: str) -> Response:
    """Single-VEVENT .ics download for one tournament (per-event add-to-calendar).

    Public like the feeds — and like them it renders venue/address (the
    deliberate projection exception documented above).
    """
    from ..db import get_tournament_by_uid

    t = await get_tournament_by_uid(uid)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    now_str = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    vevent = _tournament_to_vevent(t, now_str)
    if not vevent:  # no start date — nothing to put on a calendar
        raise HTTPException(status_code=404, detail="Tournament has no start date")

    ical_content = (
        "\r\n".join(
            [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//VEKN//Archon//EN",
                "CALSCALE:GREGORIAN",
                "METHOD:PUBLISH",
                vevent,
                "END:VCALENDAR",
            ]
        )
        + "\r\n"
    )
    return Response(
        content=ical_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{t.uid}.ics"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/tournaments.ics")
async def tournament_calendar(
    token: str | None = Query(None, description="Personal calendar token"),
    country: str | None = Query(None, description="Filter by country ISO code"),
    online: bool = Query(True, description="Include online events"),
    format: str | None = Query(None, description="Filter by format"),
    league: str | None = Query(None, description="Only events of this league uid"),
) -> Response:
    """Generate an iCal feed of upcoming tournaments.

    If league is provided, returns that league's events (public data).
    Else if token is provided, returns a personalized agenda feed (online
    discovery honors ?online=false; own events always included, and
    recently-finished ones stay for FINISHED_WINDOW_DAYS).
    Otherwise, returns a public feed filtered by country/online/format params.
    """
    from ..db import decode_json, get_connection

    now = datetime.now(UTC)
    now_str = now.strftime("%Y%m%dT%H%M%SZ")
    # Include tournaments from last 7 days
    cutoff = (now - timedelta(days=7)).isoformat()
    finished_cutoff = (now - timedelta(days=FINISHED_WINDOW_DAYS)).isoformat()

    # Resolve user for personal feed (league feeds are public — no token needed)
    user = None
    if token and not league:
        user = await get_user_by_calendar_token(token)

    # Query tournaments from DB. Finished events are excluded except for
    # personal feeds, which keep them within FINISHED_WINDOW_DAYS (keyed on
    # finish, falling back to start — some imported Finished rows carry no
    # finish); _matches_agenda then restricts them to own events.
    async with get_connection() as conn:
        result = await conn.execute(
            """
            SELECT "full" FROM objects
            WHERE type = %s
              AND deleted_at IS NULL
              AND (
                ("full"->>'state' != 'Finished'
                  AND ("full"->>'start' IS NULL OR ("full"->>'start')::timestamp >= %s::timestamp))
                OR (%s AND "full"->>'state' = 'Finished'
                  AND (COALESCE("full"->>'finish', "full"->>'start'))::timestamp >= %s::timestamp)
              )
            ORDER BY "full"->>'start' ASC
            """,
            (ObjectType.TOURNAMENT, cutoff, user is not None, finished_cutoff),
        )
        rows = await result.fetchall()

    tournaments = [decode_json(row[0], Tournament) for row in rows]

    # Filter
    if league:
        tournaments = [t for t in tournaments if t.league_uid == league]
    elif user and user.country:
        continent_countries = get_countries_on_continent(user.country)
        tournaments = [
            t
            for t in tournaments
            if _matches_agenda(t, user.uid, user.country, continent_countries, online)
        ]
    else:
        # Public filtering
        filtered = []
        for t in tournaments:
            if country and t.country != country.upper() and not t.online:
                continue
            if not online and t.online:
                continue
            if format and t.format != format:
                continue
            filtered.append(t)
        tournaments = filtered

    # Generate iCal
    vevents = []
    for t in tournaments:
        vevent = _tournament_to_vevent(t, now_str)
        if vevent:
            vevents.append(vevent)

    cal_name = "Archon Tournaments"
    if league:
        from ..db import get_league_by_uid

        league_obj = await get_league_by_uid(league)
        cal_name = f"VEKN League — {league_obj.name}" if league_obj else "VEKN League"
    elif user:
        cal_name = "My VEKN Tournaments"
    elif country:
        cal_name = f"VEKN Tournaments ({country.upper()})"

    ical_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//VEKN//Archon//EN",
        f"X-WR-CALNAME:{cal_name}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for v in vevents:
        ical_lines.append(v)
    ical_lines.append("END:VCALENDAR")

    ical_content = "\r\n".join(ical_lines) + "\r\n"

    return Response(
        content=ical_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": 'inline; filename="archon-tournaments.ics"',
            "Cache-Control": "public, max-age=3600",
        },
    )
