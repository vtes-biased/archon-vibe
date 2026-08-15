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
    Promo,
    PromoLedgerEntry,
    PromoLedgerKind,
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
async def batch_read_connection(
    statement_timeout_ms: int = 120_000,
) -> AsyncIterator[psycopg.AsyncConnection]:
    """Pooled connection with a relaxed statement_timeout for internal batch jobs
    (snapshot gen, VEKN push) whose full-corpus reads outlast the 30s user-request
    guard when this shared VPS's disk is latency-bound.

    Autocommit pool has no reset hook, so RESET on release stops the relaxed
    timeout leaking to the next borrower. int() interpolation: SET can't bind-param.
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
# Access-version fingerprint (SSE connect handshake) — see wiki/sync.md
# ---------------------------------------------------------------------------

# Global wire-shape lever: bump on any change to the projected JSON shape that does
# NOT also ride a frontend DB_VERSION bump (a field rename/remove in models.py, an
# access_levels projection-policy change, a nested engine-struct change). One bump
# flips every client's fingerprint → exactly one resync. The narrow backstop, not
# the primary mechanism (a DB_VERSION bump self-heals client-side).
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
    roles, the country that scopes an NC's overlay, and the tournaments they
    organize. A mismatch at connect ⇒ the cached corpus predates an entitlement
    change a since-delta can't repair ⇒ resync. Backend-only + opaque: the client
    stores + echoes it, never parses it, so the inputs stay server-evolvable.
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
    *,
    conn: psycopg.AsyncConnection | None = None,
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
    return await save_object(
        obj_type, obj.uid, full_data, conn=conn, deleted_at=deleted_at
    )  # ty: ignore[unresolved-attribute]


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
    """Stream pre-serialized JSON in keyset-paginated batches — the monotonic,
    `since`-ordered path for SSE catch-up and the full-corpus rating recompute.

    Each batch acquires a pooled connection, fetches up to `batch_size` rows ordered
    by (modified_at, uid), then RELEASES the connection BEFORE yielding — so a slow
    SSE client never pins a pool slot across its catch-up, and app heap holds at most
    one batch (not the whole resultset). This bounds the full-corpus reads a single
    fetchall would otherwise materialize per connection: a no-`since` rating recompute,
    or a large catch-up delta. Keyset continuation on (modified_at, uid) is tie-safe
    across batch boundaries (a same-timestamp run split by the LIMIT is neither skipped
    nor duplicated) and rides the idx_objects_type_modified (type, modified_at, uid) index.

    The ORDER BY is load-bearing here (the `since` high-water mark must advance
    monotonically); a full snapshot needs no order and takes the cheaper unordered
    sequential scan instead — see stream_objects_snapshot. Yields
    (batch_of_raw_json_strings, max_modified_at_in_batch) per non-empty batch.
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
        async with _pool.connection() as c:
            rows = await (await c.execute(sql, (*params, batch_size))).fetchall()

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
) -> AsyncIterator[list[tuple[str, str | None, str | None, str | None]]]:
    """Stream the WHOLE live corpus once — every type, all three levels per row.

    ONE unordered sequential scan feeds all three snapshot files. The previous shape
    (one query per type per level) issued len(ObjectType) x 3 = 18 queries, each of
    which the planner answers with a full heap scan for the big types: ~477MB of heap
    reads per cycle to emit ~20MB of gzip, every 15 minutes, on a latency-bound disk.
    Selecting the three level columns of the same row together drops that to 1x heap +
    1x toast for the same detoast volume.

    No ORDER BY: a full snapshot needs no row order, and dropping it frees the planner
    to choose a seq/bitmap heap scan (physical page order = sequential I/O) over an
    index scan (index-order heap access = random I/O). Note the plan is costed with
    cursor_tuple_fraction (a named cursor is a DECLARE), so verify with EXPLAIN of the
    DECLARE, not of the bare SELECT.

    Consistency comes free: a DECLAREd cursor holds ONE MVCC snapshot for its whole
    lifetime even under READ COMMITTED, so all three files describe the same instant
    without needing REPEATABLE READ. The cursor bounds app heap to one fetch; it is
    DECLAREd inside an explicit transaction (autocommit forbids a bare DECLARE CURSOR)
    spanning the iteration — the gaps between FETCHes are just gzip writes (ms).
    `batch_size` is deliberately far below the ordered streamer's 1000: rows now carry
    three projections of the same object, and a tournament averages ~8KB per level.

    The transaction/cursor live inside this generator but the `conn` is caller-owned, so
    the caller MUST drive it under contextlib.aclosing (or fully drain it) — an early
    break/exception then unwinds the cursor+ROLLBACK deterministically before the conn
    is released, instead of at GC on a connection the pool may have already re-lent.
    Yields batches of (type, public, member, full); a level is None where that
    projection doesn't exist for the row, and the caller omits it from that file.
    """
    sql = (
        'SELECT type, "public"::text, "member"::text, "full"::text '
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
    # Minimum VEKN ID to avoid leading zeros (7 digits)
    min_vekn_id = 1000000

    if not _pool:
        raise RuntimeError("Database not initialized")
    async with _pool.connection() as conn:
        async with conn.transaction():
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
            return str(row[0]) if row and row[0] is not None else str(min_vekn_id)


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


async def save_tournament(
    tournament: Tournament, *, conn: psycopg.AsyncConnection
) -> BroadcastData:
    """Upsert a tournament. `conn` is REQUIRED: every whole-row tournament write
    must run on a caller-supplied connection — inside tournament_transaction(uid)
    for an existing row (so a concurrent /action commit can't be lost to a stale
    read-modify-write), or a plain get_connection() for a fresh uuid7 (creation)
    or bulk seed. Non-optional so an unlocked tournament write can no longer be typed."""
    return await save_object_from_model(ObjectType.TOURNAMENT, tournament, conn=conn)


async def get_tournament_by_uid(
    uid: str, conn: psycopg.AsyncConnection | None = None
) -> Tournament | None:
    """Get a tournament by UID."""
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
    """Soft-delete a tournament and cascade to its decks and sanctions.

    Returns (tournament, [tournament_bd, *deck_bds, *sanction_bds]) so the caller
    broadcasts a tombstone for the tournament AND each dependent object — otherwise
    they linger, live and orphaned (a deck pointing at a gone event, a DQ/SA still
    on the player's record), in every client's IndexedDB. All writes share the
    tournament's row-lock transaction, so the cascade is atomic.
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


# Same-event matcher for the two import paths that create tournaments without a
# shared key: the VEKN tournament sync (keyed on external_ids.vekn) and the
# legacy-archon merge (keyed on the old uid / external_ids.archon / the old
# extra.vekn_id). A legacy event that never carried a vekn id is invisible to both
# keys, so each path used to insert its own copy of the one real event.
#
# Name is compared case- and whitespace-insensitively; start within 24h rather
# than on the calendar date because the two paths derive the instant differently
# (the sync applies a guessed venue timezone, the ETL takes old archon's stored
# value) — the observed skew reaches 9h and can straddle midnight UTC.
#
# Name+day is NOT an identity key on its own: legacy imports share placeholder
# names ("Imported VTES Event" covers hundreds of distinct 2005 events, dozens on
# one Saturday), and one convention runs several same-named events in a day. It is
# only evidence of identity when unambiguous — callers must apply the guards in
# their own docstrings, never merge on a bare hit.
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
    declared stay in, since most legacy imports have none.
    """
    if not name or start is None:
        return []
    async with get_connection() as conn:
        result = await conn.execute(
            SAME_EVENT_QUERY, (exclude_uid, name, start.isoformat())
        )
        found = [decode_json(row[0], Tournament) for row in await result.fetchall()]
    if country:
        found = [t for t in found if not t.country or t.country == country]
    return found


# The #520 class: several live copies of ONE event where at least one copy holds a
# vekn id and at least one holds none. Grouping by external_ids.vekn (the
# one-live-per-vekn-id invariant check) cannot see it — the extra copies have no
# vekn id at all.
#
# The mixed-vekn clause is load-bearing, not a refinement: without it this reports
# every same-name/same-day cluster, and legacy placeholder names make that
# hundreds of DISTINCT events (each with its own vekn id) rather than duplicates.
# Copies that ALL hold vekn ids are a different class — one event entered twice on
# vekn.net — resolvable locally only once one of the ids is deleted there (see
# BOTH_VEKN_GROUPS_QUERY below).
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


# Same-name/same-day groups where EVERY copy holds a (different) vekn id. Most are
# DISTINCT events sharing a legacy placeholder name, not duplicates — only a VEKN
# API probe can tell (one id confirmed deleted marks a resolvable double-entry), so
# this feeds the operator dedup script only, never the sync's end-of-run logging.
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


async def get_tournament_wins_for_users(user_uids: set[str]) -> dict[str, list[str]]:
    """Get all-time IRL tournament win UIDs for multiple users at once.

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
            # Official VEKN HoF convention counts IRL wins only.
            f"AND (\"full\"->>'online') IS DISTINCT FROM 'true' "
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
    """Get all live FINISHED tournaments matching format/online within date window."""
    async with get_connection() as conn:
        # finish is optional (the engine never stamps it on FinishTournament /
        # FinishFinals) — fall back to start then modified, mirroring the date
        # used for the rating entry itself (ratings.py).
        # deleted_at IS NULL: a soft-deleted tournament keeps state='Finished', so
        # without this it would still feed ratings (and never drop out on delete).
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


# ---------------------------------------------------------------------------
# League CRUD (thin wrappers around objects table)
# ---------------------------------------------------------------------------


async def save_league(league: League) -> BroadcastData:
    """Upsert a league into the objects table."""
    return await save_object_from_model(ObjectType.LEAGUE, league)


async def save_promo(promo: Promo) -> BroadcastData:
    """Upsert a promo into the objects table."""
    return await save_object_from_model(ObjectType.PROMO, promo)


async def get_promo_by_uid(uid: str) -> Promo | None:
    """Get a promo by UID."""
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


async def upsert_promo_image(
    promo_uid: str, data: bytes, content_type: str = "image/webp"
) -> None:
    """Insert or update the image for a promo."""
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
    """Get promo image data and content type, or None."""
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
    """Delete the image for a promo. Returns True if deleted, else False."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM promo_images WHERE promo_uid = %s RETURNING promo_uid",
            (promo_uid,),
        )
        row = await result.fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Promo ledger (side table, not synced — see the wiki/sync.md carve-out)
# ---------------------------------------------------------------------------

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
