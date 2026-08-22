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
from .schemas import NDJSON, ref, responds, streams

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_token)])

_BATCH = 250
_VISIBLE = '"api" IS NOT NULL AND deleted_at IS NULL'
_BY_MODIFIED = "(modified_at, uid) > (%s::timestamp, %s)"


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
        f'SELECT modified_at::text, uid, "api"::text FROM objects '
        f"WHERE type = %s AND {match} AND ({{keyset}}) "
        "ORDER BY modified_at, uid LIMIT %s",
        (obj_type, *values),
        _BY_MODIFIED,
        2,
    )


@router.get("/tournaments", openapi_extra=streams("Tournament", "tournament"))
async def stream_tournaments(
    country: str | None = None,
    format: str | None = None,
    state: str | None = None,
    start_after: str | None = None,
    start_before: str | None = None,
) -> StreamingResponse:
    """Every tournament, oldest change first.

    `start_after` / `start_before` compare ISO-8601 wall-clock text, so a bare
    date bounds at its midnight.
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


@router.get("/tournaments/{code_or_uid}", openapi_extra=responds(ref("Tournament")))
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
async def stream_leagues() -> StreamingResponse:
    """Every league, oldest change first."""
    return _ndjson(
        _data_lines(
            ObjectType.LEAGUE,
            await _read_at(),
            _object_batches(ObjectType.LEAGUE, [], []),
        )
    )


@router.get("/leagues/{uid}", openapi_extra=responds(ref("League")))
async def get_league(uid: str) -> Response:
    row = await _one(
        f'SELECT "api"::text FROM objects WHERE uid = %s AND type = %s AND {_VISIBLE}',
        (uid, ObjectType.LEAGUE),
    )
    if not row:
        raise HTTPException(404, "League not found")
    return _json(row[0])


@router.get("/users/{vekn_id}", openapi_extra=responds(ref("User")))
async def get_user(vekn_id: str) -> Response:
    """A member by VEKN ID. Nobody else is addressable: a user without one has no
    `api` row at all."""
    row = await _one(
        f'SELECT "api"::text FROM objects WHERE type = %s AND {_VISIBLE} '
        "AND \"full\"->>'vekn_id' = %s",
        (ObjectType.USER, vekn_id),
    )
    if not row:
        raise HTTPException(404, "User not found")
    return _json(row[0])


@router.get("/decks", openapi_extra=streams("DeckObject", "deck"))
async def stream_decks(tournament: str | None = None) -> StreamingResponse:
    """Every published deck, oldest change first."""
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


@router.get("/rankings", openapi_extra=streams("User", "user"))
async def stream_rankings(
    category: RatingCategory = RatingCategory.CONSTRUCTED_ONLINE,
    country: str | None = None,
) -> StreamingResponse:
    """Every rated member, highest total first. For a top-N, read N lines and
    close the connection."""
    total = f"(\"api\"->'{category.value}'->>'total')::int"
    clauses = [_VISIBLE, f"{total} IS NOT NULL"]
    values: list[str] = []
    if country:
        clauses.append("\"api\"->>'country' = %s")
        values.append(country)
    sql = (
        f'SELECT {total}, uid, "api"::text FROM objects '
        f"WHERE type = %s AND {' AND '.join(clauses)} AND ({{keyset}}) "
        f"ORDER BY {total} DESC, uid DESC LIMIT %s"
    )
    return _ndjson(
        _data_lines(
            ObjectType.USER,
            await _read_at(),
            _batches(
                sql,
                (ObjectType.USER, *values),
                f"({total}, uid) < (%s, %s)",
                2,
            ),
        )
    )


@router.get(
    "/community-links",
    openapi_extra=streams("CommunityLinkEntry", "community_link"),
)
async def stream_community_links() -> StreamingResponse:
    """Every member's community links, one line per link. A link a moderator hid
    is withheld — the app's own clients filter those client-side, and a third
    party has no way to know it should."""
    sql = (
        "SELECT o.uid, link.idx, jsonb_build_object("
        "'vekn_id', o.\"api\"->>'vekn_id', "
        "'country', coalesce(link.value->>'country', o.\"api\"->>'country'), "
        "'link', link.value)::text "
        "FROM objects o CROSS JOIN LATERAL jsonb_array_elements("
        "coalesce(o.\"api\"->'community_links', '[]'::jsonb)) "
        "WITH ORDINALITY AS link(value, idx) "
        'WHERE o.type = %s AND o."api" IS NOT NULL AND o.deleted_at IS NULL '
        "AND coalesce(link.value->'moderation'->>'status', '') <> 'hidden' "
        "AND ({keyset}) ORDER BY o.uid, link.idx LIMIT %s"
    )
    return _ndjson(
        _data_lines(
            "community_link",
            await _read_at(),
            _batches(sql, (ObjectType.USER,), "(o.uid, link.idx) > (%s, %s)", 2),
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
    """The whole `api` corpus as the periodically-generated snapshot file."""
    path = get_snapshot_path("api")
    if path is None:
        raise HTTPException(503, "Export not generated yet")
    return FileResponse(
        path, media_type="application/gzip", filename="archon-api.jsonl.gz"
    )
