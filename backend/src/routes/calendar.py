"""iCal calendar feed endpoint for tournament subscriptions."""

import json
import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from archon_engine import PyEngine
from fastapi import APIRouter, HTTPException, Query, Response

from ..db import get_user_by_calendar_token
from ..geonames import get_countries_on_continent
from ..models import Tournament

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

_engine = PyEngine()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Personal feeds only; other feeds stay upcoming-only.
FINISHED_WINDOW_DAYS = 90


def _escape_ical(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _as_utc(dt: datetime, tz_name: str) -> datetime:
    if dt.tzinfo is None:
        try:
            dt = dt.replace(tzinfo=ZoneInfo(tz_name or "UTC"))
        except (ZoneInfoNotFoundError, ValueError):
            dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _format_dt(dt: datetime | None, tz_name: str = "UTC") -> str:
    if not dt:
        return ""
    return _as_utc(dt, tz_name).strftime("%Y%m%dT%H%M%SZ")


def _tournament_to_vevent(t: Tournament, now_str: str) -> str:
    dtstart = _format_dt(t.start, t.timezone)
    if not dtstart:
        return ""

    if t.finish:
        dtend = _format_dt(t.finish, t.timezone)
    else:
        assert t.start is not None
        dtend = (_as_utc(t.start, t.timezone) + timedelta(hours=8)).strftime(
            "%Y%m%dT%H%M%SZ"
        )

    parts = []
    if t.format:
        parts.append(f"{t.format} tournament")
    if t.rank:
        parts.append(f"({t.rank})")
    if t.venue:
        parts.append(f"\n{t.venue}")
    url = (
        f"{FRONTEND_URL}/t/{t.event_code}"
        if t.event_code
        else f"{FRONTEND_URL}/tournaments/{t.uid}"
    )
    description = _escape_ical(" ".join(parts) if parts else t.name)

    # venue/address render even in anonymous feeds: public-projection fields.
    if t.online:
        location = "Online"
    elif t.venue or t.address:
        loc_parts = [p for p in [t.venue, t.address] if p]
        location = _escape_ical(", ".join(loc_parts))
    else:
        location = ""

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


def _agenda_filter(
    tournaments: list[Tournament],
    user_uid: str,
    user_country: str | None,
    continent_countries: list[str],
    include_online: bool,
    hidden: list[str],
    added: list[str],
) -> list[Tournament]:
    viewer = {
        "uid": user_uid,
        "country": user_country,
        "continent_countries": continent_countries,
        "hidden": hidden,
        "added": added,
    }
    events = [
        {
            "uid": t.uid,
            "state": t.state,
            "country": t.country,
            "online": t.online,
            "rank": t.rank,
            "organizers_uids": t.organizers_uids,
            "playing": any(p.user_uid == user_uid for p in t.players),
        }
        for t in tournaments
    ]
    on = json.loads(
        _engine.agenda_filter(json.dumps(viewer), json.dumps(events), include_online)
    )
    return [t for t, keep in zip(tournaments, on, strict=True) if keep]


@router.get("/tournaments/{uid}.ics")
async def tournament_event_ics(uid: str) -> Response:
    """Public like the feeds: the same venue/address projection exception applies."""
    from ..db import get_tournament_by_uid

    t = await get_tournament_by_uid(uid)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    now_str = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    vevent = _tournament_to_vevent(t, now_str)
    if not vevent:
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
    country: str | None = Query(
        None, description="Filter by comma-separated country ISO codes"
    ),
    online: bool = Query(True, description="Include online events"),
    format: str | None = Query(None, description="Filter by format"),
    league: str | None = Query(None, description="Only events of this league uid"),
) -> Response:
    """iCal feed: league's events if `league`, else a personal agenda if `token`
    (own events always included, recently-finished ones stay for
    FINISHED_WINDOW_DAYS), else a public feed filtered by country/online/format."""
    from ..db import decode_json, get_connection

    countries = {c.strip().upper() for c in (country or "").split(",") if c.strip()}
    now = datetime.now(UTC)
    now_str = now.strftime("%Y%m%dT%H%M%SZ")
    cutoff = (now - timedelta(days=7)).isoformat()
    finished_cutoff = (now - timedelta(days=FINISHED_WINDOW_DAYS)).isoformat()

    # Resolve user for personal feed (league feeds are public — no token needed)
    user = None
    if token and not league:
        user = await get_user_by_calendar_token(token)

    query = """
        SELECT "full", "full"->>'start' FROM objects
        WHERE type = 'tournament' AND deleted_at IS NULL
          AND "full"->>'state' <> 'Finished'
          AND ("full"->>'start' IS NULL OR (
            "full"->>'start' >= %s AND ("full"->>'start')::timestamp >= %s::timestamp
          ))
    """
    params: tuple = (cutoff[:10], cutoff)
    if user is not None:
        query += """
        UNION ALL
        SELECT "full", "full"->>'start' FROM objects
        WHERE type = 'tournament' AND deleted_at IS NULL
          AND "full"->>'state' = 'Finished'
          AND COALESCE("full"->>'finish', "full"->>'start', "full"->>'modified') >= %s
          AND COALESCE("full"->>'finish', "full"->>'start', "full"->>'modified')::timestamp
              >= %s::timestamp
        """
        params += (finished_cutoff[:10], finished_cutoff)
    async with get_connection() as conn:
        result = await conn.execute(query + " ORDER BY 2 ASC", params)
        rows = await result.fetchall()

    tournaments = [decode_json(row[0], Tournament) for row in rows]

    # Filter
    if league:
        tournaments = [t for t in tournaments if t.league_uid == league]
    elif user and user.country:
        # Finished events arrive only within FINISHED_WINDOW_DAYS (bounded by
        # the SQL above), so the engine's own-event branches need no date check.
        tournaments = _agenda_filter(
            tournaments,
            user.uid,
            user.country,
            get_countries_on_continent(user.country),
            online,
            user.agenda_hidden or [],
            user.agenda_added or [],
        )
    else:
        # Public filtering
        filtered = []
        for t in tournaments:
            if countries and t.country not in countries and not t.online:
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
    elif countries:
        cal_name = f"VEKN Tournaments ({', '.join(sorted(countries))})"

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
