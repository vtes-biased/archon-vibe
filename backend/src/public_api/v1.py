import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse, StreamingResponse

from ..models import ObjectType, RatingCategory
from ..snapshots import get_snapshot_path
from .auth import require_api_token
from .db import get_connection
from .schemas import NDJSON, responds, streams

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_token)])

_BATCH = 250
_VISIBLE = '"api" IS NOT NULL AND deleted_at IS NULL'
_BY_UID = "uid < %s"


def _json(body: str) -> Response:
    return Response(content=body, media_type="application/json")


def _ndjson(lines: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(lines, media_type=NDJSON)


def _timestamp(value: str, label: str) -> str:
    try:
        datetime.fromisoformat(value)
    except ValueError as err:
        raise HTTPException(400, f"Invalid {label}") from err
    return value


async def _fetch(sql: str, params: Sequence) -> list[tuple]:
    # Shielded: a reader hanging up mid-query costs the pool the connection.
    async def run() -> list[tuple]:
        async with get_connection() as conn:
            cur = await conn.execute(sql, params)
            return await cur.fetchall()

    return await asyncio.shield(run())


async def _one(sql: str, params: Sequence) -> tuple | None:
    rows = await _fetch(sql, params)
    return rows[0] if rows else None


async def _read_at() -> str:
    row = await _one("SELECT now()::timestamp", ())
    return row[0].isoformat()


async def _batches(
    sql: str, params: Sequence, keyset: str, keys: int
) -> AsyncIterator[list[tuple]]:
    """`sql` carries a `{keyset}` slot and ends with `LIMIT %s`; its first `keys`
    columns are the ordering key."""
    clause, bound = "TRUE", ()
    while True:
        rows = await _fetch(sql.replace("{keyset}", clause), (*params, *bound, _BATCH))
        if not rows:
            return
        yield rows
        if len(rows) < _BATCH:
            return
        clause, bound = keyset, tuple(rows[-1][:keys])


def _header(generated_at: str) -> str:
    return json.dumps({"type": "header", "generated_at": generated_at}) + "\n"


def _eof(count: int) -> str:
    return json.dumps({"type": "eof", "count": count}) + "\n"


async def _data_lines(
    line_type: str, generated_at: str, batches: AsyncIterator[list[tuple]]
) -> AsyncIterator[str]:
    yield _header(generated_at)
    count = 0
    async for rows in batches:
        count += len(rows)
        yield "".join(f'{{"type":"{line_type}","data":{row[-1]}}}\n' for row in rows)
    yield _eof(count)


def _object_batches(
    obj_type: str, filters: list[str], values: list[str]
) -> AsyncIterator[list[tuple]]:
    match = " AND ".join([_VISIBLE, *filters])
    return _batches(
        f'SELECT uid, "api"::text FROM objects '
        f"WHERE type = %s AND {match} AND ({{keyset}}) "
        "ORDER BY uid DESC LIMIT %s",
        (obj_type, *values),
        _BY_UID,
        1,
    )


@router.get("/tournaments", openapi_extra=streams("Tournament", "tournament"))
async def list_tournaments(
    country: str | None = None,
    format: str | None = None,
    state: str | None = None,
    start_after: str | None = None,
    start_before: str | None = None,
) -> StreamingResponse:
    """Every tournament, newest first.

    `country` is an ISO 3166-1 alpha-2 code. `format` is `Standard`, `Limited`
    or `V5`. `state` is `Planned`, `Registration`, `Waiting`, `Playing` or
    `Finished`.

    `start_after` and `start_before` are ISO-8601 dates or datetimes carrying no
    timezone. Each tournament is compared in its own local time, so
    `start_after=2026-01-01` means the first of January wherever the event is
    held. A bare date bounds at midnight.
    """
    filters: list[str] = []
    values: list[str] = []
    for field, value in (("country", country), ("format", format), ("state", state)):
        if value:
            filters.append(f"\"api\"->>'{field}' = %s")
            values.append(value)
    if start_after:
        filters.append("\"api\"->>'start' >= %s")
        values.append(_timestamp(start_after, "start_after"))
    if start_before:
        filters.append("\"api\"->>'start' <= %s")
        values.append(_timestamp(start_before, "start_before"))
    return _ndjson(
        _data_lines(
            ObjectType.TOURNAMENT,
            await _read_at(),
            _object_batches(ObjectType.TOURNAMENT, filters, values),
        )
    )


@router.get("/tournaments/{code_or_uid}", openapi_extra=responds("Tournament"))
async def get_tournament(code_or_uid: str) -> Response:
    """A tournament by its short event code (case-insensitive) or its uid."""
    row = await _one(
        f'SELECT "api"::text FROM objects WHERE type = %s AND {_VISIBLE} '
        "AND (uid = %s OR lower(\"full\"->>'event_code') = lower(%s))",
        (ObjectType.TOURNAMENT, code_or_uid, code_or_uid),
    )
    if not row:
        raise HTTPException(404, "Tournament not found")
    return _json(row[0])


@router.get("/leagues", openapi_extra=streams("League", "league"))
async def list_leagues() -> StreamingResponse:
    """Every league, newest first."""
    return _ndjson(
        _data_lines(
            ObjectType.LEAGUE,
            await _read_at(),
            _object_batches(ObjectType.LEAGUE, [], []),
        )
    )


@router.get("/leagues/{uid}", openapi_extra=responds("League"))
async def get_league(uid: str) -> Response:
    row = await _one(
        f'SELECT "api"::text FROM objects WHERE uid = %s AND type = %s AND {_VISIBLE}',
        (uid, ObjectType.LEAGUE),
    )
    if not row:
        raise HTTPException(404, "League not found")
    return _json(row[0])


@router.get("/users", openapi_extra=streams("User", "user"))
async def list_users(
    country: str | None = None,
    category: RatingCategory | None = None,
    tournament: str | None = None,
) -> StreamingResponse:
    """Every member, newest first.

    Each line carries the member's rating in all four categories, so a ranking
    is a sort away. `country` is an ISO 3166-1 alpha-2 code. `category` narrows
    to members carrying a rating in it, which is a small fraction of the whole.
    `tournament` is a tournament uid and narrows to the members who played in
    it, so a result set costs one call rather than one call per player.
    """
    filters: list[str] = []
    values: list[str] = []
    if country:
        filters.append("\"api\"->>'country' = %s")
        values.append(country)
    if category:
        filters.append(f"\"api\"->'{category.value}'->>'total' IS NOT NULL")
    if tournament:
        filters.append(
            "uid IN (SELECT jsonb_array_elements(t.\"api\"->'players')->>'user_uid' "
            "FROM objects t WHERE t.uid = %s AND t.type = 'tournament')"
        )
        values.append(tournament)
    return _ndjson(
        _data_lines(
            ObjectType.USER,
            await _read_at(),
            _object_batches(ObjectType.USER, filters, values),
        )
    )


@router.get("/users/{uid_or_vekn_id}", openapi_extra=responds("User"))
async def get_user(uid_or_vekn_id: str) -> Response:
    """A member by uid or VEKN ID.

    A tournament's players, standings and winner carry uids, so this is how a
    result becomes a member.
    """
    row = await _one(
        f'SELECT "api"::text FROM objects WHERE type = %s AND {_VISIBLE} '
        "AND (uid = %s OR \"full\"->>'vekn_id' = %s)",
        (ObjectType.USER, uid_or_vekn_id, uid_or_vekn_id),
    )
    if not row:
        raise HTTPException(404, "User not found")
    return _json(row[0])


@router.get("/decks", openapi_extra=streams("DeckObject", "deck"))
async def list_decks(tournament: str | None = None) -> StreamingResponse:
    """Every published deck, newest first. `tournament` is a tournament uid."""
    filters: list[str] = []
    values: list[str] = []
    if tournament:
        filters.append("\"full\"->>'tournament_uid' = %s")
        values.append(tournament)
    return _ndjson(
        _data_lines(
            ObjectType.DECK,
            await _read_at(),
            _object_batches(ObjectType.DECK, filters, values),
        )
    )


@router.get(
    "/community-links",
    openapi_extra=streams("CommunityLinkEntry", "community_link"),
)
async def list_community_links() -> StreamingResponse:
    """Every member's community links, one line per link.

    Lines for one member arrive together; their order within a member carries no
    meaning. A link a moderator has hidden is not served.
    """
    sql = (
        "SELECT o.uid, link.idx, jsonb_build_object("
        "'vekn_id', o.\"api\"->>'vekn_id', "
        "'link', link.value || jsonb_build_object('country', "
        "coalesce(link.value->>'country', o.\"api\"->>'country')))::text "
        "FROM objects o CROSS JOIN LATERAL jsonb_array_elements("
        "coalesce(o.\"api\"->'community_links', '[]'::jsonb)) "
        "WITH ORDINALITY AS link(value, idx) "
        'WHERE o.type = %s AND o."api" IS NOT NULL AND o.deleted_at IS NULL '
        "AND coalesce(link.value->>'moderation', '') <> 'hidden' "
        "AND ({keyset}) ORDER BY o.uid DESC, link.idx DESC LIMIT %s"
    )
    return _ndjson(
        _data_lines(
            "community_link",
            await _read_at(),
            _batches(sql, (ObjectType.USER,), "(o.uid, link.idx) < (%s, %s)", 2),
        )
    )


@router.get(
    "/export",
    openapi_extra={
        "responses": {
            "200": {
                "description": "The same JSON Lines, gzipped, whole corpus",
                "content": {
                    "application/gzip": {
                        "schema": {"type": "string", "format": "binary"}
                    }
                },
            }
        }
    },
)
async def export() -> FileResponse:
    """The whole corpus as one gzipped JSON Lines file, never more than an hour
    old. One request instead of five, and the cheapest way to take everything."""
    path = get_snapshot_path("api")
    if path is None:
        raise HTTPException(503, "Export not generated yet")
    return FileResponse(
        path, media_type="application/gzip", filename="archon-api.jsonl.gz"
    )
