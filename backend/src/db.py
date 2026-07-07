"""Database connection and initialization."""

import asyncio
import hashlib
import os
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
from psycopg_pool import AsyncConnectionPool

from .models import (
    AuthMethod,
    DeckObject,
    League,
    ObjectType,
    Role,
    Sanction,
    Tournament,
    User,
)


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
    # Authoritative modified_at (DB clock) of the written row. Emitted in the
    # live SSE envelope as `ts` so clients advance their sync cursor in the same
    # value space the `since` catch-up filter uses (not the payload's `modified`,
    # which is an independent app-clock value in a different format).
    modified_at: str | None = None


# Database connection string from environment
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://archon:archon_dev_password@localhost:5433/archon",
)

# Pool ceiling. One async uvicorn worker, so this bounds the backend's PG
# backends (~5-10MB RSS each). Lowered via env on the memory-constrained prod
# box that shares one cluster with legacy archon; beta/dev keep the default.
POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "20"))

# Global connection pool
_pool: AsyncConnectionPool | None = None


class _ActiveTx(NamedTuple):
    """The connection an open `tournament_transaction` owns, plus its owner task."""

    conn: "psycopg.AsyncConnection"
    task: "asyncio.Task | None"


# Ambient transaction connection. `tournament_transaction` sets this to its
# locked connection for the duration of the `async with` block; while it is set,
# `get_connection()` (and therefore every DB helper that calls it) transparently
# runs on that one connection instead of checking out a fresh one. This keeps a
# single in-flight action to ONE pooled connection — it cannot starve the pool by
# acquiring more while holding the FOR UPDATE lock — and makes every nested
# read/write part of the same transaction. See `get_connection`.
#
# INVARIANT: never start a DB-touching `asyncio.create_task`/`gather` inside a
# transaction. A child task inherits this ContextVar (and the connection) and
# would interleave operations on it with the parent and/or outlive the `with`
# block. We do NOT rely on discipline alone: `get_connection` records the owner
# task and raises if the ambient connection is reached from any other task, so
# such misuse fails loudly instead of corrupting the wire protocol. (Today all
# spawned DB tasks — Discord role sync, VEKN sync — fire post-commit, outside any
# transaction, so the var is unset when their context is copied.)
_tx_conn: ContextVar["_ActiveTx | None"] = ContextVar("_tx_conn", default=None)


async def init_db() -> None:
    """Initialize database connection pool and schema."""
    global _pool

    # Create connection pool with autocommit enabled
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
    """Close database connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterator[psycopg.AsyncConnection]:
    """Check a connection out of the pool (the raw pool primitive).

    This always pools — it is intentionally NOT ambient-aware, so writers that
    must commit independently of an open `tournament_transaction` (e.g. the
    go-online VEKN-ID allocation loop, where each new user must be committed and
    visible before the next `allocate_next_vekn_id`) keep their own connection.
    Reads that should join an open transaction go through `_acquire`.
    """
    if not _pool:
        raise RuntimeError("Database not initialized")
    async with _pool.connection() as conn:
        yield conn


@asynccontextmanager
async def _acquire(
    conn: psycopg.AsyncConnection | None = None,
) -> AsyncIterator[psycopg.AsyncConnection]:
    """Resolve a connection for a READ by precedence: explicit ``conn`` → ambient
    transaction connection → pool.

    An explicit ``conn`` pins the read to a connection the caller already holds.
    With none, if a `tournament_transaction` is open on THIS task its connection
    is reused (so the action never checks out a second connection while holding
    its FOR UPDATE lock, and the read sees the transaction's snapshot); otherwise
    a pooled connection is used. Reaching the ambient connection from a *different*
    task raises — that only happens if DB work was spawned inside a transaction
    (`create_task`/`gather`), which would interleave operations on the shared
    connection or outlive it. See `_tx_conn`.

    For WRITES inside a transaction, pass `conn=tx_conn` explicitly to join it, or
    use `get_connection` to commit independently — never rely on the ambient path
    for a write, so the read/write transaction boundary stays obvious at the call.
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
    """Lock a tournament row for update within a transaction.

    Uses SELECT ... FOR UPDATE to serialize concurrent writes to the same
    tournament. Yields (tournament, connection). The caller must use the
    yielded connection for any UPDATE within the same transaction.
    Commits on normal exit, rolls back on exception.

    While this block is open, `_tx_conn` is set so every DB helper called on this
    task transparently runs on `conn` (one pooled connection per action, all reads
    and writes inside the one transaction) — see `get_connection`.
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


# ---------------------------------------------------------------------------
# Access-version fingerprint (SSE connect handshake) — see SYNC.md
# ---------------------------------------------------------------------------

# Global wire-shape lever: bump on any change to the projected JSON shape that does
# NOT also ride a frontend DB_VERSION bump (a field rename/remove in models.py, an
# access_levels projection-policy change, a nested engine-struct change). One bump
# flips every client's fingerprint → exactly one resync. The narrow backstop, not
# the primary mechanism (a DB_VERSION bump self-heals client-side).
DATA_SCHEMA_VERSION = 1

# Roles that branch in base_data_level / entitled_level / access_levels — the only
# roles whose presence changes a viewer's entitlement (so only these enter the fp).
_OVERLAY_ROLES = (Role.IC, Role.NC, Role.PRINCE)


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
                # index's `WHERE type = 'tournament'` predicate; @> (not ?) so its
                # jsonb_path_ops opclass applies. See idx_objects_tournament_organizers.
                "SELECT uid FROM objects WHERE type = 'tournament' "
                "AND (\"full\"->'organizers_uids') @> %s::jsonb AND deleted_at IS NULL",
                (_encoder.encode([user_uid]).decode(),),
            )
        ).fetchall()
    return sorted(r[0] for r in rows)


async def compute_access_version(viewer: User | None) -> str:
    """Opaque per-user entitlement fingerprint for the SSE connect handshake.

    Hashes everything that changes WHICH objects (or which projection of them) a
    viewer is entitled to: the wire-shape version, base level, overlay-granting
    roles, the country that scopes an NC/Prince overlay, and the tournaments they
    organize. A mismatch at connect ⇒ the cached corpus predates an entitlement
    change a since-delta can't repair ⇒ resync. Backend-only + opaque: the client
    stores + echoes it, never parses it, so the inputs stay server-evolvable.
    """
    level = base_data_level(viewer)
    roles = sorted(r.value for r in _OVERLAY_ROLES if viewer and r in viewer.roles)
    # country enters the fp ONLY for officials — it scopes their same-country overlay.
    # Must stay in lockstep with entitled_level's same-country branch (broadcast.py).
    official = bool(viewer and (Role.NC in viewer.roles or Role.PRINCE in viewer.roles))
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
    """Encode a msgspec Struct to JSON string."""
    return _encoder.encode(obj).decode("utf-8")


def decode_json[T](data: str | dict, type_: type[T]) -> T:
    """Decode JSON string or dict to a msgspec Struct."""
    decoder = _decoder_for(type_)
    if isinstance(data, dict):
        # Convert dict back to JSON string for msgspec
        data = _encoder.encode(data).decode("utf-8")
    return decoder.decode(data)


# ---------------------------------------------------------------------------
# Unified objects table operations
# ---------------------------------------------------------------------------

from .access_levels import compute_full, compute_member, compute_public  # noqa: E402


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
    """Save an object to the unified objects table.

    Computes public/member/full projections and upserts.
    Returns BroadcastData for broadcasting without DB re-read.
    """
    pub = compute_public(obj_type, full_data)
    mem = compute_member(obj_type, full_data)
    full = compute_full(obj_type, full_data)

    # Serialize to JSON strings for JSONB columns
    pub_json = _encoder.encode(pub).decode("utf-8") if pub is not None else None
    mem_json = _encoder.encode(mem).decode("utf-8") if mem is not None else None
    full_json = _encoder.encode(full).decode("utf-8")

    # calendar_token is the only field persisted outside the JSONB projections
    # (it must never be broadcast over SSE — see the objects table DDL). The
    # token rarely travels in full_data (reads strip it), so the upsert below
    # COALESCEs it: a NULL write PRESERVES the stored token. This makes every
    # write path (profile edits, role changes, the nightly VEKN sync, …) safe
    # without each loader having to re-read the secret. The two paths that must
    # actually drop a token (strip/split VEKN) call clear_calendar_token().
    cal_token = full_data.get("calendar_token") if obj_type == ObjectType.USER else None

    query = """
        INSERT INTO objects (uid, type, deleted_at, "public", "member", "full", calendar_token)
        VALUES (%s, %s, %s::timestamp, %s::jsonb, %s::jsonb, %s::jsonb, %s)
        ON CONFLICT (uid) DO UPDATE SET
            type = EXCLUDED.type,
            deleted_at = EXCLUDED.deleted_at,
            "public" = EXCLUDED."public",
            "member" = EXCLUDED."member",
            "full" = EXCLUDED."full",
            calendar_token = COALESCE(EXCLUDED.calendar_token, objects.calendar_token)
        RETURNING modified_at
    """
    params = (uid, obj_type, deleted_at, pub_json, mem_json, full_json, cal_token)

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
) -> BroadcastData:
    """Save a msgspec model to the objects table."""
    full_data = msgspec.to_builtins(obj)
    deleted_at = full_data.get("deleted_at")
    # Convert deleted_at to string if it's not None
    if deleted_at is not None and not isinstance(deleted_at, str):
        deleted_at = (
            deleted_at.isoformat()
            if hasattr(deleted_at, "isoformat")
            else str(deleted_at)
        )
    return await save_object(obj_type, obj.uid, full_data, deleted_at=deleted_at)  # ty: ignore[unresolved-attribute]


async def delete_object(
    uid: str, *, conn: psycopg.AsyncConnection | None = None
) -> None:
    """Hard delete an object and any side-table binary asset keyed by its uid.

    Avatars (user_uid) and banners (tournament_uid) live in separate tables with
    no FK cascade, so a bare `DELETE FROM objects` would orphan their image bytes.
    A uid is a v7 UUID — it matches at most one of the two side tables, so both
    cleanup deletes are cheap PK lookups that no-op for objects without an asset.
    """

    async def _run(c: psycopg.AsyncConnection) -> None:
        # Atomic across the three tables: the pool is autocommit, so without an
        # explicit transaction a crash between deletes would orphan asset bytes
        # permanently (no future purge can re-find them). Nests as a savepoint if
        # `c` is already in a caller transaction.
        async with c.transaction():
            await c.execute("DELETE FROM objects WHERE uid = %s", (uid,))
            await c.execute("DELETE FROM avatars WHERE user_uid = %s", (uid,))
            await c.execute("DELETE FROM banners WHERE tournament_uid = %s", (uid,))
            await c.execute(
                "DELETE FROM push_subscriptions WHERE user_uid = %s", (uid,)
            )

    if conn:
        await _run(conn)
    else:
        async with get_connection() as c:
            await _run(c)


def _level_col(level: str) -> str:
    """Map access level name to quoted SQL column name.

    Fail-closed: an unknown level raises KeyError rather than silently serving
    the "full" projection — a mistyped level must never leak fields. Every caller
    passes a DataLevel value (public/member/full), so this never fires in practice.
    """
    return {"public": '"public"', "member": '"member"', "full": '"full"'}[level]


async def get_object(uid: str, *, level: str = "full") -> dict | None:
    """Get an object from the objects table at a given access level.

    Returns the raw dict (parsed from JSONB), or None if not found
    or not visible at the requested level.
    """
    col = _level_col(level)
    async with get_connection() as conn:
        result = await conn.execute(
            f"SELECT {col} FROM objects WHERE uid = %s",  # ty: ignore[invalid-argument-type]
            (uid,),
        )
        row = await result.fetchone()
        if row and row[0] is not None:
            return row[0] if isinstance(row[0], dict) else msgspec.json.decode(row[0])
        return None


# Model class -> stored `type` string. Lets get_object_full constrain its read to
# the type it will decode into, so a uid of the wrong type reads as absent instead
# of decoding a foreign row (msgspec fills the defaults) and being written back
# under EXCLUDED.type — silently transmuting e.g. a User row into a Tournament.
_OBJECT_TYPES: dict[type, ObjectType] = {
    User: ObjectType.USER,
    Sanction: ObjectType.SANCTION,
    Tournament: ObjectType.TOURNAMENT,
    League: ObjectType.LEAGUE,
    DeckObject: ObjectType.DECK,
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


async def get_objects_by_type(
    obj_type: str, *, level: str = "full", where: str = "", params: tuple = ()
) -> list[dict]:
    """Query objects table by type. Returns list of dicts at the given level."""
    col = _level_col(level)
    query = f"SELECT {col} FROM objects WHERE type = %s AND {col} IS NOT NULL"
    if where:
        query += f" AND {where}"
    all_params = (obj_type, *params)
    async with get_connection() as conn:
        result = await conn.execute(
            query,  # ty: ignore[invalid-argument-type]
            all_params,
        )
        rows = await result.fetchall()
        return [
            row[0] if isinstance(row[0], dict) else msgspec.json.decode(row[0])
            for row in rows
        ]


async def stream_objects_new(
    obj_type: str | None = None,
    level: str = "full",
    since: str | None = None,
    batch_size: int = 1000,
    exclude_deleted: bool = False,
) -> AsyncIterator[tuple[list[str], str]]:
    """Stream pre-serialized JSON in keyset-paginated batches.

    Each batch acquires a pooled connection, fetches up to `batch_size` rows
    ordered by (modified_at, uid), then RELEASES the connection BEFORE yielding —
    so a slow SSE client never pins a pool slot across its catch-up, and app heap
    holds at most one batch (not the whole resultset). This bounds the full-corpus
    reads a single fetchall would otherwise materialize per connection: a no-`since`
    rating recompute, or a large catch-up delta. Keyset continuation on
    (modified_at, uid) is tie-safe across batch boundaries (a same-timestamp run
    split by the LIMIT is neither skipped nor duplicated) and rides the
    idx_objects_type_modified (type, modified_at, uid) index.

    `exclude_deleted` filters soft-deleted rows (the snapshot path — a fresh client
    needs no tombstones); the SSE catch-up leaves it False so deletions propagate.
    Yields (batch_of_raw_json_strings, max_modified_at_in_batch) per non-empty batch.
    """
    if not _pool:
        raise RuntimeError("Database not initialized")

    col = _level_col(level)
    last_modified: str | None = None
    last_uid: str | None = None

    while True:
        conditions = [f"{col} IS NOT NULL"]
        params: list = []
        if obj_type:
            conditions.append("type = %s")
            params.append(obj_type)
        if exclude_deleted:
            conditions.append("deleted_at IS NULL")
        if last_modified is not None:
            # Keyset continuation: tie-safe past the previous batch's last row.
            conditions.append("(modified_at, uid) > (%s::timestamp, %s)")
            params += [last_modified, last_uid]
        elif since:
            conditions.append("modified_at > %s::timestamp")
            params.append(since)
        where = " AND ".join(conditions)

        async with _pool.connection() as conn:
            rows = await (
                await conn.execute(
                    f"SELECT {col}::text, modified_at, uid FROM objects "  # ty: ignore[invalid-argument-type]
                    f"WHERE {where} ORDER BY modified_at ASC, uid ASC LIMIT %s",
                    (*params, batch_size),
                )
            ).fetchall()

        if not rows:
            break
        yield [r[0] for r in rows], rows[-1][1].isoformat()
        if len(rows) < batch_size:
            break
        last_modified = rows[-1][1].isoformat()
        last_uid = rows[-1][2]


async def purge_deleted_objects(days: int = 30) -> int:
    """Hard-delete objects that were soft-deleted more than `days` ago."""
    if not _pool:
        raise RuntimeError("Database not initialized")
    async with _pool.connection() as conn:
        # One transaction (pool is autocommit): the object purge and its
        # side-table asset cleanup commit together, so a crash can't leave bytes
        # orphaned with their owning row already gone (unrecoverable — no future
        # purge can re-find them).
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
        return len(purged)


# ---------------------------------------------------------------------------
# User CRUD (thin wrappers around objects table)
# ---------------------------------------------------------------------------


async def save_user(user: User) -> BroadcastData:
    """Upsert a user into the objects table."""
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
    """Batch-fetch users by uid, keyed by uid (full projection, same as
    get_user_by_uid). One query instead of N round-trips — the post-finish rating
    recompute would otherwise do one get_user_by_uid per player (400 sequential
    round-trips at a big-event finish). Missing/null-full uids are absent from the
    map, so the caller skips them exactly as the per-uid loop did."""
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


async def delete_user(uid: str) -> None:
    """Delete a user from the database (hard delete)."""
    await delete_object(uid)


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
    fresh create nor be a merge target. ORDER BY uid + LIMIT 1 is a stable pick
    across the legacy dup emails (#368-class data) both callers can encounter.
    """
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
    """Get a user by VEKN ID."""
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
    """Get users whose VEKN ID starts with a given prefix."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND "full"->>'vekn_id' LIKE %s || '%%'""",
            (prefix,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], User) for row in rows]


async def get_princes_and_ncs() -> list[User]:
    """Get all users with Prince or NC roles who have a vekn_prefix."""
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
    """Get users with vekn_id but no coopted_by."""
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
    """Atomically allocate the next available VEKN ID.

    Finds the first gap in existing VEKN IDs starting from 1000000.
    Uses advisory lock to ensure atomic allocation across concurrent requests.
    Returns the allocated VEKN ID as a string (7 digits).
    """
    if not _pool:
        raise RuntimeError("Database not initialized")

    # Minimum VEKN ID to avoid leading zeros (7 digits)
    min_vekn_id = 1000000

    conn = await _pool.getconn()
    try:
        await conn.execute("BEGIN")
        try:
            # Advisory lock to prevent concurrent allocations
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

            if not row or row[0] is None:
                next_id = min_vekn_id
            else:
                next_id = row[0]

            await conn.execute("COMMIT")
            return str(next_id)
        except Exception:
            await conn.execute("ROLLBACK")
            raise
    finally:
        await _pool.putconn(conn)


# Auth methods CRUD
async def insert_auth_method(auth_method: AuthMethod) -> None:
    """Insert a new auth method into the database."""
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO auth_methods (uid, data) VALUES (%s, %s)",
            (auth_method.uid, encode_json(auth_method)),
        )


async def update_auth_method(auth_method: AuthMethod) -> None:
    """Update an existing auth method in the database."""
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
    """Find an auth method by type and identifier (e.g., email address)."""
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
    """Get all auth methods for a user."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM auth_methods WHERE data->>'user_uid' = %s",
            (user_uid,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], AuthMethod) for row in rows]


async def delete_auth_method(uid: str) -> None:
    """Delete an auth method from the database."""
    async with get_connection() as conn:
        await conn.execute("DELETE FROM auth_methods WHERE uid = %s", (uid,))


# ---------------------------------------------------------------------------
# Sanction CRUD (thin wrappers around objects table)
# ---------------------------------------------------------------------------


async def save_sanction(sanction: Sanction) -> BroadcastData:
    """Upsert a sanction into the objects table."""
    return await save_object_from_model(ObjectType.SANCTION, sanction)


async def get_sanction_by_uid(uid: str) -> Sanction | None:
    """Get a sanction by UID."""
    return await get_object_full(uid, Sanction)


async def get_sanctions_for_user(
    user_uid: str, conn: psycopg.AsyncConnection | None = None
) -> list[Sanction]:
    """Get all sanctions for a user."""
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

    Batched replacement for a per-user fan-out loop — one round-trip instead of
    one per player, which matters when called while holding a row lock.
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
    """Hard delete a sanction from the database."""
    await delete_object(uid)


# ---------------------------------------------------------------------------
# Tournament CRUD (thin wrappers around objects table)
# ---------------------------------------------------------------------------


async def save_tournament(tournament: Tournament) -> BroadcastData:
    """Upsert a tournament into the objects table."""
    return await save_object_from_model(ObjectType.TOURNAMENT, tournament)


async def get_tournament_by_uid(
    uid: str, conn: psycopg.AsyncConnection | None = None
) -> Tournament | None:
    """Get a tournament by UID."""
    return await get_object_full(uid, Tournament, conn=conn)


async def delete_tournament_db(uid: str) -> None:
    """Delete a tournament from the database."""
    await delete_object(uid)


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


async def soft_delete_tournament(uid: str) -> tuple[Tournament, BroadcastData] | None:
    """Soft-delete a tournament. Returns (tournament, BroadcastData) for SSE."""
    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        return None
    now = datetime.now(UTC)
    tournament.deleted_at = now
    tournament.modified = now
    bd = await save_tournament(tournament)
    return tournament, bd


async def get_tournament_by_external_id(
    platform: str, ext_id: str
) -> Tournament | None:
    """Get a LIVE tournament by external ID (e.g., platform='vekn', ext_id='123').

    Soft-deleted holders are skipped: the legacy-archon merge tombstones
    round-less duplicates of an event id — matching one here (VEKN tournament
    sync) would refresh a dead copy instead of the surviving tournament.
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


async def get_tournament_wins_for_users(user_uids: set[str]) -> dict[str, list[str]]:
    """Get all-time tournament win UIDs for multiple users at once.

    Returns: {user_uid: [tournament_uid, ...]}
    """
    if not user_uids:
        return {}
    async with get_connection() as conn:
        placeholders = ", ".join(["%s"] * len(user_uids))
        result = await conn.execute(
            f"SELECT uid, \"full\"->>'winner' AS winner FROM objects "  # ty: ignore[invalid-argument-type]
            f"WHERE type = 'tournament' "
            f"AND \"full\"->>'state' = 'Finished' "
            f"AND \"full\"->>'winner' IN ({placeholders}) "
            # Non-VEKN house format: open-rounds / self-organized wins don't count
            # toward the Hall of Fame (mirrors their exclusion from ratings/push).
            f"AND (\"full\"->>'open_rounds') IS DISTINCT FROM 'true' "
            f"AND (\"full\"->>'self_organized_rounds') IS DISTINCT FROM 'true' "
            f"AND deleted_at IS NULL",
            tuple(user_uids),
        )
        rows = await result.fetchall()
        wins: dict[str, list[str]] = {}
        for row in rows:
            t_uid, winner = row[0], row[1]
            wins.setdefault(winner, []).append(t_uid)
        return wins


async def get_finished_tournaments_for_category(
    format_value: str, online: bool, since_date: str
) -> list[Tournament]:
    """Get all FINISHED tournaments matching format/online within date window."""
    async with get_connection() as conn:
        # finish is optional (the engine never stamps it on FinishTournament /
        # FinishFinals) — fall back to start then modified, mirroring the date
        # used for the rating entry itself (ratings.py).
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'tournament'
              AND "full"->>'state' = 'Finished'
              AND "full"->>'format' = %s
              AND ("full"->>'online')::boolean = %s
              AND COALESCE("full"->>'finish', "full"->>'start', "full"->>'modified')::timestamp
                  >= %s::timestamp""",
            (format_value, online, since_date),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Tournament) for row in rows]


# ---------------------------------------------------------------------------
# League CRUD (thin wrappers around objects table)
# ---------------------------------------------------------------------------


async def save_league(league: League) -> BroadcastData:
    """Upsert a league into the objects table."""
    return await save_object_from_model(ObjectType.LEAGUE, league)


async def get_all_leagues(
    conn: psycopg.AsyncConnection | None = None,
) -> list[League]:
    """Get all leagues."""
    async with _acquire(conn) as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'league' AND deleted_at IS NULL""",
        )
        rows = await result.fetchall()
        return [decode_json(row[0], League) for row in rows]


async def get_league_by_uid(uid: str) -> League | None:
    """Get a league by UID."""
    return await get_object_full(uid, League)


async def get_child_leagues(parent_uid: str) -> list[League]:
    """Get child leagues for a meta-league."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'league' AND "full"->>'parent_uid' = %s""",
            (parent_uid,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], League) for row in rows]


async def get_tournaments_for_league(league_uid: str) -> list[Tournament]:
    """Get all tournaments associated with a league."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'tournament' AND "full"->>'league_uid' = %s""",
            (league_uid,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Tournament) for row in rows]


# ---------------------------------------------------------------------------
# Avatar CRUD (stays on avatars table, not a synced object)
# ---------------------------------------------------------------------------


async def upsert_avatar(
    user_uid: str, data: bytes, content_type: str = "image/webp"
) -> None:
    """Insert or update an avatar for a user."""
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
    """Get avatar data and content type for a user. Returns (data, content_type) or None."""
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
    """Delete avatar for a user. Returns True if deleted, False if not found."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM avatars WHERE user_uid = %s RETURNING user_uid",
            (user_uid,),
        )
        row = await result.fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Banner CRUD (per-tournament hero / social image; banners table, not synced)
# ---------------------------------------------------------------------------


async def upsert_banner(
    tournament_uid: str, data: bytes, content_type: str = "image/webp"
) -> None:
    """Insert or update the banner for a tournament."""
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
    """Get banner data and content type. Returns (data, content_type) or None."""
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
    """Delete the banner for a tournament. Returns True if deleted, else False."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM banners WHERE tournament_uid = %s RETURNING tournament_uid",
            (tournament_uid,),
        )
        row = await result.fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Transient Token CRUD (auth challenges, magic links, discord state, etc.)
# ---------------------------------------------------------------------------


async def store_transient_token(key: str, data: dict, expires_at) -> None:
    """Store a transient token with expiry."""
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
    """Get a transient token if not expired. Returns None if missing or expired."""
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
    """Delete a transient token."""
    async with get_connection() as conn:
        await conn.execute("DELETE FROM transient_tokens WHERE key = %s", (key,))


async def cleanup_expired_tokens() -> int:
    """Delete all expired transient tokens. Returns count deleted."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM transient_tokens WHERE expires_at < NOW() RETURNING key"
        )
        rows = await result.fetchall()
        return len(rows)


# ---------------------------------------------------------------------------
# Web Push subscriptions (#314): server-side send credentials, never synced.
# ---------------------------------------------------------------------------


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
