"""Database connection and initialization."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import msgspec
import psycopg
from psycopg_pool import AsyncConnectionPool

from .models import (
    AuthMethod,
    League,
    Sanction,
    Tournament,
    User,
)

# Database connection string from environment
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://archon:archon_dev_password@localhost:5433/archon",
)

# Global connection pool
_pool: AsyncConnectionPool | None = None


async def init_db() -> None:
    """Initialize database connection pool and schema."""
    global _pool

    # Create connection pool with autocommit enabled
    _pool = AsyncConnectionPool(
        conninfo=DB_URL,
        min_size=2,
        max_size=20,
        open=False,
        kwargs={"autocommit": True},
    )
    await _pool.open()

    # Create schema if not exists
    async with _pool.connection() as conn:
        # Create trigger function to auto-update modified timestamp
        await conn.execute("""
            CREATE OR REPLACE FUNCTION update_modified_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.modified = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)

        # Auth methods table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_methods (
                uid TEXT PRIMARY KEY,
                modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data JSONB NOT NULL
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_methods_modified
            ON auth_methods(modified);
        """)
        # Index on user_uid for efficient lookups
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_methods_user_uid
            ON auth_methods((data->>'user_uid'));
        """)
        # Unique constraint on method_type + identifier (e.g., only one email per address)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_methods_type_identifier
            ON auth_methods((data->>'method_type'), (data->>'identifier'));
        """)
        await conn.execute("""
            DROP TRIGGER IF EXISTS auth_methods_modified_trigger ON auth_methods;
        """)
        await conn.execute("""
            CREATE TRIGGER auth_methods_modified_trigger
            BEFORE INSERT OR UPDATE ON auth_methods
            FOR EACH ROW
            EXECUTE FUNCTION update_modified_column();
        """)

        # Avatars table - binary storage for user profile images
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS avatars (
                user_uid TEXT PRIMARY KEY,
                data BYTEA NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'image/webp',
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # OAuth tables
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS oauth_clients (
                uid TEXT PRIMARY KEY,
                modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data JSONB NOT NULL
            );
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_oauth_clients_client_id
            ON oauth_clients((data->>'client_id'));
        """)
        await conn.execute("""
            DROP TRIGGER IF EXISTS oauth_clients_modified_trigger ON oauth_clients;
        """)
        await conn.execute("""
            CREATE TRIGGER oauth_clients_modified_trigger
            BEFORE INSERT OR UPDATE ON oauth_clients
            FOR EACH ROW
            EXECUTE FUNCTION update_modified_column();
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
                uid TEXT PRIMARY KEY,
                modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data JSONB NOT NULL
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_oauth_codes_code
            ON oauth_authorization_codes((data->>'code'));
        """)
        await conn.execute("""
            DROP TRIGGER IF EXISTS oauth_codes_modified_trigger ON oauth_authorization_codes;
        """)
        await conn.execute("""
            CREATE TRIGGER oauth_codes_modified_trigger
            BEFORE INSERT OR UPDATE ON oauth_authorization_codes
            FOR EACH ROW
            EXECUTE FUNCTION update_modified_column();
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                uid TEXT PRIMARY KEY,
                modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data JSONB NOT NULL
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_oauth_tokens_jti
            ON oauth_tokens((data->>'token_jti'));
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_oauth_tokens_client_user
            ON oauth_tokens((data->>'client_id'), (data->>'user_uid'));
        """)
        await conn.execute("""
            DROP TRIGGER IF EXISTS oauth_tokens_modified_trigger ON oauth_tokens;
        """)
        await conn.execute("""
            CREATE TRIGGER oauth_tokens_modified_trigger
            BEFORE INSERT OR UPDATE ON oauth_tokens
            FOR EACH ROW
            EXECUTE FUNCTION update_modified_column();
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS oauth_consents (
                uid TEXT PRIMARY KEY,
                modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data JSONB NOT NULL
            );
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_oauth_consents_user_client
            ON oauth_consents((data->>'user_uid'), (data->>'client_id'));
        """)
        await conn.execute("""
            DROP TRIGGER IF EXISTS oauth_consents_modified_trigger ON oauth_consents;
        """)
        await conn.execute("""
            CREATE TRIGGER oauth_consents_modified_trigger
            BEFORE INSERT OR UPDATE ON oauth_consents
            FOR EACH ROW
            EXECUTE FUNCTION update_modified_column();
        """)

        # Transient tokens table (auth challenges, magic links, discord state, etc.)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transient_tokens (
                key TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                expires_at TIMESTAMP NOT NULL
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_transient_tokens_expires
            ON transient_tokens(expires_at);
        """)

        # ---------------------------------------------------------------
        # Unified objects table (users, tournaments, sanctions, leagues, etc.)
        # ---------------------------------------------------------------
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS objects (
                uid TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                modified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP,
                "public" JSONB,
                "member" JSONB,
                "full" JSONB NOT NULL
            );
        """)
        # Composite index for SSE catch-up queries (type + modified_at + uid)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_objects_type_modified
            ON objects(type, modified_at, uid);
        """)
        # Type filter for non-deleted objects
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_objects_type
            ON objects(type) WHERE deleted_at IS NULL;
        """)
        # User-specific lookups
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_objects_user_vekn_id
            ON objects(("full"->>'vekn_id'))
            WHERE type = 'user' AND "full"->>'vekn_id' IS NOT NULL AND "full"->>'vekn_id' != '';
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_objects_user_calendar_token
            ON objects(("full"->>'calendar_token'))
            WHERE type = 'user' AND "full"->>'calendar_token' IS NOT NULL;
        """)
        # Tournament VEKN external ID lookup
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_objects_tournament_vekn
            ON objects(("full"->'external_ids'->>'vekn'))
            WHERE type = 'tournament' AND "full"->'external_ids'->>'vekn' IS NOT NULL;
        """)
        # Deck lookups by tournament and user
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_objects_deck_tournament
            ON objects(("full"->>'tournament_uid'))
            WHERE type = 'deck';
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_objects_deck_user
            ON objects(("full"->>'user_uid'))
            WHERE type = 'deck';
        """)
        # Sanction lookup by user
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_objects_sanction_user
            ON objects(("full"->>'user_uid'))
            WHERE type = 'sanction';
        """)
        # Sanction lookup by tournament
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_objects_sanction_tournament
            ON objects(("full"->>'tournament_uid'))
            WHERE type = 'sanction';
        """)
        # Trigger function for objects table (uses modified_at, not modified)
        await conn.execute("""
            CREATE OR REPLACE FUNCTION update_objects_modified_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.modified_at = CURRENT_TIMESTAMP;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        await conn.execute("""
            DROP TRIGGER IF EXISTS objects_modified_trigger ON objects;
        """)
        await conn.execute("""
            CREATE TRIGGER objects_modified_trigger
            BEFORE INSERT OR UPDATE ON objects
            FOR EACH ROW
            EXECUTE FUNCTION update_objects_modified_at();
        """)

        # Note: vekn_id_counter table is no longer used.
        # VEKN IDs are now allocated by finding the first gap >= 1000000.


async def close_db() -> None:
    """Close database connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterator[psycopg.AsyncConnection]:
    """Get a database connection from the pool."""
    if not _pool:
        raise RuntimeError("Database not initialized")
    async with _pool.connection() as conn:
        yield conn


@asynccontextmanager
async def tournament_transaction(
    uid: str,
) -> AsyncIterator[tuple[Tournament | None, psycopg.AsyncConnection]]:
    """Lock a tournament row for update within a transaction.

    Uses SELECT ... FOR UPDATE to serialize concurrent writes to the same
    tournament. Yields (tournament, connection). The caller must use the
    yielded connection for any UPDATE within the same transaction.
    Commits on normal exit, rolls back on exception.
    """
    if not _pool:
        raise RuntimeError("Database not initialized")
    async with _pool.connection() as conn:
        async with conn.transaction():
            result = await conn.execute(
                'SELECT "full" FROM objects WHERE uid = %s FOR UPDATE',
                (uid,),
            )
            row = await result.fetchone()
            tournament = decode_json(row[0], Tournament) if row else None
            yield tournament, conn


# JSON encoder/decoder
_encoder = msgspec.json.Encoder()
_decoder = msgspec.json.Decoder()


def encode_json(obj: msgspec.Struct) -> str:
    """Encode a msgspec Struct to JSON string."""
    return _encoder.encode(obj).decode("utf-8")


def decode_json[T](data: str | dict, type_: type[T]) -> T:
    """Decode JSON string or dict to a msgspec Struct."""
    decoder = msgspec.json.Decoder(type_)
    if isinstance(data, dict):
        # Convert dict back to JSON string for msgspec
        data = _encoder.encode(data).decode("utf-8")
    return decoder.decode(data)


# ---------------------------------------------------------------------------
# Unified objects table operations
# ---------------------------------------------------------------------------

from .access_levels import compute_full, compute_member, compute_public  # noqa: E402
from .models import DeckObject  # noqa: E402


async def get_decks_for_tournament(tournament_uid: str) -> list[DeckObject]:
    """Get all DeckObjects for a tournament (uses idx_objects_deck_tournament)."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full"::text FROM objects WHERE type = 'deck' AND "full"->>'tournament_uid' = %s""",
            (tournament_uid,),
        )
        rows = await result.fetchall()
    return [msgspec.json.decode(row[0].encode(), type=DeckObject) for row in rows]


async def save_object(
    obj_type: str,
    uid: str,
    full_data: dict,
    *,
    conn: psycopg.AsyncConnection | None = None,
    deleted_at: str | None = None,
) -> None:
    """Save an object to the unified objects table.

    Computes public/member/full projections and upserts.
    If conn is provided, uses that connection (for transactions).
    """
    pub = compute_public(obj_type, full_data)
    mem = compute_member(obj_type, full_data)
    full = compute_full(obj_type, full_data)

    # Serialize to JSON strings for JSONB columns
    pub_json = _encoder.encode(pub).decode("utf-8") if pub is not None else None
    mem_json = _encoder.encode(mem).decode("utf-8") if mem is not None else None
    full_json = _encoder.encode(full).decode("utf-8")

    query = """
        INSERT INTO objects (uid, type, deleted_at, "public", "member", "full")
        VALUES (%s, %s, %s::timestamp, %s::jsonb, %s::jsonb, %s::jsonb)
        ON CONFLICT (uid) DO UPDATE SET
            type = EXCLUDED.type,
            deleted_at = EXCLUDED.deleted_at,
            "public" = EXCLUDED."public",
            "member" = EXCLUDED."member",
            "full" = EXCLUDED."full"
    """
    params = (uid, obj_type, deleted_at, pub_json, mem_json, full_json)

    if conn:
        await conn.execute(query, params)
    else:
        async with get_connection() as c:
            await c.execute(query, params)


async def save_object_from_model(
    obj_type: str,
    obj: msgspec.Struct,
) -> None:
    """Save a msgspec model to the objects table."""
    full_data = msgspec.to_builtins(obj)
    deleted_at = full_data.get("deleted_at")
    # Convert deleted_at to string if it's not None
    if deleted_at is not None and not isinstance(deleted_at, str):
        deleted_at = deleted_at.isoformat() if hasattr(deleted_at, "isoformat") else str(deleted_at)
    await save_object(obj_type, obj.uid, full_data, deleted_at=deleted_at)


async def delete_object(uid: str, *, conn: psycopg.AsyncConnection | None = None) -> None:
    """Hard delete an object from the objects table."""
    query = "DELETE FROM objects WHERE uid = %s"
    if conn:
        await conn.execute(query, (uid,))
    else:
        async with get_connection() as c:
            await c.execute(query, (uid,))


def _level_col(level: str) -> str:
    """Map access level name to quoted SQL column name."""
    return {"public": '"public"', "member": '"member"', "full": '"full"'}.get(level, '"full"')


async def get_object(
    uid: str, *, level: str = "full"
) -> dict | None:
    """Get an object from the objects table at a given access level.

    Returns the raw dict (parsed from JSONB), or None if not found
    or not visible at the requested level.
    """
    col = _level_col(level)
    async with get_connection() as conn:
        result = await conn.execute(
            f"SELECT {col} FROM objects WHERE uid = %s",
            (uid,),
        )
        row = await result.fetchone()
        if row and row[0] is not None:
            return row[0] if isinstance(row[0], dict) else msgspec.json.decode(row[0])
        return None


async def get_object_full[T](uid: str, type_: type[T]) -> T | None:
    """Get an object from the objects table, decoded into a typed model."""
    async with get_connection() as conn:
        result = await conn.execute(
            'SELECT "full" FROM objects WHERE uid = %s',
            (uid,),
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
        result = await conn.execute(query, all_params)
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
) -> AsyncIterator[tuple[list[str], str]]:
    """Stream pre-serialized JSON strings from objects table.

    Yields (batch_of_json_strings, max_modified_at) tuples.
    Each string is the raw JSONB text — no Python deserialization needed.
    """
    if not _pool:
        raise RuntimeError("Database not initialized")

    col = _level_col(level)
    cursor_modified: str | None = since
    cursor_uid: str | None = None

    while True:
        async with _pool.connection() as conn:
            conditions = [f"{col} IS NOT NULL"]
            bind_params: list = []

            if obj_type:
                conditions.append("type = %s")
                bind_params.append(obj_type)

            if cursor_uid is not None:
                conditions.append("(modified_at, uid) > (%s, %s)")
                bind_params.extend([cursor_modified, cursor_uid])
            elif cursor_modified:
                conditions.append("modified_at > %s")
                bind_params.append(cursor_modified)

            where = " AND ".join(conditions)
            bind_params.append(batch_size)

            rows = await (await conn.execute(
                f"SELECT {col}::text, modified_at, uid FROM objects "
                f"WHERE {where} ORDER BY modified_at ASC, uid ASC LIMIT %s",
                tuple(bind_params),
            )).fetchall()

        if not rows:
            break

        json_strings = [row[0] for row in rows]
        cursor_modified = rows[-1][1].isoformat()
        cursor_uid = rows[-1][2]

        yield json_strings, cursor_modified

        if len(rows) < batch_size:
            break


async def purge_deleted_objects(days: int = 30) -> int:
    """Hard-delete objects that were soft-deleted more than `days` ago."""
    if not _pool:
        raise RuntimeError("Database not initialized")
    async with _pool.connection() as conn:
        result = await conn.execute(
            "DELETE FROM objects WHERE deleted_at < NOW() - make_interval(days => %s)",
            (days,),
        )
        return result.rowcount or 0


# ---------------------------------------------------------------------------
# User CRUD (thin wrappers around objects table)
# ---------------------------------------------------------------------------


async def insert_user(user: User) -> None:
    """Insert a new user into the database."""
    await save_object_from_model("user", user)


async def update_user(user: User) -> None:
    """Update an existing user in the database."""
    await save_object_from_model("user", user)


async def get_user_by_uid(uid: str) -> User | None:
    """Get a user by UID."""
    return await get_object_full(uid, User)


async def set_user_resync_after(user_uid: str) -> None:
    """Set resync_after to now() on a user, triggering full resync on next SSE connect."""
    from datetime import UTC, datetime

    user = await get_user_by_uid(user_uid)
    if not user:
        return
    user.resync_after = datetime.now(UTC)
    await update_user(user)


async def delete_user(uid: str) -> None:
    """Delete a user from the database (hard delete)."""
    await delete_object(uid)


async def soft_delete_user(uid: str) -> User | None:
    """Soft-delete a user by setting deleted_at. Returns updated user for SSE."""
    from datetime import UTC, datetime

    user = await get_user_by_uid(uid)
    if not user:
        return None
    now = datetime.now(UTC)
    user.deleted_at = now
    user.modified = now
    await update_user(user)
    return user


async def get_user_by_contact_email(email: str) -> User | None:
    """Find a user by contact_email for account merging."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND LOWER("full"->>'contact_email') = LOWER(%s)""",
            (email,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], User)
        return None


async def get_user_by_calendar_token(token: str) -> User | None:
    """Lookup user by calendar subscription token."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND "full"->>'calendar_token' = %s LIMIT 1""",
            (token,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], User)
        return None


async def get_user_by_vekn_id(vekn_id: str) -> User | None:
    """Get a user by VEKN ID."""
    async with get_connection() as conn:
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
    method_type: str, identifier: str
) -> AuthMethod | None:
    """Find an auth method by type and identifier (e.g., email address)."""
    async with get_connection() as conn:
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


async def reassign_auth_methods(from_user_uid: str, to_user_uid: str) -> int:
    """Reassign all auth methods from one user to another. Returns count updated."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM auth_methods WHERE data->>'user_uid' = %s",
            (from_user_uid,),
        )
        rows = await result.fetchall()

        count = 0
        for row in rows:
            auth_method = decode_json(row[0], AuthMethod)
            updated = AuthMethod(
                uid=auth_method.uid,
                modified=auth_method.modified,
                user_uid=to_user_uid,
                method_type=auth_method.method_type,
                identifier=auth_method.identifier,
                credential_hash=auth_method.credential_hash,
                verified=auth_method.verified,
                created_at=auth_method.created_at,
                last_used_at=auth_method.last_used_at,
            )
            await conn.execute(
                "UPDATE auth_methods SET data = %s WHERE uid = %s",
                (encode_json(updated), auth_method.uid),
            )
            count += 1

        return count


async def reassign_sanctions(from_user_uid: str, to_user_uid: str) -> int:
    """Reassign all sanctions from one user to another. Returns count updated."""
    sanctions = await get_sanctions_for_user(from_user_uid)
    count = 0
    for sanction in sanctions:
        updated = Sanction(
            uid=sanction.uid,
            modified=sanction.modified,
            user_uid=to_user_uid,
            issued_by_uid=sanction.issued_by_uid,
            tournament_uid=sanction.tournament_uid,
            level=sanction.level,
            category=sanction.category,
            description=sanction.description,
            issued_at=sanction.issued_at,
            expires_at=sanction.expires_at,
            lifted_at=sanction.lifted_at,
            lifted_by_uid=sanction.lifted_by_uid,
            deleted_at=sanction.deleted_at,
        )
        await update_sanction(updated)
        count += 1
    return count


async def reassign_coopted_by_references(from_user_uid: str, to_user_uid: str) -> int:
    """Update all users whose coopted_by references from_user_uid to point to to_user_uid."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND "full"->>'coopted_by' = %s""",
            (from_user_uid,),
        )
        rows = await result.fetchall()

    count = 0
    for row in rows:
        user = decode_json(row[0], User)
        user.coopted_by = to_user_uid
        await update_user(user)
        count += 1

    return count


async def merge_users(keep_uid: str, delete_uid: str) -> User | None:
    """Merge two user accounts.

    Transfers all auth methods from delete_uid to keep_uid,
    merges user data (preferring non-empty values from keep_uid),
    reassigns sanctions and coopted_by references,
    then deletes the duplicate account.

    Returns the merged user or None if keep_uid doesn't exist.
    """
    keep_user = await get_user_by_uid(keep_uid)
    delete_user_obj = await get_user_by_uid(delete_uid)

    if not keep_user:
        return None
    if not delete_user_obj:
        return keep_user  # Nothing to merge

    # Merge user data - prefer keep_user for identity (name, vekn_id, roles),
    # but prefer delete_user (the claiming user) for contact info
    merged = User(
        uid=keep_user.uid,
        modified=keep_user.modified,
        name=keep_user.name or delete_user_obj.name,
        country=keep_user.country or delete_user_obj.country,
        vekn_id=keep_user.vekn_id or delete_user_obj.vekn_id,
        city=keep_user.city or delete_user_obj.city,
        state=keep_user.state or delete_user_obj.state,
        nickname=delete_user_obj.nickname or keep_user.nickname,
        roles=list(set(keep_user.roles) | set(delete_user_obj.roles)),  # Union of roles
        avatar_path=delete_user_obj.avatar_path or keep_user.avatar_path,
        contact_email=delete_user_obj.contact_email or keep_user.contact_email,
        contact_discord=delete_user_obj.contact_discord or keep_user.contact_discord,
        contact_phone=delete_user_obj.contact_phone or keep_user.contact_phone,
        coopted_by=keep_user.coopted_by or delete_user_obj.coopted_by,
        coopted_at=keep_user.coopted_at or delete_user_obj.coopted_at,
        vekn_synced=keep_user.vekn_synced or delete_user_obj.vekn_synced,
        vekn_synced_at=keep_user.vekn_synced_at or delete_user_obj.vekn_synced_at,
        local_modifications=keep_user.local_modifications
        | delete_user_obj.local_modifications,
        vekn_prefix=keep_user.vekn_prefix or delete_user_obj.vekn_prefix,
    )

    await update_user(merged)
    await reassign_auth_methods(delete_uid, keep_uid)
    await reassign_sanctions(delete_uid, keep_uid)
    await reassign_coopted_by_references(delete_uid, keep_uid)
    await soft_delete_user(delete_uid)

    return merged


async def strip_vekn_from_user(user_uid: str) -> tuple[User, User] | None:
    """Displace a user from their VEKN record.

    Creates a new user with auth methods and contact info.
    The VEKN user keeps: uid, vekn_id, roles, name, country, city.
    Returns (displaced_new_user, stripped_vekn_user) or None if not found.
    """
    from datetime import UTC, datetime

    from uuid6 import uuid7

    user = await get_user_by_uid(user_uid)
    if not user:
        return None

    new_uid = str(uuid7())
    now = datetime.now(UTC)
    displaced = User(
        uid=new_uid,
        modified=now,
        name=user.name,
        country=user.country,
        vekn_id=None,
        city=user.city,
        state=user.state,
        nickname=user.nickname,
        roles=[],
        avatar_path=user.avatar_path,
        contact_email=user.contact_email,
        contact_discord=user.contact_discord,
        contact_phone=user.contact_phone,
    )
    await insert_user(displaced)
    await reassign_auth_methods(user_uid, new_uid)

    stripped = User(
        uid=user.uid,
        modified=now,
        name=user.name,
        country=user.country,
        vekn_id=user.vekn_id,
        city=user.city,
        state=user.state,
        nickname=None,
        roles=user.roles,
        avatar_path=None,
        contact_email=None,
        contact_discord=None,
        contact_phone=None,
        coopted_by=user.coopted_by,
        coopted_at=user.coopted_at,
        vekn_synced=user.vekn_synced,
        vekn_synced_at=user.vekn_synced_at,
        local_modifications=set(),
        vekn_prefix=user.vekn_prefix,
    )
    await update_user(stripped)

    return displaced, stripped


async def split_user_from_vekn(user_uid: str) -> User | None:
    """Split a user away from their VEKN record.

    Creates a new user with the personal data and auth methods.
    The old user becomes an orphaned VEKN record (no auth, no personal data).
    Returns the new user (with auth methods) or None if not found.
    """
    from datetime import UTC, datetime

    from uuid6 import uuid7

    user = await get_user_by_uid(user_uid)
    if not user:
        return None

    new_uid = str(uuid7())
    now = datetime.now(UTC)
    new_user = User(
        uid=new_uid,
        modified=now,
        name=user.name,
        country=user.country,
        vekn_id=None,
        city=user.city,
        state=user.state,
        nickname=user.nickname,
        roles=[],
        avatar_path=user.avatar_path,
        contact_email=user.contact_email,
        contact_discord=user.contact_discord,
        contact_phone=user.contact_phone,
    )
    await insert_user(new_user)

    stripped = User(
        uid=user.uid,
        modified=user.modified,
        name=user.name,
        country=user.country,
        vekn_id=user.vekn_id,
        city=user.city,
        state=user.state,
        nickname=None,
        roles=user.roles,
        avatar_path=None,
        contact_email=None,
        contact_discord=None,
        contact_phone=None,
        coopted_by=None,
        coopted_at=None,
        vekn_synced=user.vekn_synced,
        vekn_synced_at=user.vekn_synced_at,
        local_modifications=set(),
        vekn_prefix=None,
    )
    await update_user(stripped)
    await reassign_auth_methods(user_uid, new_uid)
    await reassign_sanctions(user_uid, new_uid)

    return new_user


# ---------------------------------------------------------------------------
# Sanction CRUD (thin wrappers around objects table)
# ---------------------------------------------------------------------------


async def insert_sanction(sanction: Sanction) -> None:
    """Insert a new sanction into the database."""
    await save_object_from_model("sanction", sanction)


async def update_sanction(sanction: Sanction) -> None:
    """Update an existing sanction in the database."""
    await save_object_from_model("sanction", sanction)


async def get_sanction_by_uid(uid: str) -> Sanction | None:
    """Get a sanction by UID."""
    return await get_object_full(uid, Sanction)


async def get_sanctions_for_user(user_uid: str) -> list[Sanction]:
    """Get all sanctions for a user."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'sanction' AND "full"->>'user_uid' = %s
            ORDER BY "full"->>'issued_at' DESC""",
            (user_uid,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Sanction) for row in rows]


async def get_sanctions_for_tournament(tournament_uid: str) -> list[Sanction]:
    """Get all non-deleted sanctions for a tournament."""
    async with get_connection() as conn:
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


async def insert_tournament(tournament: Tournament) -> None:
    """Insert a new tournament into the database."""
    await save_object_from_model("tournament", tournament)


async def update_tournament(tournament: Tournament) -> None:
    """Update an existing tournament in the database."""
    await save_object_from_model("tournament", tournament)


async def get_tournament_by_uid(uid: str) -> Tournament | None:
    """Get a tournament by UID."""
    return await get_object_full(uid, Tournament)


async def delete_tournament_db(uid: str) -> None:
    """Delete a tournament from the database."""
    await delete_object(uid)


async def soft_delete_tournament(uid: str) -> Tournament | None:
    """Soft-delete a tournament by setting deleted_at. Returns updated tournament for SSE."""
    from datetime import UTC, datetime

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        return None
    now = datetime.now(UTC)
    tournament.deleted_at = now
    tournament.modified = now
    await update_tournament(tournament)
    return tournament


async def get_tournament_by_external_id(platform: str, ext_id: str) -> Tournament | None:
    """Get a tournament by external ID (e.g., platform='vekn', ext_id='123')."""
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'tournament' AND "full"->'external_ids'->>%s = %s LIMIT 1""",
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
            f"""SELECT uid, "full"->>'winner' AS winner FROM objects
            WHERE type = 'tournament'
              AND "full"->>'state' = 'Finished'
              AND "full"->>'winner' IN ({placeholders})
              AND deleted_at IS NULL""",
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
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'tournament'
              AND "full"->>'state' = 'Finished'
              AND "full"->>'format' = %s
              AND ("full"->>'online')::boolean = %s
              AND ("full"->>'finish')::timestamp >= %s::timestamp""",
            (format_value, online, since_date),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Tournament) for row in rows]


# ---------------------------------------------------------------------------
# League CRUD (thin wrappers around objects table)
# ---------------------------------------------------------------------------


async def insert_league(league: League) -> None:
    """Insert a new league into the database."""
    await save_object_from_model("league", league)


async def update_league(league: League) -> None:
    """Update an existing league in the database."""
    await save_object_from_model("league", league)


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


async def upsert_avatar(user_uid: str, data: bytes, content_type: str = "image/webp") -> None:
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
            return msgspec.json.decode(row[0]) if isinstance(row[0], (str, bytes)) else row[0]
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
