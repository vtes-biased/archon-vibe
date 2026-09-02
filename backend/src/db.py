"""Database connection and initialization."""

import asyncio
import hashlib
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from importlib import resources
from typing import NamedTuple

import msgspec
import psycopg
from archon_engine import PyEngine
from psycopg_pool import AsyncConnectionPool

from .geonames import country_key
from .models import (
    AuthMethod,
    DeckObject,
    League,
    ObjectType,
    Promo,
    PromoLedgerEntry,
    PromoLedgerKind,
    Role,
    Sanction,
    Tournament,
    User,
)

_engine = PyEngine()


@dataclass(slots=True)
class BroadcastData:
    """Pre-computed broadcast data returned by save functions. No DB re-read needed."""

    obj_type: ObjectType
    uid: str
    pub_json: str | None
    mem_json: str | None
    full_json: str
    country: str | None = None
    org_uids: list[str] | None = None
    obj_user_uid: str | None = None
    # The tournament a sanction/deck belongs to (None for tournaments/users/
    # leagues). Lets a tournament-scoped SSE connection match related objects.
    tournament_uid: str | None = None
    # DB-clock modified_at, emitted as the SSE envelope `ts` for cursor advance —
    # not the payload's app-clock `modified`, a different format and value space.
    modified_at: str | None = None


DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://archon:archon_dev_password@localhost:5433/archon",
)

# Bounds PG backend RSS (~5-10MB each, one async worker). Lowered via env on
# the memory-constrained prod box sharing a cluster with legacy archon.
POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "20"))

_pool: AsyncConnectionPool | None = None


class _ActiveTx(NamedTuple):
    """The connection an open `tournament_transaction` owns, plus its owner task."""

    conn: "psycopg.AsyncConnection"
    task: "asyncio.Task | None"


# Ambient transaction connection; see `_acquire`/`get_connection`. Never start a
# DB-touching task while set — `_acquire` raises if reached from another task.
_tx_conn: ContextVar["_ActiveTx | None"] = ContextVar("_tx_conn", default=None)


async def init_db() -> None:
    global _pool

    _pool = AsyncConnectionPool(
        conninfo=DB_URL,
        min_size=2,
        max_size=POOL_MAX_SIZE,
        open=False,
        kwargs={"autocommit": True},
    )
    await _pool.open()

    # Apply the schema (idempotent; see schema.sql). Executed as one
    # multi-statement script — no params, so PostgreSQL parses it server-side.
    schema_sql = (resources.files(__package__) / "schema.sql").read_text(
        encoding="utf-8"
    )
    async with _pool.connection() as conn:
        await conn.execute(schema_sql)


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterator[psycopg.AsyncConnection]:
    """Check a connection out of the pool — always pools, not ambient-aware.

    Writers that must commit independently of an open transaction (e.g.
    go-online's per-user VEKN allocation loop) use this directly; reads that
    should join an open transaction go through `_acquire`.
    """
    if not _pool:
        raise RuntimeError("Database not initialized")
    async with _pool.connection() as conn:
        yield conn


@asynccontextmanager
async def batch_read_connection(
    statement_timeout_ms: int = 120_000,
) -> AsyncIterator[psycopg.AsyncConnection]:
    """Pooled connection with a relaxed statement_timeout for full-corpus batch
    jobs (snapshot gen, VEKN push) that outlast the 30s request guard.

    Autocommit pool has no reset hook, so the caller must RESET on release;
    `SET` can't bind-param, hence the `int()` interpolation.
    """
    async with get_connection() as conn:
        await conn.execute(f"SET statement_timeout = {int(statement_timeout_ms)}")
        try:
            yield conn
        finally:
            # Swallow reset failure on an already-broken conn (pool recycles it) so
            # the original error is never masked.
            try:
                await conn.execute("RESET statement_timeout")
            except Exception:
                pass


@asynccontextmanager
async def _acquire(
    conn: psycopg.AsyncConnection | None = None,
) -> AsyncIterator[psycopg.AsyncConnection]:
    """Resolve a connection for a READ: explicit `conn` → ambient transaction
    connection → pool. Reusing the ambient connection means one action never
    checks out a second connection while holding its FOR UPDATE lock.

    Reached from a different task, it raises — DB work spawned inside a
    transaction (`create_task`/`gather`) would race the shared connection.

    For WRITES inside a transaction, pass `conn=tx_conn` explicitly to join it;
    never rely on this ambient path for a write, so the transaction boundary
    stays visible at the call site.
    """
    if conn is not None:
        yield conn
        return
    active = _tx_conn.get()
    if active is not None:
        if active.task is not None and asyncio.current_task() is not active.task:
            raise RuntimeError(
                "ambient transaction connection reached from a different task — "
                "do not run DB work in an asyncio task spawned inside a "
                "tournament_transaction (it would race the locked connection)"
            )
        yield active.conn  # reuse; the transaction owns this connection's lifecycle
        return
    async with get_connection() as c:
        yield c


@asynccontextmanager
async def tournament_transaction(
    uid: str,
) -> AsyncIterator[tuple[Tournament | None, psycopg.AsyncConnection]]:
    """Lock a tournament row FOR UPDATE within a transaction; yields
    (tournament, connection). Commits on normal exit, rolls back on exception.

    While open, `_tx_conn` is set so every DB helper called on this task
    transparently shares `conn` — see `get_connection`.
    """
    if not _pool:
        raise RuntimeError("Database not initialized")
    async with _pool.connection() as conn:
        token = _tx_conn.set(_ActiveTx(conn, asyncio.current_task()))
        try:
            async with conn.transaction():
                result = await conn.execute(
                    # type predicate: a non-tournament uid must read as absent, not
                    # decode a foreign row as Tournament and get overwritten in place.
                    "SELECT \"full\" FROM objects WHERE uid = %s AND type = 'tournament' FOR UPDATE",
                    (uid,),
                )
                row = await result.fetchone()
                tournament = decode_json(row[0], Tournament) if row else None
                yield tournament, conn
        finally:
            _tx_conn.reset(token)


# JSON encoder/decoder
_encoder = msgspec.json.Encoder()


# Bump on a wire-shape change that does NOT ride a frontend DB_VERSION bump —
# flips every client's access-version fingerprint into exactly one resync.
DATA_SCHEMA_VERSION = 1

# Roles that branch in base_data_level / entitled_level / access_levels — the only
# roles whose presence changes a viewer's entitlement (so only these enter the fp).
_OVERLAY_ROLES = (Role.IC, Role.NC)


def base_data_level(viewer: User | None) -> str:
    """The viewer's base projection level BEFORE any personal overlay.

    Single source of truth (main._viewer_level delegates here and the fingerprint
    reuses it): IC → full; any vekn member → member; otherwise public.
    """
    if not viewer:
        return "public"
    if Role.IC in viewer.roles:
        return "full"
    if viewer.vekn_id:
        return "member"
    return "public"


async def organizer_tournament_uids(user_uid: str) -> list[str]:
    """Sorted uids of non-deleted tournaments this user organizes (GIN-indexed)."""
    async with get_connection() as conn:
        rows = await (
            await conn.execute(
                # Literal type (not a %s param) so the planner can prove the partial
                # index's WHERE predicate; @> (not ?) so its jsonb_path_ops opclass applies.
                "SELECT uid FROM objects WHERE type = 'tournament' "
                "AND (\"full\"->'organizers_uids') @> %s::jsonb AND deleted_at IS NULL",
                (_encoder.encode([user_uid]).decode(),),
            )
        ).fetchall()
    return sorted(r[0] for r in rows)


async def compute_access_version(viewer: User | None) -> str:
    """Opaque per-user entitlement fingerprint for the SSE connect handshake.

    Hashes the wire-shape version, base level, overlay-granting roles, an NC's
    country, and organized-tournament uids. Backend-only and opaque — the client
    stores and echoes it without parsing, so the inputs stay server-evolvable.
    """
    level = base_data_level(viewer)
    roles = sorted(r.value for r in _OVERLAY_ROLES if viewer and r in viewer.roles)
    # country enters the fp ONLY for officials — it scopes their same-country overlay.
    # Must stay in lockstep with entitled_level's same-country branch (broadcast.py).
    official = bool(viewer and Role.NC in viewer.roles)
    country = viewer.country if official else None
    # The org-set only changes a MEMBER's entitlement (IC already sees full
    # everywhere; public/anon have no overlay) — so only members pay the query.
    org_uids = (
        await organizer_tournament_uids(viewer.uid)
        if viewer and level == "member"
        else []
    )
    payload = _encoder.encode([DATA_SCHEMA_VERSION, level, roles, country, org_uids])
    return hashlib.sha256(payload).hexdigest()[:16]


@cache
def _decoder_for(type_: type) -> msgspec.json.Decoder:
    """Cached per-type msgspec Decoder (Decoders are reusable and meant to be shared)."""
    return msgspec.json.Decoder(type_)


def encode_json(obj: msgspec.Struct) -> str:
    return _encoder.encode(obj).decode("utf-8")


def decode_json[T](data: str | dict, type_: type[T]) -> T:
    decoder = _decoder_for(type_)
    if isinstance(data, dict):
        data = _encoder.encode(data).decode("utf-8")
    return decoder.decode(data)


from .access_levels import (  # noqa: E402
    compute_api,
    compute_full,
    compute_member,
    compute_public,
)


async def get_decks_for_tournament(
    tournament_uid: str, conn: psycopg.AsyncConnection | None = None
) -> list[DeckObject]:
    """Get all DeckObjects for a tournament (uses idx_objects_deck_tournament)."""
    async with _acquire(conn) as conn:
        result = await conn.execute(
            """SELECT "full"::text FROM objects WHERE type = 'deck' AND "full"->>'tournament_uid' = %s""",
            (tournament_uid,),
        )
        rows = await result.fetchall()
    return [msgspec.json.decode(row[0].encode(), type=DeckObject) for row in rows]


async def save_object(
    obj_type: ObjectType,
    uid: str,
    full_data: dict,
    *,
    conn: psycopg.AsyncConnection | None = None,
    deleted_at: str | None = None,
) -> BroadcastData:
    """Save an object to the unified objects table, computing and upserting all
    four access-level projections.
    """
    pub = compute_public(obj_type, full_data)
    mem = compute_member(obj_type, full_data)
    api = compute_api(obj_type, full_data)
    full = compute_full(obj_type, full_data)

    pub_json = _encoder.encode(pub).decode("utf-8") if pub is not None else None
    mem_json = _encoder.encode(mem).decode("utf-8") if mem is not None else None
    api_json = _encoder.encode(api).decode("utf-8") if api is not None else None
    full_json = _encoder.encode(full).decode("utf-8")

    # calendar_token lives outside the JSONB projections and must never be
    # broadcast. A NULL write here COALESCEs — only clear_calendar_token() drops it.
    cal_token = full_data.get("calendar_token") if obj_type == ObjectType.USER else None

    query = """
        INSERT INTO objects (uid, type, deleted_at, "public", "member", "api", "full", calendar_token)
        VALUES (%s, %s, %s::timestamp, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (uid) DO UPDATE SET
            type = EXCLUDED.type,
            deleted_at = EXCLUDED.deleted_at,
            "public" = EXCLUDED."public",
            "member" = EXCLUDED."member",
            "api" = EXCLUDED."api",
            "full" = EXCLUDED."full",
            calendar_token = COALESCE(EXCLUDED.calendar_token, objects.calendar_token)
        RETURNING modified_at
    """
    params = (
        uid,
        obj_type,
        deleted_at,
        pub_json,
        mem_json,
        api_json,
        full_json,
        cal_token,
    )

    if conn:
        row = await (await conn.execute(query, params)).fetchone()
    else:
        async with get_connection() as c:
            row = await (await c.execute(query, params)).fetchone()
    # BEFORE trigger sets modified_at = CURRENT_TIMESTAMP, so RETURNING reflects
    # the authoritative DB-clock value used by the `since`/sync_complete cursor.
    modified_at = row[0].isoformat() if row and row[0] else None

    return BroadcastData(
        obj_type=obj_type,
        uid=uid,
        pub_json=pub_json,
        mem_json=mem_json,
        full_json=full_json,
        country=full_data.get("country"),
        org_uids=full_data.get("organizers_uids"),
        obj_user_uid=full_data.get("user_uid"),
        tournament_uid=full_data.get("tournament_uid"),
        modified_at=modified_at,
    )


async def save_object_from_model(
    obj_type: ObjectType,
    obj: msgspec.Struct,
    *,
    conn: psycopg.AsyncConnection | None = None,
) -> BroadcastData:
    """Save a msgspec model to the objects table."""
    full_data = msgspec.to_builtins(obj)
    deleted_at = full_data.get("deleted_at")
    if deleted_at is not None and not isinstance(deleted_at, str):
        deleted_at = (
            deleted_at.isoformat()
            if hasattr(deleted_at, "isoformat")
            else str(deleted_at)
        )
    return await save_object(
        obj_type, obj.uid, full_data, conn=conn, deleted_at=deleted_at
    )  # ty: ignore[unresolved-attribute]


async def delete_object(
    uid: str, *, conn: psycopg.AsyncConnection | None = None
) -> None:
    """Hard delete an object and any side-table binary asset keyed by its uid.

    Avatars/banners have no FK cascade, so a bare DELETE would orphan bytes.
    A uid matches at most one side table (v7 UUID), so both deletes are
    cheap no-ops when the object has no asset.
    """

    async def _run(c: psycopg.AsyncConnection) -> None:
        # Explicit transaction: autocommit pool, so a crash mid-delete would
        # permanently orphan asset bytes. Nests as a savepoint if already in one.
        async with c.transaction():
            await c.execute("DELETE FROM objects WHERE uid = %s", (uid,))
            await c.execute("DELETE FROM avatars WHERE user_uid = %s", (uid,))
            await c.execute("DELETE FROM banners WHERE tournament_uid = %s", (uid,))
            await c.execute(
                "DELETE FROM push_subscriptions WHERE user_uid = %s", (uid,)
            )
            await c.execute("DELETE FROM nda_records WHERE user_uid = %s", (uid,))

    if conn:
        await _run(conn)
    else:
        async with get_connection() as c:
            await _run(c)


def _level_col(level: str) -> str:
    """Map access level name to quoted SQL column name.

    Fail-closed: an unknown level raises KeyError instead of silently serving
    the "full" projection — a mistyped level must never leak fields.
    """
    return {"public": '"public"', "member": '"member"', "full": '"full"'}[level]


# Constrains get_object_full's read to the stored type — else a uid of the
# wrong type could decode as this type and get written back, silently transmuting it.
_OBJECT_TYPES: dict[type, ObjectType] = {
    User: ObjectType.USER,
    Sanction: ObjectType.SANCTION,
    Tournament: ObjectType.TOURNAMENT,
    League: ObjectType.LEAGUE,
    DeckObject: ObjectType.DECK,
    Promo: ObjectType.PROMO,
}


async def get_object_full[T](
    uid: str, type_: type[T], conn: psycopg.AsyncConnection | None = None
) -> T | None:
    """Get an object from the objects table, decoded into a typed model."""
    obj_type = _OBJECT_TYPES[type_]  # KeyError on an unmapped class = fail-closed
    async with _acquire(conn) as conn:
        result = await conn.execute(
            'SELECT "full" FROM objects WHERE uid = %s AND type = %s',
            (uid, obj_type),
        )
        row = await result.fetchone()
        if row and row[0] is not None:
            return decode_json(row[0], type_)
        return None


async def stream_objects_new(
    obj_type: str | None = None,
    level: str = "full",
    since: str | None = None,
    batch_size: int = 1000,
) -> AsyncIterator[tuple[list[str], str]]:
    """Stream pre-serialized JSON in keyset-paginated batches for SSE catch-up
    and the full-corpus rating recompute.

    Releases the pooled connection before each yield, so a slow client never
    pins a pool slot and the app heap holds at most one batch. `ORDER BY
    (modified_at, uid)` is load-bearing — the `since` cursor must advance
    monotonically; keyset continuation stays tie-safe across batch seams.

    Yields (batch_of_raw_json_strings, max_modified_at_in_batch) per batch.
    """
    if not _pool:
        raise RuntimeError("Database not initialized")

    col = _level_col(level)
    last_modified: str | None = None
    last_uid: str | None = None

    # Shielded: a reader hanging up mid-query costs the pool the connection.
    async def _fetch_batch(sql: str, params: list) -> list:
        async with _pool.connection() as c:
            return await (await c.execute(sql, (*params, batch_size))).fetchall()

    while True:
        conditions = [f"{col} IS NOT NULL"]
        params: list = []
        if obj_type:
            conditions.append("type = %s")
            params.append(obj_type)
        if last_modified is not None:
            # Keyset continuation: tie-safe past the previous batch's last row.
            conditions.append("(modified_at, uid) > (%s::timestamp, %s)")
            params += [last_modified, last_uid]
        elif since:
            conditions.append("modified_at > %s::timestamp")
            params.append(since)
        where = " AND ".join(conditions)
        sql = (
            f"SELECT {col}::text, modified_at, uid FROM objects "  # ty: ignore[invalid-argument-type]
            f"WHERE {where} ORDER BY modified_at ASC, uid ASC LIMIT %s"
        )
        rows = await asyncio.shield(_fetch_batch(sql, params))

        if not rows:
            break
        yield [r[0] for r in rows], rows[-1][1].isoformat()
        if len(rows) < batch_size:
            break
        last_modified = rows[-1][1].isoformat()
        last_uid = rows[-1][2]


async def stream_objects_snapshot(
    conn: psycopg.AsyncConnection,
    batch_size: int = 150,
) -> AsyncIterator[list[tuple[str, str | None, str | None, str | None, str | None]]]:
    """Stream the whole live corpus once, unordered — every type, all four
    access levels per row.

    `conn` is caller-owned; drive this under `contextlib.aclosing` (or fully
    drain it), or an early exit leaves the cursor/transaction open until GC
    re-lends the connection. Plan checks must EXPLAIN the DECLARE, not the
    bare SELECT — cursor_tuple_fraction costs it differently.

    Yields batches of (type, public, member, api, full) in `snapshots._LEVELS`
    order — the two must move together, or a level's rows land in another
    level's file. A None level means the row has no such projection.
    """
    sql = (
        'SELECT type, "public"::text, "member"::text, "api"::text, "full"::text '
        "FROM objects WHERE deleted_at IS NULL"
    )
    async with conn.transaction():
        async with conn.cursor(name="snap_all") as cur:
            await cur.execute(sql)
            while True:
                rows = await cur.fetchmany(batch_size)
                if not rows:
                    break
                yield rows


async def purge_deleted_objects(days: int = 30) -> int:
    """Hard-delete objects that were soft-deleted more than `days` ago."""
    if not _pool:
        raise RuntimeError("Database not initialized")
    async with _pool.connection() as conn:
        # Explicit transaction (autocommit pool): purge and asset cleanup commit
        # together, so a crash can't orphan bytes whose owning row is already gone.
        async with conn.transaction():
            result = await conn.execute(
                "DELETE FROM objects WHERE deleted_at < NOW() - make_interval(days => %s) "
                "RETURNING uid",
                (days,),
            )
            purged = [row[0] for row in await result.fetchall()]
            if purged:
                # Drop orphaned side-table assets (no FK cascade); see delete_object.
                await conn.execute(
                    "DELETE FROM avatars WHERE user_uid = ANY(%s)", (purged,)
                )
                await conn.execute(
                    "DELETE FROM banners WHERE tournament_uid = ANY(%s)", (purged,)
                )
                await conn.execute(
                    "DELETE FROM push_subscriptions WHERE user_uid = ANY(%s)", (purged,)
                )
                await conn.execute(
                    "DELETE FROM nda_records WHERE user_uid = ANY(%s)", (purged,)
                )
        return len(purged)


async def save_user(user: User) -> BroadcastData:
    return await save_object_from_model(ObjectType.USER, user)


async def get_user_by_uid(
    uid: str, conn: psycopg.AsyncConnection | None = None
) -> User | None:
    """Get a user by UID.

    Returns the "full" projection, which does NOT carry calendar_token (an
    owner-only secret kept in its own column). Read-modify-write still preserves
    the token because save_object COALESCEs it (see there) — loaders need not
    re-read it. Owner display reads it explicitly via get_calendar_token().
    """
    return await get_object_full(uid, User, conn=conn)


async def get_users_by_uids(uids: set[str]) -> dict[str, User]:
    """Batch-fetch users by uid (full projection). One query avoids N round-trips
    — up to 400 sequential ones in the post-finish rating recompute at a big
    event. Missing/null-full uids are simply absent from the map."""
    if not uids:
        return {}
    async with get_connection() as conn:
        result = await conn.execute(
            'SELECT "full" FROM objects '
            "WHERE type = 'user' AND uid = ANY(%s) AND \"full\" IS NOT NULL",
            (list(uids),),
        )
        rows = await result.fetchall()
    return {u.uid: u for u in (decode_json(row[0], User) for row in rows)}


async def soft_delete_user(uid: str) -> tuple[User, BroadcastData] | None:
    """Soft-delete a user by setting deleted_at. Returns (user, BroadcastData) for SSE."""
    user = await get_user_by_uid(uid)
    if not user:
        return None
    now = datetime.now(UTC)
    user.deleted_at = now
    user.modified = now
    bd = await save_user(user)
    return user, bd


async def get_user_by_contact_email(email: str) -> User | None:
    """Find a live user by contact_email (account-merge + door-dedup lookup).
    Skips soft-deleted rows — a merged/tombstoned duplicate must neither block a
    fresh create nor be a merge target. ORDER BY uid + LIMIT 1 gives a stable pick
    across legacy duplicate emails."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND LOWER("full"->>'contact_email') = LOWER(%s)
              AND deleted_at IS NULL ORDER BY uid LIMIT 1""",
            (email,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], User)
        return None


async def get_user_by_calendar_token(token: str) -> User | None:
    """Lookup user by calendar subscription token (dedicated column, owner secret).

    Skips soft-deleted users so a revoked/merged account's feed stops resolving.
    The returned User has no calendar_token set (stripped from "full"); the
    caller already holds the token and only needs the user identity.
    """
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND calendar_token = %s
              AND deleted_at IS NULL LIMIT 1""",
            (token,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], User)
        return None


async def get_calendar_token(uid: str) -> str | None:
    """Read a user's calendar_token (owner-only secret) from its dedicated column.

    Used to surface the token to the owner (e.g. /auth/me) without ever putting
    it in the broadcast "full" projection.
    """
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT calendar_token FROM objects WHERE uid = %s",
            (uid,),
        )
        row = await result.fetchone()
    return row[0] if row else None


async def clear_calendar_token(uid: str) -> None:
    """Explicitly clear a user's calendar_token.

    save_object COALESCEs the token (a NULL write preserves the existing value),
    so account surgery that orphans a record (strip/split VEKN) must clear the
    feed token here rather than by writing None through the User model.
    """
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE objects SET calendar_token = NULL WHERE uid = %s",
            (uid,),
        )


async def get_user_by_vekn_id(
    vekn_id: str, conn: psycopg.AsyncConnection | None = None
) -> User | None:
    async with _acquire(conn) as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND "full"->>'vekn_id' = %s LIMIT 1""",
            (vekn_id,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], User)
        return None


async def is_vekn_id_claimed(vekn_id: str) -> bool:
    """Check if a VEKN ID is claimed (has auth_methods linked)."""
    user = await get_user_by_vekn_id(vekn_id)
    if not user:
        return False
    auth_methods = await get_auth_methods_for_user(user.uid)
    return len(auth_methods) > 0


async def get_users_by_vekn_prefix(prefix: str) -> list[User]:
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND "full"->>'vekn_id' LIKE %s || '%%'""",
            (prefix,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], User) for row in rows]


async def get_users_with_vekn_prefix() -> list[User]:
    """Get all users with a non-empty vekn_prefix (in practice Princes and NCs,
    but the query filters on the prefix alone — no role predicate)."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user'
              AND "full"->>'vekn_prefix' IS NOT NULL
              AND "full"->>'vekn_prefix' != ''"""
        )
        rows = await result.fetchall()
        return [decode_json(row[0], User) for row in rows]


async def get_users_without_coopted_by() -> list[User]:
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user'
              AND "full"->>'coopted_by' IS NULL
              AND "full"->>'vekn_id' IS NOT NULL
              AND "full"->>'vekn_id' != ''"""
        )
        rows = await result.fetchall()
        return [decode_json(row[0], User) for row in rows]


async def allocate_next_vekn_id() -> str:
    """Atomically allocate the next available VEKN ID: first gap starting at
    1000000, guarded by an advisory lock against concurrent requests.
    """
    # Avoid leading zeros: VEKN IDs are 7 digits.
    min_vekn_id = 1000000

    if not _pool:
        raise RuntimeError("Database not initialized")
    async with _pool.connection() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(1)")

            result = await conn.execute(
                """
                WITH used_ids AS (
                    SELECT ("full"->>'vekn_id')::integer AS vekn_id
                    FROM objects
                    WHERE type = 'user'
                      AND "full"->>'vekn_id' IS NOT NULL
                      AND "full"->>'vekn_id' ~ '^[0-9]+$'
                      AND ("full"->>'vekn_id')::integer >= %s
                ),
                candidates AS (
                    SELECT generate_series(%s, COALESCE((SELECT MAX(vekn_id) FROM used_ids), %s) + 1) AS candidate
                )
                SELECT MIN(candidate) AS next_id
                FROM candidates
                WHERE candidate NOT IN (SELECT vekn_id FROM used_ids)
                """,
                (min_vekn_id, min_vekn_id, min_vekn_id),
            )
            row = await result.fetchone()
            return str(row[0]) if row and row[0] is not None else str(min_vekn_id)


async def insert_auth_method(auth_method: AuthMethod) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO auth_methods (uid, data) VALUES (%s, %s)",
            (auth_method.uid, encode_json(auth_method)),
        )


async def update_auth_method(auth_method: AuthMethod) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE auth_methods SET data = %s WHERE uid = %s",
            (encode_json(auth_method), auth_method.uid),
        )


async def get_auth_method_by_identifier(
    method_type: str,
    identifier: str,
    conn: psycopg.AsyncConnection | None = None,
) -> AuthMethod | None:
    async with _acquire(conn) as conn:
        result = await conn.execute(
            """
            SELECT data FROM auth_methods
            WHERE data->>'method_type' = %s AND data->>'identifier' = %s
            """,
            (method_type, identifier),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], AuthMethod)
        return None


async def get_auth_methods_for_user(user_uid: str) -> list[AuthMethod]:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM auth_methods WHERE data->>'user_uid' = %s",
            (user_uid,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], AuthMethod) for row in rows]


async def delete_auth_method(uid: str) -> None:
    async with get_connection() as conn:
        await conn.execute("DELETE FROM auth_methods WHERE uid = %s", (uid,))


async def save_sanction(sanction: Sanction) -> BroadcastData:
    return await save_object_from_model(ObjectType.SANCTION, sanction)


async def get_sanction_by_uid(uid: str) -> Sanction | None:
    return await get_object_full(uid, Sanction)


async def get_sanctions_for_user(
    user_uid: str, conn: psycopg.AsyncConnection | None = None
) -> list[Sanction]:
    async with _acquire(conn) as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'sanction' AND "full"->>'user_uid' = %s
            ORDER BY "full"->>'issued_at' DESC""",
            (user_uid,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Sanction) for row in rows]


async def get_sanctions_for_users(
    user_uids: list[str], conn: psycopg.AsyncConnection | None = None
) -> list[Sanction]:
    """Get all sanctions for a set of users in a single query.

    Batched replacement for a per-user fan-out loop, which matters when
    called while holding a row lock.
    """
    if not user_uids:
        return []
    async with _acquire(conn) as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'sanction' AND "full"->>'user_uid' = ANY(%s)""",
            (list(user_uids),),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Sanction) for row in rows]


async def get_sanctions_for_tournament(
    tournament_uid: str, conn: psycopg.AsyncConnection | None = None
) -> list[Sanction]:
    """Get all non-deleted sanctions for a tournament."""
    async with _acquire(conn) as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'sanction'
              AND "full"->>'tournament_uid' = %s
              AND "full"->>'deleted_at' IS NULL""",
            (tournament_uid,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Sanction) for row in rows]


async def get_expired_sanctions() -> list[Sanction]:
    """Get sanctions that should be auto-expired (>18 months, not permanent, not deleted)."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'sanction'
              AND "full"->>'deleted_at' IS NULL
              AND "full"->>'issued_at' IS NOT NULL
              AND ("full"->>'issued_at')::timestamp < NOW() - INTERVAL '18 months'
              AND NOT (
                  "full"->>'level' = 'suspension'
                  AND "full"->>'expires_at' IS NULL
              )"""
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Sanction) for row in rows]


async def get_sanctions_for_cleanup(days: int = 30) -> list[Sanction]:
    """Get soft-deleted sanctions older than N days for hard deletion."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'sanction'
              AND deleted_at IS NOT NULL
              AND deleted_at < NOW() - make_interval(days => %s)""",
            (days,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Sanction) for row in rows]


async def delete_sanction_hard(uid: str) -> None:
    await delete_object(uid)


async def save_tournament(
    tournament: Tournament, *, conn: psycopg.AsyncConnection
) -> BroadcastData:
    """Upsert a tournament. `conn` is REQUIRED — inside `tournament_transaction(uid)`
    for an existing row, so a concurrent `/action` commit can't be lost to a stale
    read-modify-write; or a plain `get_connection()` for a fresh create/bulk seed.
    """
    return await save_object_from_model(ObjectType.TOURNAMENT, tournament, conn=conn)


async def get_tournament_by_uid(
    uid: str, conn: psycopg.AsyncConnection | None = None
) -> Tournament | None:
    return await get_object_full(uid, Tournament, conn=conn)


async def get_tournament_public_projection(uid: str) -> dict | None:
    """Public-level projection of a tournament, as a raw dict.

    For the unauthenticated OG share-stub: type-filtered so a non-tournament uid
    can't leak another object's public projection through /tournaments/{uid}.
    """
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT \"public\" FROM objects WHERE uid = %s AND type = 'tournament'",
            (uid,),
        )
        row = await result.fetchone()
        if row and row[0] is not None:
            return row[0] if isinstance(row[0], dict) else msgspec.json.decode(row[0])
        return None


async def get_league_public_projection(uid: str) -> tuple[dict, int] | None:
    """Public-level projection of a league + its live tournament count.

    For the unauthenticated OG share-stub: type-filtered so a non-league uid
    can't leak another object's public projection through /leagues/{uid}.
    """
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT \"public\" FROM objects WHERE uid = %s AND type = 'league'",
            (uid,),
        )
        row = await result.fetchone()
        if not row or row[0] is None:
            return None
        pub = row[0] if isinstance(row[0], dict) else msgspec.json.decode(row[0])
        result = await conn.execute(
            """SELECT COUNT(*) FROM objects
               WHERE type = 'tournament' AND deleted_at IS NULL
                 AND "full"->>'league_uid' = %s""",
            (uid,),
        )
        count = (await result.fetchone())[0]
        return pub, count


async def soft_delete_tournament(
    uid: str,
) -> tuple[Tournament, list[BroadcastData]] | None:
    """Soft-delete a tournament and cascade the tombstone to its decks and sanctions.

    Returns bd for the tournament plus each dependent object, or they'd linger
    live and orphaned in every client's IndexedDB. All writes share the
    tournament's row-lock transaction.
    """
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            return None
        now = datetime.now(UTC)
        tournament.deleted_at = now
        tournament.modified = now
        bds = [await save_tournament(tournament, conn=tx_conn)]
        decks = await get_decks_for_tournament(uid, conn=tx_conn)
        sanctions = await get_sanctions_for_tournament(uid, conn=tx_conn)
        for obj_type, objs in (
            (ObjectType.DECK, decks),
            (ObjectType.SANCTION, sanctions),
        ):
            for obj in objs:
                if obj.deleted_at is not None:
                    continue  # get_decks_for_tournament doesn't filter tombstones
                tombstoned = msgspec.structs.replace(obj, deleted_at=now, modified=now)
                bds.append(
                    await save_object_from_model(obj_type, tombstoned, conn=tx_conn)
                )
    return tournament, bds


async def get_tournament_by_event_code(code: str) -> Tournament | None:
    """Resolve a short code, then a vekn event id on a miss.

    The fallback covers the events whose vekn id arrived after their code was
    minted — a push that failed at creation and succeeded on a later batch. It
    can never shadow a real code, since a hit on the code column ends the lookup.
    """
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'tournament' AND deleted_at IS NULL
              AND lower("full"->>'event_code') = lower(%s) LIMIT 1""",
            (code,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], Tournament)
    return await get_tournament_by_external_id("vekn", code)


async def get_tournament_by_external_id(
    platform: str, ext_id: str
) -> Tournament | None:
    """Get a LIVE tournament by external ID (e.g., platform='vekn', ext_id='123').

    Skips soft-deleted holders: the legacy-archon merge tombstones round-less
    duplicates of an event id, so matching one here would refresh the dead
    copy instead of the surviving tournament.
    """
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'tournament' AND "full"->'external_ids'->>%s = %s
              AND deleted_at IS NULL LIMIT 1""",
            (platform, ext_id),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], Tournament)
        return None


# Crockford base32: no I/L/O/U, so nothing decodes two ways when read aloud.
_EVENT_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


async def _event_code_taken(code: str, conn: psycopg.AsyncConnection) -> bool:
    result = await conn.execute(
        """SELECT 1 FROM objects
        WHERE type = 'tournament' AND lower("full"->>'event_code') = lower(%s)
        LIMIT 1""",
        (code,),
    )
    return await result.fetchone() is not None


async def resolve_event_code(
    tournament: Tournament, conn: psycopg.AsyncConnection
) -> str:
    """The event's permanent public handle, decided once and never revisited.

    A taken candidate falls through to a mint rather than failing the save: the
    14 numeric archive keys are vekn event ids a row we already hold may carry.
    """
    for candidate in (
        tournament.external_ids.get("vekn"),
        tournament.external_ids.get("twda"),
    ):
        if candidate and not await _event_code_taken(candidate, conn):
            return candidate
    for _ in range(20):
        code = "".join(secrets.choice(_EVENT_CODE_ALPHABET) for _ in range(6))
        # An all-digit mint would read as a vekn event id it is not.
        if code.isdigit():
            continue
        if not await _event_code_taken(code, conn):
            return code
    raise RuntimeError("event code space exhausted")


async def ensure_event_code(uid: str) -> BroadcastData | None:
    """Stamp the handle on a row that has none. Returns None when it already had
    one — the code is written once, so this can never overwrite."""
    async with tournament_transaction(uid) as (fresh, tx_conn):
        if not fresh or fresh.event_code:
            return None
        fresh.event_code = await resolve_event_code(fresh, tx_conn)
        fresh.modified = datetime.now(UTC)
        return await save_tournament(fresh, conn=tx_conn)


async def tournament_uids_without_event_code() -> list[str]:
    """Live rows a creation path never got to stamp — a restart between the insert
    and the push task. Without the sweep they would have no handle at all."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT uid FROM objects
            WHERE type = 'tournament' AND deleted_at IS NULL
              AND coalesce("full"->>'event_code', '') = ''"""
        )
        return [row[0] for row in await result.fetchall()]


# Same-event matcher for two import paths with no shared key. Name+day is NOT
# an identity key alone — legacy placeholder names collide, so a hit is candidate evidence only.
SAME_EVENT_QUERY = """
    SELECT "full" FROM objects
    WHERE type = 'tournament'
      AND deleted_at IS NULL
      AND uid <> %s
      AND lower(btrim("full"->>'name')) = lower(btrim(%s))
      AND "full"->>'start' IS NOT NULL
      AND abs(extract(epoch FROM (("full"->>'start')::timestamptz - %s::timestamptz))) < 86400
"""


async def find_same_event_tournaments(
    name: str, start: datetime, exclude_uid: str = "", country: str | None = None
) -> list[Tournament]:
    """Live tournaments that MIGHT be the same real event as (name, start).

    A hit is a candidate, not a match — see SAME_EVENT_QUERY. `country` drops
    candidates that declare a different one (a same-named event elsewhere on the
    same day is a different event); candidates or callers without a country
    declared stay in, since most legacy imports have none. Both sides go through
    `country_key` because some rows hold the country NAME in that field — comparing
    raw drops them as if they disagreed ([hazards](../../wiki/hazards.md)) — and a
    value that resolves to nothing still compares as itself, so an unrecognised
    spelling narrows the candidates rather than disabling the filter.
    """
    if not name or start is None:
        return []
    async with get_connection() as conn:
        result = await conn.execute(
            SAME_EVENT_QUERY, (exclude_uid, name, start.isoformat())
        )
        found = [decode_json(row[0], Tournament) for row in await result.fetchall()]
    if country:
        wanted = country_key(country)
        found = [t for t in found if not t.country or country_key(t.country) == wanted]
    return found


VEKN_ABSENCE_CANDIDATES_QUERY = """
    SELECT "full" FROM objects
    WHERE type = 'tournament'
      AND deleted_at IS NULL
      AND ("full"->'external_ids'->>'vekn' = ANY(%s::text[])
           OR "full"->>'vekn_event_absent_at' IS NOT NULL)
"""


async def find_vekn_absence_candidates(absent_ids: list[str]) -> list[Tournament]:
    """Live tournaments holding one of `absent_ids`, plus every flagged row."""
    async with get_connection() as conn:
        result = await conn.execute(VEKN_ABSENCE_CANDIDATES_QUERY, (absent_ids,))
        return [decode_json(row[0], Tournament) for row in await result.fetchall()]


# Live copies of one event where only SOME hold a vekn id. The mixed-vekn filter
# is load-bearing — without it, legacy placeholder names flood every result.
DUPLICATE_GROUPS_QUERY = """
    WITH t AS (
        SELECT uid,
               btrim("full"->>'name') AS name,
               ("full"->>'start')::timestamptz AS start,
               "full"->'external_ids'->>'vekn' AS vekn
        FROM objects
        WHERE type = 'tournament'
          AND deleted_at IS NULL
          AND "full"->>'start' IS NOT NULL
    )
    SELECT lower(name) AS key, (start AT TIME ZONE 'UTC')::date AS day,
           min(name) AS name, array_agg(uid ORDER BY uid) AS uids,
           count(vekn) AS with_vekn
    FROM t
    GROUP BY 1, 2
    HAVING count(*) > 1
       AND count(vekn) BETWEEN 1 AND count(*) - 1
"""


async def find_duplicate_tournament_groups() -> list[dict]:
    """Live copies of one event where only some copies hold a vekn id."""
    async with get_connection() as conn:
        result = await conn.execute(DUPLICATE_GROUPS_QUERY)
        return [
            {"name": row[2], "day": row[1], "uids": row[3], "with_vekn": row[4]}
            for row in await result.fetchall()
        ]


# Same-name/same-day groups where EVERY copy holds a different vekn id — usually
# distinct events sharing a placeholder name; feeds the dedup script, never the sync's logging.
BOTH_VEKN_GROUPS_QUERY = """
    WITH t AS (
        SELECT uid,
               btrim("full"->>'name') AS name,
               ("full"->>'start')::timestamptz AS start,
               "full"->'external_ids'->>'vekn' AS vekn
        FROM objects
        WHERE type = 'tournament'
          AND deleted_at IS NULL
          AND "full"->>'start' IS NOT NULL
    )
    SELECT lower(name) AS key, (start AT TIME ZONE 'UTC')::date AS day,
           min(name) AS name, array_agg(uid ORDER BY uid) AS uids
    FROM t
    GROUP BY 1, 2
    HAVING count(*) > 1
       AND count(vekn) = count(*)
       AND count(DISTINCT vekn) > 1
"""


async def find_both_vekn_tournament_groups() -> list[dict]:
    """Live same-event copies that all hold different vekn ids (see query comment)."""
    async with get_connection() as conn:
        result = await conn.execute(BOTH_VEKN_GROUPS_QUERY)
        return [
            {"name": row[2], "day": row[1], "uids": row[3]}
            for row in await result.fetchall()
        ]


# An event needs this many players to reach the TWDA, and a win counts toward the
# Hall of Fame only where it would have qualified. Deliberately not the 8-player
# rating floor in `ranking_eligibility` — the two are meant to disagree.
TWDA_MIN_PLAYERS = 10

_HOF_WINS_QUERY = """
    SELECT t.uid,
           t."full"->>'winner',
           t."full"->'external_ids'->>'twda',
           COALESCE((t."full"->>'reported_player_count')::int, 0),
           t."full"::text
    FROM objects t
    WHERE t.type = 'tournament'
      AND t.deleted_at IS NULL
      AND t."full"->>'state' = 'Finished'
      AND COALESCE(t."full"->>'winner', '') <> ''
      AND (t."full"->>'online') IS DISTINCT FROM 'true'
      AND (t."full"->>'open_rounds') IS DISTINCT FROM 'true'
      AND (t."full"->>'self_organized_rounds') IS DISTINCT FROM 'true'
      AND (t."full"->>'format') IS DISTINCT FROM 'Limited'
      AND EXISTS (
          SELECT 1 FROM objects d
          WHERE d.type = 'deck'
            AND d.deleted_at IS NULL
            AND d."full"->>'tournament_uid' = t.uid
            AND d."full"->>'user_uid' = t."full"->>'winner'
      )
"""
_HOF_WINS_BATCH = 500


async def get_all_tournament_wins(
    winners: set[str] | None = None,
) -> dict[str, list[str]]:
    """Hall-of-Fame win uids per winner, enumerated from the tournaments.

    Never from a user list: a historic winner who played no rated event appears
    in no player set, which is exactly how half the Hall of Fame went missing.
    `winners` narrows what a targeted recompute rewrites, never what qualifies.

    The floor reads `attested_player_count`, not the seated count — a rounds-less
    VEKN import and an archival reconstruction both seat nobody and would read 0.
    """
    if winners is not None and not winners:
        return {}
    wins: dict[str, list[str]] = {}
    async with get_connection() as conn:
        if winners is not None:
            # Deliberately unpaginated: `idx_objects_tournament_winner` answers
            # this directly, while a keyset `ORDER BY uid LIMIT n` invites the
            # planner onto the primary key and scans the corpus per recompute.
            result = await conn.execute(
                _HOF_WINS_QUERY + " AND t.\"full\"->>'winner' = ANY(%s)",
                ([*winners],),
            )
            _collect_wins(await result.fetchall(), wins)
            return wins

        last_uid = ""
        while True:
            result = await conn.execute(
                _HOF_WINS_QUERY + " AND t.uid > %s ORDER BY t.uid LIMIT %s",
                (last_uid, _HOF_WINS_BATCH),
            )
            rows = await result.fetchall()
            _collect_wins(rows, wins)
            if len(rows) < _HOF_WINS_BATCH:
                return wins
            last_uid = rows[-1][0]


def _collect_wins(rows: list, wins: dict[str, list[str]]) -> None:
    """The floor half of the rule, which SQL cannot express: the precedence chain
    and the seat union live in the engine."""
    for uid, winner, twda_id, reported, full in rows:
        if _engine.attested_player_count(full) < TWDA_MIN_PLAYERS:
            # A TWDA entry with no `players_count` grandfathers past the floor:
            # the archive accepting it is the attestation. Only where the row
            # played nothing — a result sheet we hold answers the question.
            archival = bool(twda_id) and not reported
            if not archival or _engine.ranking_eligibility(full) != "no_results":
                continue
        wins.setdefault(winner, []).append(uid)


async def get_user_uids_with_wins() -> set[str]:
    """Users whose stored win list is non-empty — the clear side of the recompute.
    A deleted tournament, a corrected winner or a withdrawn deck leaves no
    tournament row naming them, so enumeration alone would never zero them."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT uid FROM objects WHERE type = 'user' AND deleted_at IS NULL "
            "AND jsonb_array_length(COALESCE(\"full\"->'wins', '[]'::jsonb)) > 0"
        )
        return {row[0] for row in await result.fetchall()}


async def get_finished_tournaments_for_category(
    format_value: str, online: bool, since_date: str
) -> list[Tournament]:
    """Get all live FINISHED tournaments matching format/online within date window."""
    async with get_connection() as conn:
        # finish is optional (the engine never stamps it) — fall back to start
        # then modified, mirroring ratings.py. A soft-deleted tournament keeps
        # state='Finished', hence deleted_at IS NULL.
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'tournament'
              AND deleted_at IS NULL
              AND "full"->>'state' = 'Finished'
              AND "full"->>'format' = %s
              AND ("full"->>'online')::boolean = %s
              AND COALESCE("full"->>'finish', "full"->>'start', "full"->>'modified')::timestamp
                  >= %s::timestamp""",
            (format_value, online, since_date),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Tournament) for row in rows]


async def save_league(league: League) -> BroadcastData:
    return await save_object_from_model(ObjectType.LEAGUE, league)


async def save_promo(promo: Promo) -> BroadcastData:
    return await save_object_from_model(ObjectType.PROMO, promo)


async def get_promo_by_uid(uid: str) -> Promo | None:
    return await get_object_full(uid, Promo)


async def get_all_promos(
    conn: psycopg.AsyncConnection | None = None,
) -> list[Promo]:
    """Get all promos (retired included; UI filters on `active`)."""
    async with _acquire(conn) as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'promo' AND deleted_at IS NULL""",
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Promo) for row in rows]


async def count_promo_references(uid: str) -> int:
    """Rows referencing a promo: tournament reports, raffle prizes, ledger.

    Guards hard-delete: a referenced promo must be retired (active=false), never
    tombstoned — the universal soft-delete would evict it from clients and dangle
    historical rows.
    """
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT
                (SELECT COUNT(*) FROM objects
                 WHERE type = 'tournament' AND deleted_at IS NULL
                   AND ("full"->'promos_distributed' @> %s::jsonb
                        OR "full"->'raffles' @> %s::jsonb))
                + (SELECT COUNT(*) FROM promo_ledger WHERE promo_uid = %s)""",
            (
                msgspec.json.encode([{"promo_uid": uid}]).decode(),
                msgspec.json.encode([{"prize_promo_uid": uid}]).decode(),
                uid,
            ),
        )
        row = await result.fetchone()
        return row[0] if row else 0


async def get_all_leagues(
    conn: psycopg.AsyncConnection | None = None,
) -> list[League]:
    async with _acquire(conn) as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'league' AND deleted_at IS NULL""",
        )
        rows = await result.fetchall()
        return [decode_json(row[0], League) for row in rows]


async def get_league_by_uid(uid: str) -> League | None:
    return await get_object_full(uid, League)


async def get_child_leagues(parent_uid: str) -> list[League]:
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'league' AND "full"->>'parent_uid' = %s""",
            (parent_uid,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], League) for row in rows]


async def upsert_avatar(
    user_uid: str, data: bytes, content_type: str = "image/webp"
) -> None:
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO avatars (user_uid, data, content_type, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (user_uid) DO UPDATE SET
                data = EXCLUDED.data,
                content_type = EXCLUDED.content_type,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_uid, data, content_type),
        )


async def get_avatar(user_uid: str) -> tuple[bytes, str] | None:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data, content_type FROM avatars WHERE user_uid = %s",
            (user_uid,),
        )
        row = await result.fetchone()
        if row:
            return (row[0], row[1])
        return None


async def delete_avatar(user_uid: str) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM avatars WHERE user_uid = %s RETURNING user_uid",
            (user_uid,),
        )
        row = await result.fetchone()
        return row is not None


async def upsert_banner(
    tournament_uid: str, data: bytes, content_type: str = "image/webp"
) -> None:
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO banners (tournament_uid, data, content_type, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (tournament_uid) DO UPDATE SET
                data = EXCLUDED.data,
                content_type = EXCLUDED.content_type,
                updated_at = CURRENT_TIMESTAMP
            """,
            (tournament_uid, data, content_type),
        )


async def get_banner(tournament_uid: str) -> tuple[bytes, str] | None:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data, content_type FROM banners WHERE tournament_uid = %s",
            (tournament_uid,),
        )
        row = await result.fetchone()
        if row:
            return (row[0], row[1])
        return None


async def delete_banner(tournament_uid: str) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM banners WHERE tournament_uid = %s RETURNING tournament_uid",
            (tournament_uid,),
        )
        row = await result.fetchone()
        return row is not None


async def upsert_promo_image(
    promo_uid: str, data: bytes, content_type: str = "image/webp"
) -> None:
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO promo_images (promo_uid, data, content_type, updated_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (promo_uid) DO UPDATE SET
                data = EXCLUDED.data,
                content_type = EXCLUDED.content_type,
                updated_at = CURRENT_TIMESTAMP
            """,
            (promo_uid, data, content_type),
        )


async def get_promo_image(promo_uid: str) -> tuple[bytes, str] | None:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data, content_type FROM promo_images WHERE promo_uid = %s",
            (promo_uid,),
        )
        row = await result.fetchone()
        if row:
            return (row[0], row[1])
        return None


async def delete_promo_image(promo_uid: str) -> bool:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM promo_images WHERE promo_uid = %s RETURNING promo_uid",
            (promo_uid,),
        )
        row = await result.fetchone()
        return row is not None


_NDA_COLS = (
    "uid, user_uid, status, document_version, document_sha256, signer_name, "
    "signer_email, requested_by, created_at, signed_at, content_type"
)


def _nda_row_to_dict(row: tuple) -> dict:
    return {
        "uid": row[0],
        "user_uid": row[1],
        "status": row[2],
        "document_version": row[3],
        "document_sha256": row[4],
        "signer_name": row[5],
        "signer_email": row[6],
        "requested_by": row[7],
        "created_at": row[8],
        "signed_at": row[9],
        "content_type": row[10],
    }


async def create_nda_request(uid: str, user_uid: str, requested_by: str) -> bool:
    """False when the member already has an open request (partial unique index)."""
    async with get_connection() as conn:
        result = await conn.execute(
            """INSERT INTO nda_records (uid, user_uid, status, requested_by)
            VALUES (%s, %s, 'pending', %s)
            ON CONFLICT (user_uid) WHERE status = 'pending' DO NOTHING
            RETURNING uid""",
            (uid, user_uid, requested_by),
        )
        return await result.fetchone() is not None


async def get_nda_records(user_uid: str) -> list[dict]:
    async with get_connection() as conn:
        result = await conn.execute(
            f"SELECT {_NDA_COLS} FROM nda_records WHERE user_uid = %s "
            "ORDER BY created_at DESC",
            (user_uid,),
        )
        return [_nda_row_to_dict(r) for r in await result.fetchall()]


async def get_nda_pending(user_uid: str) -> dict | None:
    async with get_connection() as conn:
        result = await conn.execute(
            f"SELECT {_NDA_COLS} FROM nda_records "
            "WHERE user_uid = %s AND status = 'pending'",
            (user_uid,),
        )
        row = await result.fetchone()
        return _nda_row_to_dict(row) if row else None


async def seal_nda_signature(
    record_uid: str,
    user_uid: str,
    *,
    document_version: int,
    document_sha256: str,
    signer_name: str,
    signer_email: str,
    signer_address: str,
    signer_phone: str,
    signed_at: datetime,
    pdf: bytes,
) -> bool:
    """Flip the pending request to signed and seal the evidence in one write."""
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE nda_records SET status = 'signed',
                document_version = %s, document_sha256 = %s, signer_name = %s,
                signer_email = %s, signer_address = %s, signer_phone = %s,
                signed_at = %s, pdf = %s, content_type = 'application/pdf'
            WHERE uid = %s AND user_uid = %s AND status = 'pending'
            RETURNING uid""",
            (
                document_version,
                document_sha256,
                signer_name,
                signer_email,
                signer_address,
                signer_phone,
                signed_at,
                pdf,
                record_uid,
                user_uid,
            ),
        )
        return await result.fetchone() is not None


async def insert_nda_upload(
    uid: str, user_uid: str, uploaded_by: str, pdf: bytes, content_type: str
) -> None:
    """A leftover pending row would block every future request through the
    partial unique index, so the delete rides the insert's transaction."""
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM nda_records WHERE user_uid = %s AND status = 'pending'",
                (user_uid,),
            )
            await conn.execute(
                """INSERT INTO nda_records
                    (uid, user_uid, status, requested_by, signed_at, pdf, content_type)
                VALUES (%s, %s, 'uploaded', %s, CURRENT_TIMESTAMP, %s, %s)""",
                (uid, user_uid, uploaded_by, pdf, content_type),
            )


async def get_nda_pdf(user_uid: str, record_uid: str) -> tuple[bytes, str] | None:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT pdf, content_type FROM nda_records "
            "WHERE uid = %s AND user_uid = %s AND pdf IS NOT NULL",
            (record_uid, user_uid),
        )
        row = await result.fetchone()
        return (bytes(row[0]), row[1]) if row else None


async def user_has_nda(user_uid: str) -> bool:
    """An NDA is on record: signed in-app or a paper scan uploaded."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT 1 FROM nda_records "
            "WHERE user_uid = %s AND status IN ('signed', 'uploaded') LIMIT 1",
            (user_uid,),
        )
        return await result.fetchone() is not None


async def remap_nda_user(old_uid: str, new_uid: str) -> None:
    """Point NDA records at the account surgery's surviving human."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE nda_records SET user_uid = %s WHERE user_uid = %s",
            (new_uid, old_uid),
        )


_LEDGER_COLS = (
    "uid, kind, promo_uid, qty, from_uid, to_uid, note, happened_at, "
    "created_by, created_at"
)


def _ledger_row_to_entry(row: tuple) -> PromoLedgerEntry:
    return PromoLedgerEntry(
        uid=row[0],
        kind=PromoLedgerKind(row[1]),
        promo_uid=row[2],
        qty=row[3],
        from_uid=row[4],
        to_uid=row[5],
        note=row[6],
        happened_at=row[7],
        created_by=row[8],
        created_at=row[9],
    )


async def insert_promo_ledger_entry(entry: PromoLedgerEntry) -> None:
    """Append one ledger row (corrections are new compensating rows)."""
    async with get_connection() as conn:
        await conn.execute(
            f"""INSERT INTO promo_ledger ({_LEDGER_COLS})
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                entry.uid,
                entry.kind,
                entry.promo_uid,
                entry.qty,
                entry.from_uid,
                entry.to_uid,
                entry.note,
                entry.happened_at,
                entry.created_by,
                entry.created_at,
            ),
        )


async def get_promo_ledger_entries(
    involved_uid: str | None = None,
) -> list[PromoLedgerEntry]:
    """Whole role-scoped ledger, oldest first. No pagination by design
    (CLAUDE.md convention): officials read everything (involved_uid=None),
    everyone else only rows they are party to."""
    async with get_connection() as conn:
        if involved_uid is None:
            result = await conn.execute(
                f"SELECT {_LEDGER_COLS} FROM promo_ledger ORDER BY happened_at, uid"
            )
        else:
            result = await conn.execute(
                f"""SELECT {_LEDGER_COLS} FROM promo_ledger
                WHERE from_uid = %s OR to_uid = %s OR created_by = %s
                ORDER BY happened_at, uid""",
                (involved_uid, involved_uid, involved_uid),
            )
        rows = await result.fetchall()
        return [_ledger_row_to_entry(r) for r in rows]


async def get_promo_ledger_for_promos(
    promo_uids: list[str],
) -> list[PromoLedgerEntry]:
    """All ledger rows for the given promos (recompute input)."""
    if not promo_uids:
        return []
    async with get_connection() as conn:
        result = await conn.execute(
            f"SELECT {_LEDGER_COLS} FROM promo_ledger WHERE promo_uid = ANY(%s)",
            (promo_uids,),
        )
        rows = await result.fetchall()
        return [_ledger_row_to_entry(r) for r in rows]


async def remap_promo_ledger_user(old_uid: str, new_uid: str) -> None:
    """Point ledger rows at a merged user (users/merge)."""
    async with get_connection() as conn:
        await conn.execute(
            """UPDATE promo_ledger SET
                from_uid = CASE WHEN from_uid = %(old)s THEN %(new)s ELSE from_uid END,
                to_uid = CASE WHEN to_uid = %(old)s THEN %(new)s ELSE to_uid END,
                created_by = CASE WHEN created_by = %(old)s THEN %(new)s ELSE created_by END
            WHERE from_uid = %(old)s OR to_uid = %(old)s OR created_by = %(old)s""",
            {"old": old_uid, "new": new_uid},
        )


async def get_tournament_promo_attributions(
    promo_uids: set[str],
) -> list[tuple[str, str, int]]:
    """(promo_uid, holder_uid, qty) from live tournaments' distribution
    reports, attributed to each report's stock source. Recompute input."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full"->'promos_distributed', "full"->>'promo_stock_source_uid'
            FROM objects WHERE type = 'tournament' AND deleted_at IS NULL
              AND jsonb_array_length(coalesce("full"->'promos_distributed', '[]'::jsonb)) > 0"""
        )
        rows = await result.fetchall()
    out: list[tuple[str, str, int]] = []
    for dist_rows, source_uid in rows:
        if not source_uid:
            continue
        for r in dist_rows or []:
            promo_uid = r.get("promo_uid")
            if promo_uid in promo_uids:
                out.append((promo_uid, source_uid, int(r.get("qty", 0))))
    return out


async def get_users_with_promo_stock_keys(promo_uids: list[str]) -> list[str]:
    """Users whose stored promo_stock mentions any of the given promos —
    ensures stale keys get cleaned even when the holder no longer appears in
    the recomputed aggregates (e.g. a report's stock source was changed)."""
    if not promo_uids:
        return []
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT uid FROM objects WHERE type = 'user' AND deleted_at IS NULL
              AND coalesce("full"->'promo_stock', '{}'::jsonb) ?| %s::text[]""",
            (promo_uids,),
        )
        rows = await result.fetchall()
        return [r[0] for r in rows]


async def store_transient_token(key: str, data: dict, expires_at) -> None:
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO transient_tokens (key, data, expires_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, expires_at = EXCLUDED.expires_at
            """,
            (key, _encoder.encode(data).decode("utf-8"), expires_at),
        )


async def get_transient_token(key: str) -> dict | None:
    """Get a transient token if not expired (None if missing or expired)."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM transient_tokens WHERE key = %s AND expires_at > NOW()",
            (key,),
        )
        row = await result.fetchone()
        if row:
            return (
                msgspec.json.decode(row[0])
                if isinstance(row[0], (str, bytes))
                else row[0]
            )
        return None


async def delete_transient_token(key: str) -> None:
    async with get_connection() as conn:
        await conn.execute("DELETE FROM transient_tokens WHERE key = %s", (key,))


async def cleanup_expired_tokens() -> int:
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM transient_tokens WHERE expires_at < NOW() RETURNING key"
        )
        rows = await result.fetchall()
        return len(rows)


async def save_push_subscription(
    *,
    endpoint: str,
    user_uid: str,
    p256dh: str,
    auth: str,
    ua: str | None = None,
    locale: str = "en",
) -> None:
    """Upsert a browser's push subscription, keyed by endpoint (re-subscribe = update).
    `locale` is the browser's UI language; payload bodies render per-subscription."""
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO push_subscriptions
                (endpoint, user_uid, p256dh, auth, ua, locale, last_seen_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (endpoint) DO UPDATE SET
                user_uid = EXCLUDED.user_uid,
                p256dh = EXCLUDED.p256dh,
                auth = EXCLUDED.auth,
                ua = EXCLUDED.ua,
                locale = EXCLUDED.locale,
                last_seen_at = NOW()
            """,
            (endpoint, user_uid, p256dh, auth, ua, locale),
        )


async def delete_push_subscription(endpoint: str, user_uid: str | None = None) -> None:
    """Delete a subscription. Scope by ``user_uid`` for user-initiated unsubscribe;
    omit it for the send-path 404/410 prune (the endpoint is gone for everyone)."""
    async with get_connection() as conn:
        if user_uid is None:
            await conn.execute(
                "DELETE FROM push_subscriptions WHERE endpoint = %s", (endpoint,)
            )
        else:
            await conn.execute(
                "DELETE FROM push_subscriptions WHERE endpoint = %s AND user_uid = %s",
                (endpoint, user_uid),
            )


async def get_push_subscriptions_for_users(
    user_uids: list[str],
) -> list[tuple[str, str, str, str, str]]:
    """All (endpoint, user_uid, p256dh, auth, locale) rows for the given users."""
    if not user_uids:
        return []
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT endpoint, user_uid, p256dh, auth, locale "
            "FROM push_subscriptions WHERE user_uid = ANY(%s)",
            (user_uids,),
        )
        return await result.fetchall()
