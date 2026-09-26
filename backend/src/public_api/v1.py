import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import datetime

from litestar import Request, Response, Router, get
from litestar.exceptions import HTTPException
from litestar.params import FromPath, FromQuery
from litestar.response import File, Stream

from ..models import ObjectType, RatingCategory, SanctionLevel
from ..snapshots import get_snapshot_path
from .auth import lookup_budget, stream_budget
from .db import get_connection
from .schemas import NDJSON, responds, streams

_BATCH = 250
_VISIBLE = '"api" IS NOT NULL AND deleted_at IS NULL'
_BY_UID = "uid < %s"


def _json(body: str) -> Response:
    return Response(body, media_type="application/json")


def _ndjson(lines: AsyncIterator[str]) -> Stream:
    return Stream(lines, media_type=NDJSON)


def _timestamp(value: str, label: str) -> str:
    try:
        datetime.fromisoformat(value)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid {label}") from err
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
        f"WHERE type = '{obj_type}' AND {match} AND ({{keyset}}) "
        "ORDER BY uid DESC LIMIT %s",
        tuple(values),
        _BY_UID,
        1,
    )


@get(
    "/tournaments",
    summary="Tournaments",
    guards=[stream_budget],
    opt={"responses": streams("Tournament", "tournament")},
)
async def list_tournaments(
    country: FromQuery[str | None] = None,
    start_after: FromQuery[str | None] = None,
    start_before: FromQuery[str | None] = None,
) -> Stream:
    """Every tournament, newest first.

    `country` is an ISO 3166-1 alpha-2 code.

    `start_after` and `start_before` are ISO-8601 dates or datetimes carrying no
    timezone. Each tournament is compared in its own local time, so
    `start_after=2026-01-01` means the first of January wherever the event is
    held. A bare date bounds at midnight.
    """
    filters: list[str] = []
    values: list[str] = []
    if country:
        filters.append("\"full\"->>'country' = %s")
        values.append(country)
    if start_after:
        filters.append("\"full\"->>'start' >= %s")
        values.append(_timestamp(start_after, "start_after"))
    if start_before:
        filters.append("\"full\"->>'start' <= %s")
        values.append(_timestamp(start_before, "start_before"))
    return _ndjson(
        _data_lines(
            ObjectType.TOURNAMENT,
            await _read_at(),
            _object_batches(ObjectType.TOURNAMENT, filters, values),
        )
    )


@get(
    "/tournaments/{code_or_uid:str}",
    guards=[lookup_budget],
    summary="A tournament",
    opt={"responses": responds("Tournament")},
)
async def get_tournament(code_or_uid: FromPath[str]) -> Response:
    """A tournament by its short event code (case-insensitive) or its uid."""
    row = await _one(
        f"SELECT \"api\"::text FROM objects WHERE type = 'tournament' AND {_VISIBLE} "
        "AND (uid = %s OR (lower(\"full\"->>'event_code') = lower(%s) "
        "AND coalesce(\"full\"->>'event_code', '') <> ''))",
        (code_or_uid, code_or_uid),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return _json(row[0])


@get(
    "/leagues",
    summary="Leagues",
    guards=[stream_budget],
    opt={"responses": streams("League", "league")},
)
async def list_leagues() -> Stream:
    """Every league, newest first."""
    return _ndjson(
        _data_lines(
            ObjectType.LEAGUE,
            await _read_at(),
            _object_batches(ObjectType.LEAGUE, [], []),
        )
    )


@get(
    "/leagues/{uid:str}",
    guards=[lookup_budget],
    summary="A league",
    opt={"responses": responds("League")},
)
async def get_league(uid: FromPath[str]) -> Response:
    row = await _one(
        f'SELECT "api"::text FROM objects WHERE uid = %s AND type = %s AND {_VISIBLE}',
        (uid, ObjectType.LEAGUE),
    )
    if not row:
        raise HTTPException(status_code=404, detail="League not found")
    return _json(row[0])


@get(
    "/users",
    summary="Members",
    guards=[stream_budget],
    opt={"responses": streams("User", "user")},
)
async def list_users(
    country: FromQuery[str | None] = None,
    category: FromQuery[RatingCategory | None] = None,
    tournament: FromQuery[str | None] = None,
) -> Stream:
    """Every member, newest first.

    Each line carries the member's rating in all four categories, so a ranking
    is a sort away. `country` is an ISO 3166-1 alpha-2 code. `category` narrows
    to members carrying a rating in it.
    `tournament` is a tournament uid and narrows to the members who played in
    it, so a result set costs one call rather than one call per player.
    """
    filters: list[str] = []
    values: list[str] = []
    if country:
        filters.append("\"full\"->>'country' = %s")
        values.append(country)
    if category:
        filters.append(f"\"full\"->'{category.value}'->>'total' IS NOT NULL")
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


_WITH_SANCTIONS = (
    "\"api\" || jsonb_build_object('sanctions', coalesce(("
    "SELECT jsonb_agg(jsonb_build_object("
    "'level', s.\"full\"->'level', 'expires_at', s.\"full\"->'expires_at'"
    ") ORDER BY s.uid) FROM objects s "
    "WHERE s.type = 'sanction' AND s.\"full\"->>'user_uid' = objects.uid "
    "AND s.deleted_at IS NULL AND s.\"full\"->>'lifted_at' IS NULL "
    f"AND s.\"full\"->>'level' IN ('{SanctionLevel.SUSPENSION}', "
    f"'{SanctionLevel.PROBATION}') "
    "AND (s.\"full\"->>'expires_at' IS NULL "
    "OR (s.\"full\"->>'expires_at')::timestamptz > now())"
    "), '[]'::jsonb))"
)


@get(
    "/users/{uid_or_vekn_id:str}",
    guards=[lookup_budget],
    summary="A member",
    opt={"responses": responds("UserLookup")},
)
async def get_user(uid_or_vekn_id: FromPath[str], request: Request) -> Response:
    """A member by uid or VEKN ID.

    A tournament's players, standings and winner carry uids, so this is how a
    result becomes a member.

    `sanctions` is answered to an app token only, never to a member's: the
    member's standing suspensions and probations, empty when there are none.
    """
    body = _WITH_SANCTIONS if request.state.app_token else '"api"'
    row = await _one(
        f"SELECT ({body})::text FROM objects WHERE type = 'user' AND {_VISIBLE} "
        "AND (uid = %s OR (\"full\"->>'vekn_id' = %s AND \"full\"->>'vekn_id' != ''))",
        (uid_or_vekn_id, uid_or_vekn_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return _json(row[0])


@get(
    "/decks",
    summary="Decks",
    guards=[stream_budget],
    opt={"responses": streams("DeckObject", "deck")},
)
async def list_decks(tournament: FromQuery[str | None] = None) -> Stream:
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


@get(
    "/community-links",
    summary="Community links",
    guards=[stream_budget],
    opt={"responses": streams("CommunityLinkEntry", "community_link")},
)
async def list_community_links() -> Stream:
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
        f"WHERE o.type = '{ObjectType.USER}' "
        "AND o.\"full\"->'community_links' <> '[]'::jsonb "
        'AND o."api" IS NOT NULL AND o.deleted_at IS NULL '
        "AND coalesce(link.value->>'moderation', '') <> 'hidden' "
        "AND ({keyset}) ORDER BY o.uid DESC, link.idx DESC LIMIT %s"
    )
    return _ndjson(
        _data_lines(
            "community_link",
            await _read_at(),
            _batches(sql, (), "(o.uid, link.idx) < (%s, %s)", 2),
        )
    )


@get(
    "/export",
    summary="The whole corpus",
    guards=[stream_budget],
    opt={
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
async def export() -> File:
    """The whole corpus as one gzipped JSON Lines file, rebuilt within 15 minutes of
    any change. One request instead of five, and the cheapest way to take everything."""
    path = get_snapshot_path("api")
    if path is None:
        raise HTTPException(status_code=503, detail="Export not generated yet")
    return File(path, media_type="application/gzip", filename="archon-api.jsonl.gz")


router = Router(
    "/v1",
    tags=["Public API"],
    route_handlers=[
        list_tournaments,
        get_tournament,
        list_leagues,
        get_league,
        list_users,
        get_user,
        list_decks,
        list_community_links,
        export,
    ],
)
