"""iCal calendar feed endpoint for tournament subscriptions."""

import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, Response

from ..db import get_user_by_calendar_token
from ..geonames import get_countries_on_continent
from ..models import Tournament, TournamentState

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


def _escape_ical(text: str) -> str:
    """Escape text for iCal format."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _format_dt(dt: datetime | None) -> str:
    """Format datetime to iCal DTSTART/DTEND value."""
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _tournament_to_vevent(t: Tournament, now_str: str) -> str:
    """Convert a tournament to an iCal VEVENT string."""
    dtstart = _format_dt(t.start)
    if not dtstart:
        return ""

    # End time: finish or start + 8h default
    if t.finish:
        dtend = _format_dt(t.finish)
    else:
        start_dt = t.start if t.start.tzinfo else t.start.replace(tzinfo=UTC)
        dtend = (start_dt + timedelta(hours=8)).strftime("%Y%m%dT%H%M%SZ")

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

    # Location
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
) -> bool:
    """Check if tournament matches the user's personal agenda criteria."""
    # User organizes it (any state)
    if t.organizers_uids and user_uid in t.organizers_uids:
        return True
    # User participates (any state)
    if t.players and any(p.user_uid == user_uid for p in t.players):
        return True
    # For non-finished only:
    if t.state == TournamentState.FINISHED:
        return False
    # Same country
    if user_country and t.country == user_country:
        return True
    # Online
    if t.online:
        return True
    # NC/CC on same continent
    if continent_countries and t.country in continent_countries:
        if t.rank in ("National Championship", "Continental Championship"):
            return True
    return False


@router.get("/tournaments.ics")
async def tournament_calendar(
    token: str | None = Query(None, description="Personal calendar token"),
    country: str | None = Query(None, description="Filter by country ISO code"),
    online: bool = Query(True, description="Include online events"),
) -> Response:
    """Generate an iCal feed of upcoming tournaments.

    If token is provided, returns a personalized agenda feed.
    Otherwise, returns a public feed filtered by country/online params.
    """
    from ..db import get_connection
    from ..db import decode_json

    now = datetime.now(UTC)
    now_str = now.strftime("%Y%m%dT%H%M%SZ")
    # Include tournaments from last 7 days
    cutoff = (now - timedelta(days=7)).isoformat()

    # Resolve user for personal feed
    user = None
    if token:
        user = await get_user_by_calendar_token(token)

    # Query tournaments from DB
    async with get_connection() as conn:
        result = await conn.execute(
            """
            SELECT data FROM tournaments
            WHERE data->>'deleted_at' IS NULL
              AND data->>'state' != 'Finished'
              AND (data->>'start' IS NULL OR (data->>'start')::timestamp >= %s::timestamp)
            ORDER BY data->>'start' ASC
            """,
            (cutoff,),
        )
        rows = await result.fetchall()

    tournaments = [decode_json(row[0], Tournament) for row in rows]

    # Filter
    if user and user.country:
        continent_countries = get_countries_on_continent(user.country)
        tournaments = [
            t for t in tournaments
            if _matches_agenda(t, user.uid, user.country, continent_countries)
        ]
    else:
        # Public filtering
        filtered = []
        for t in tournaments:
            if country and t.country != country.upper() and not t.online:
                continue
            if not online and t.online:
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
    if user:
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
