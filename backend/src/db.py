"""Database connection and initialization."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import msgspec
import psycopg
from psycopg_pool import AsyncConnectionPool

from .models import (
    AuthMethod,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    OAuthToken,
    Rating,
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
        max_size=10,
        open=False,
        kwargs={"autocommit": True},
    )
    await _pool.open()

    # Create schema if not exists
    async with _pool.connection() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                uid TEXT PRIMARY KEY,
                modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data JSONB NOT NULL
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_modified ON users(modified);
        """)
        # Unique constraint on vekn_id (partial index - only for non-null values)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_vekn_id
            ON users((data->>'vekn_id'))
            WHERE data->>'vekn_id' IS NOT NULL AND data->>'vekn_id' != '';
        """)

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

        # Create trigger for users table
        await conn.execute("""
            DROP TRIGGER IF EXISTS users_modified_trigger ON users;
        """)
        await conn.execute("""
            CREATE TRIGGER users_modified_trigger
            BEFORE INSERT OR UPDATE ON users
            FOR EACH ROW
            EXECUTE FUNCTION update_modified_column();
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

        # Sanctions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sanctions (
                uid TEXT PRIMARY KEY,
                modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data JSONB NOT NULL
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sanctions_modified
            ON sanctions(modified);
        """)
        # Index on user_uid for efficient lookups (who received the sanction)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sanctions_user_uid
            ON sanctions((data->>'user_uid'));
        """)
        await conn.execute("""
            DROP TRIGGER IF EXISTS sanctions_modified_trigger ON sanctions;
        """)
        await conn.execute("""
            CREATE TRIGGER sanctions_modified_trigger
            BEFORE INSERT OR UPDATE ON sanctions
            FOR EACH ROW
            EXECUTE FUNCTION update_modified_column();
        """)

        # Tournaments table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                uid TEXT PRIMARY KEY,
                modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data JSONB NOT NULL
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tournaments_modified
            ON tournaments(modified);
        """)
        # Index for external_ids lookups (VEKN sync)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tournaments_external_vekn
            ON tournaments((data->'external_ids'->>'vekn'))
            WHERE data->'external_ids'->>'vekn' IS NOT NULL;
        """)
        await conn.execute("""
            DROP TRIGGER IF EXISTS tournaments_modified_trigger ON tournaments;
        """)
        await conn.execute("""
            CREATE TRIGGER tournaments_modified_trigger
            BEFORE INSERT OR UPDATE ON tournaments
            FOR EACH ROW
            EXECUTE FUNCTION update_modified_column();
        """)

        # Ratings table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                uid TEXT PRIMARY KEY,
                modified TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                data JSONB NOT NULL
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ratings_modified ON ratings(modified);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ratings_user_uid
            ON ratings((data->>'user_uid'));
        """)
        await conn.execute("""
            DROP TRIGGER IF EXISTS ratings_modified_trigger ON ratings;
        """)
        await conn.execute("""
            CREATE TRIGGER ratings_modified_trigger
            BEFORE INSERT OR UPDATE ON ratings
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


async def insert_user(user: User) -> None:
    """Insert a new user into the database."""
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO users (uid, data) VALUES (%s, %s)",
            (user.uid, encode_json(user)),
        )


async def update_user(user: User) -> None:
    """Update an existing user in the database."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET data = %s WHERE uid = %s",
            (encode_json(user), user.uid),
        )


async def set_user_resync_after(user_uid: str) -> None:
    """Set resync_after to now() on a user, triggering full resync on next SSE connect."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET data = jsonb_set(data, '{resync_after}', to_jsonb(now()::text)) WHERE uid = %s",
            (user_uid,),
        )


async def stream_objects[T](
    table: str, type_: type[T], since: str | None = None, batch_size: int = 1000
) -> AsyncIterator[tuple[list[T], str | None]]:
    """Stream objects in batches using a server-side cursor.

    Yields (batch, max_modified) tuples. Uses true streaming from DB
    for constant memory usage regardless of dataset size.
    """
    if not _pool:
        raise RuntimeError("Database not initialized")

    conn = await _pool.getconn()
    try:
        await conn.execute("BEGIN")
        try:
            async with conn.cursor(name=f"{table}_stream") as cursor:
                if since:
                    await cursor.execute(
                        f"SELECT data, modified FROM {table} "
                        "WHERE modified > %s ORDER BY modified ASC, uid ASC",
                        (since,),
                    )
                else:
                    await cursor.execute(
                        f"SELECT data, modified FROM {table} "
                        "ORDER BY modified ASC, uid ASC",
                    )

                batch: list[T] = []
                last_modified: str | None = None

                async for row in cursor:
                    obj = decode_json(row[0], type_)
                    batch.append(obj)
                    last_modified = row[1].isoformat()

                    if len(batch) >= batch_size:
                        yield batch, last_modified
                        batch = []

                if batch:
                    yield batch, last_modified
        finally:
            try:
                await conn.cancel_safe()
            except Exception:
                pass
            try:
                await conn.execute("ROLLBACK")
            except Exception:
                pass
    finally:
        await _pool.putconn(conn)


def stream_users(
    since: str | None = None, batch_size: int = 1000
) -> AsyncIterator[tuple[list[User], str | None]]:
    """Stream users from DB."""
    return stream_objects("users", User, since=since, batch_size=batch_size)


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


async def get_user_by_uid(uid: str) -> User | None:
    """Get a user by UID."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM users WHERE uid = %s",
            (uid,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], User)
        return None


# Sanctions CRUD
async def insert_sanction(sanction: Sanction) -> None:
    """Insert a new sanction into the database."""
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO sanctions (uid, data) VALUES (%s, %s)",
            (sanction.uid, encode_json(sanction)),
        )


async def update_sanction(sanction: Sanction) -> None:
    """Update an existing sanction in the database."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE sanctions SET data = %s WHERE uid = %s",
            (encode_json(sanction), sanction.uid),
        )


async def get_sanctions_for_user(user_uid: str) -> list[Sanction]:
    """Get all sanctions for a user."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM sanctions WHERE data->>'user_uid' = %s ORDER BY data->>'issued_at' DESC",
            (user_uid,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Sanction) for row in rows]


async def delete_user(uid: str) -> None:
    """Delete a user from the database."""
    async with get_connection() as conn:
        await conn.execute("DELETE FROM users WHERE uid = %s", (uid,))


async def delete_auth_method(uid: str) -> None:
    """Delete an auth method from the database."""
    async with get_connection() as conn:
        await conn.execute("DELETE FROM auth_methods WHERE uid = %s", (uid,))


async def reassign_auth_methods(from_user_uid: str, to_user_uid: str) -> int:
    """Reassign all auth methods from one user to another. Returns count updated."""
    async with get_connection() as conn:
        # Get all auth methods for the source user
        result = await conn.execute(
            "SELECT data FROM auth_methods WHERE data->>'user_uid' = %s",
            (from_user_uid,),
        )
        rows = await result.fetchall()

        count = 0
        for row in rows:
            auth_method = decode_json(row[0], AuthMethod)
            # Update user_uid in the data
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
    async with get_connection() as conn:
        # Get all sanctions for the source user
        result = await conn.execute(
            "SELECT data FROM sanctions WHERE data->>'user_uid' = %s",
            (from_user_uid,),
        )
        rows = await result.fetchall()

        count = 0
        for row in rows:
            sanction = decode_json(row[0], Sanction)
            # Update user_uid in the data
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
            await conn.execute(
                "UPDATE sanctions SET data = %s WHERE uid = %s",
                (encode_json(updated), sanction.uid),
            )
            count += 1

        return count


async def reassign_coopted_by_references(from_user_uid: str, to_user_uid: str) -> int:
    """Update all users whose coopted_by references from_user_uid to point to to_user_uid."""
    async with get_connection() as conn:
        # Get all users who were coopted by the source user
        result = await conn.execute(
            "SELECT data FROM users WHERE data->>'coopted_by' = %s",
            (from_user_uid,),
        )
        rows = await result.fetchall()

        count = 0
        for row in rows:
            user = decode_json(row[0], User)
            # Update coopted_by to point to the new user
            updated = User(
                uid=user.uid,
                modified=user.modified,
                name=user.name,
                country=user.country,
                vekn_id=user.vekn_id,
                city=user.city,
                state=user.state,
                nickname=user.nickname,
                roles=user.roles,
                avatar_path=user.avatar_path,
                contact_email=user.contact_email,
                contact_discord=user.contact_discord,
                contact_phone=user.contact_phone,
                coopted_by=to_user_uid,
                coopted_at=user.coopted_at,
                vekn_synced=user.vekn_synced,
                vekn_synced_at=user.vekn_synced_at,
                local_modifications=user.local_modifications,
                vekn_prefix=user.vekn_prefix,
            )
            await conn.execute(
                "UPDATE users SET data = %s WHERE uid = %s",
                (encode_json(updated), user.uid),
            )
            count += 1

        return count


async def get_user_by_contact_email(email: str) -> User | None:
    """Find a user with DISCORD auth method whose contact_email matches.

    This is used to find Discord users by their contact_email for account merging
    when a magic link login proves ownership of that email.
    """
    async with get_connection() as conn:
        # Find users with matching contact_email
        result = await conn.execute(
            "SELECT data FROM users WHERE LOWER(data->>'contact_email') = LOWER(%s)",
            (email,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], User)
        return None


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

    # Merge user data - prefer keep_user values, but fill in blanks from delete_user
    merged = User(
        uid=keep_user.uid,
        modified=keep_user.modified,
        name=keep_user.name or delete_user_obj.name,
        country=keep_user.country or delete_user_obj.country,
        vekn_id=keep_user.vekn_id or delete_user_obj.vekn_id,
        city=keep_user.city or delete_user_obj.city,
        state=keep_user.state or delete_user_obj.state,
        nickname=keep_user.nickname or delete_user_obj.nickname,
        roles=list(set(keep_user.roles) | set(delete_user_obj.roles)),  # Union of roles
        avatar_path=keep_user.avatar_path or delete_user_obj.avatar_path,
        contact_email=keep_user.contact_email or delete_user_obj.contact_email,
        contact_discord=keep_user.contact_discord or delete_user_obj.contact_discord,
        contact_phone=keep_user.contact_phone or delete_user_obj.contact_phone,
        coopted_by=keep_user.coopted_by or delete_user_obj.coopted_by,
        coopted_at=keep_user.coopted_at or delete_user_obj.coopted_at,
        vekn_synced=keep_user.vekn_synced or delete_user_obj.vekn_synced,
        vekn_synced_at=keep_user.vekn_synced_at or delete_user_obj.vekn_synced_at,
        local_modifications=keep_user.local_modifications
        | delete_user_obj.local_modifications,
        vekn_prefix=keep_user.vekn_prefix or delete_user_obj.vekn_prefix,
    )

    # Update the kept user with merged data
    await update_user(merged)

    # Reassign auth methods
    await reassign_auth_methods(delete_uid, keep_uid)

    # Reassign sanctions received by the deleted user
    await reassign_sanctions(delete_uid, keep_uid)

    # Reassign coopted_by references (users who were coopted by deleted user)
    await reassign_coopted_by_references(delete_uid, keep_uid)

    # Delete the duplicate user
    await delete_user(delete_uid)

    return merged


async def get_user_by_vekn_id(vekn_id: str) -> User | None:
    """Get a user by VEKN ID."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM users WHERE data->>'vekn_id' = %s LIMIT 1",
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
    # Check if user has any auth methods
    auth_methods = await get_auth_methods_for_user(user.uid)
    return len(auth_methods) > 0


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

            # Find the first gap in VEKN IDs starting from min_vekn_id
            # This query finds the smallest number >= min_vekn_id that isn't used
            result = await conn.execute(
                """
                WITH used_ids AS (
                    SELECT (data->>'vekn_id')::integer AS vekn_id
                    FROM users
                    WHERE data->>'vekn_id' IS NOT NULL
                      AND data->>'vekn_id' ~ '^[0-9]+$'
                      AND (data->>'vekn_id')::integer >= %s
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
                # No used IDs yet, start at min
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


async def strip_vekn_from_user(user_uid: str) -> User | None:
    """Strip VEKN-related data from a user (abandonment/displacement).

    Clears: auth_methods, roles, coopted_by/at, contact info
    Keeps: vekn_id, name, vekn_synced (orphaned record)

    Returns the updated user or None if not found.
    """
    user = await get_user_by_uid(user_uid)
    if not user:
        return None

    # Delete all auth methods for this user
    auth_methods = await get_auth_methods_for_user(user_uid)
    for auth_method in auth_methods:
        await delete_auth_method(auth_method.uid)

    # Update user - clear roles and contact info but keep vekn_id
    stripped = User(
        uid=user.uid,
        modified=user.modified,
        name=user.name,
        country=user.country,
        vekn_id=user.vekn_id,  # Keep VEKN ID
        city=user.city,
        state=user.state,
        nickname=None,  # Clear
        roles=[],  # Clear all roles
        avatar_path=None,  # Clear
        contact_email=None,  # Clear
        contact_discord=None,  # Clear
        contact_phone=None,  # Clear
        coopted_by=None,  # Clear
        coopted_at=None,  # Clear
        vekn_synced=user.vekn_synced,  # Keep sync status
        vekn_synced_at=user.vekn_synced_at,
        local_modifications=set(),  # Clear
        vekn_prefix=None,  # Clear
    )

    await update_user(stripped)
    return stripped


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

    # Create new user with personal data, no vekn_id
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

    # Strip old user: clear personal data, keep vekn_id (orphaned)
    stripped = User(
        uid=user.uid,
        modified=user.modified,
        name=user.name,
        country=user.country,
        vekn_id=user.vekn_id,
        city=user.city,
        state=user.state,
        nickname=None,
        roles=user.roles,  # Roles follow the VEKN ID
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

    # Reassign auth methods and sanctions to new user
    await reassign_auth_methods(user_uid, new_uid)
    await reassign_sanctions(user_uid, new_uid)

    return new_user


async def get_users_by_vekn_prefix(prefix: str) -> list[User]:
    """Get users whose VEKN ID starts with a given prefix."""
    async with get_connection() as conn:
        result = await conn.execute(
            """
            SELECT data FROM users
            WHERE data->>'vekn_id' LIKE %s || '%%'
            """,
            (prefix,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], User) for row in rows]


async def get_princes_and_ncs() -> list[User]:
    """Get all users with Prince or NC roles who have a vekn_prefix."""
    async with get_connection() as conn:
        result = await conn.execute(
            """
            SELECT data FROM users
            WHERE data->>'vekn_prefix' IS NOT NULL
              AND data->>'vekn_prefix' != ''
            """
        )
        rows = await result.fetchall()
        return [decode_json(row[0], User) for row in rows]


# Sanction streaming and cleanup functions
def stream_sanctions(
    since: str | None = None, batch_size: int = 1000
) -> AsyncIterator[tuple[list[Sanction], str | None]]:
    """Stream sanctions from DB."""
    return stream_objects("sanctions", Sanction, since=since, batch_size=batch_size)


async def get_sanction_by_uid(uid: str) -> Sanction | None:
    """Get a sanction by UID."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM sanctions WHERE uid = %s",
            (uid,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], Sanction)
        return None


async def get_expired_sanctions() -> list[Sanction]:
    """Get sanctions that should be auto-expired (>18 months, not permanent, not deleted).

    Excludes:
    - Permanent bans (SUSPENSION without expires_at)
    - Already soft-deleted sanctions
    - Sanctions within 18 months
    """
    async with get_connection() as conn:
        # 18 months = ~548 days
        result = await conn.execute(
            """
            SELECT data FROM sanctions
            WHERE data->>'deleted_at' IS NULL
              AND data->>'issued_at' IS NOT NULL
              AND (data->>'issued_at')::timestamp < NOW() - INTERVAL '18 months'
              AND NOT (
                  data->>'level' = 'suspension'
                  AND data->>'expires_at' IS NULL
              )
            """
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Sanction) for row in rows]


async def get_sanctions_for_cleanup(days: int = 30) -> list[Sanction]:
    """Get soft-deleted sanctions older than N days for hard deletion."""
    async with get_connection() as conn:
        result = await conn.execute(
            """
            SELECT data FROM sanctions
            WHERE data->>'deleted_at' IS NOT NULL
              AND (data->>'deleted_at')::timestamp < NOW() - INTERVAL '%s days'
            """,
            (days,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Sanction) for row in rows]


async def delete_sanction_hard(uid: str) -> None:
    """Hard delete a sanction from the database."""
    async with get_connection() as conn:
        await conn.execute("DELETE FROM sanctions WHERE uid = %s", (uid,))


# Avatar CRUD
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


# Tournament CRUD
async def insert_tournament(tournament: Tournament) -> None:
    """Insert a new tournament into the database."""
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO tournaments (uid, data) VALUES (%s, %s)",
            (tournament.uid, encode_json(tournament)),
        )


async def update_tournament(tournament: Tournament) -> None:
    """Update an existing tournament in the database."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE tournaments SET data = %s WHERE uid = %s",
            (encode_json(tournament), tournament.uid),
        )


async def get_tournament_by_uid(uid: str) -> Tournament | None:
    """Get a tournament by UID."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM tournaments WHERE uid = %s",
            (uid,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], Tournament)
        return None


async def delete_tournament_db(uid: str) -> None:
    """Delete a tournament from the database."""
    async with get_connection() as conn:
        await conn.execute("DELETE FROM tournaments WHERE uid = %s", (uid,))


def stream_tournaments(
    since: str | None = None, batch_size: int = 1000
) -> AsyncIterator[tuple[list[Tournament], str | None]]:
    """Stream tournaments from DB."""
    return stream_objects("tournaments", Tournament, since=since, batch_size=batch_size)


# OAuth CRUD


async def insert_oauth_client(client: OAuthClient) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO oauth_clients (uid, data) VALUES (%s, %s)",
            (client.uid, encode_json(client)),
        )


async def update_oauth_client(client: OAuthClient) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE oauth_clients SET data = %s WHERE uid = %s",
            (encode_json(client), client.uid),
        )


async def get_oauth_client_by_client_id(client_id: str) -> OAuthClient | None:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM oauth_clients WHERE data->>'client_id' = %s",
            (client_id,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], OAuthClient)
        return None


async def get_oauth_clients_by_owner(user_uid: str) -> list[OAuthClient]:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM oauth_clients WHERE data->>'created_by_uid' = %s ORDER BY modified DESC",
            (user_uid,),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], OAuthClient) for row in rows]


async def insert_oauth_code(code: OAuthAuthorizationCode) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO oauth_authorization_codes (uid, data) VALUES (%s, %s)",
            (code.uid, encode_json(code)),
        )


async def get_oauth_code(code: str) -> OAuthAuthorizationCode | None:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM oauth_authorization_codes WHERE data->>'code' = %s",
            (code,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], OAuthAuthorizationCode)
        return None


async def update_oauth_code(code_obj: OAuthAuthorizationCode) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE oauth_authorization_codes SET data = %s WHERE uid = %s",
            (encode_json(code_obj), code_obj.uid),
        )


async def insert_oauth_token(token: OAuthToken) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "INSERT INTO oauth_tokens (uid, data) VALUES (%s, %s)",
            (token.uid, encode_json(token)),
        )


async def get_oauth_token_by_jti(jti: str) -> OAuthToken | None:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM oauth_tokens WHERE data->>'token_jti' = %s",
            (jti,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], OAuthToken)
        return None


async def update_oauth_token(token: OAuthToken) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE oauth_tokens SET data = %s WHERE uid = %s",
            (encode_json(token), token.uid),
        )


async def revoke_oauth_token_chain(parent_token_uid: str) -> int:
    """Revoke all tokens in a refresh chain by parent_token_uid."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM oauth_tokens WHERE data->>'parent_token_uid' = %s OR uid = %s",
            (parent_token_uid, parent_token_uid),
        )
        rows = await result.fetchall()
        count = 0
        for row in rows:
            t = decode_json(row[0], OAuthToken)
            if not t.revoked:
                revoked = OAuthToken(
                    uid=t.uid, modified=t.modified, token_jti=t.token_jti,
                    client_id=t.client_id, user_uid=t.user_uid, scopes=t.scopes,
                    token_type=t.token_type, expires_at=t.expires_at, revoked=True,
                    parent_token_uid=t.parent_token_uid,
                )
                await conn.execute(
                    "UPDATE oauth_tokens SET data = %s WHERE uid = %s",
                    (encode_json(revoked), revoked.uid),
                )
                count += 1
        return count


async def get_oauth_consent(user_uid: str, client_id: str) -> OAuthConsent | None:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM oauth_consents WHERE data->>'user_uid' = %s AND data->>'client_id' = %s",
            (user_uid, client_id),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], OAuthConsent)
        return None


async def upsert_oauth_consent(consent: OAuthConsent) -> None:
    async with get_connection() as conn:
        existing = await get_oauth_consent(consent.user_uid, consent.client_id)
        if existing:
            await conn.execute(
                "UPDATE oauth_consents SET data = %s WHERE uid = %s",
                (encode_json(consent), existing.uid),
            )
        else:
            await conn.execute(
                "INSERT INTO oauth_consents (uid, data) VALUES (%s, %s)",
                (consent.uid, encode_json(consent)),
            )


async def cleanup_expired_oauth_codes() -> int:
    """Delete expired authorization codes."""
    async with get_connection() as conn:
        result = await conn.execute(
            """
            DELETE FROM oauth_authorization_codes
            WHERE (data->>'expires_at')::timestamp < NOW()
            RETURNING uid
            """
        )
        rows = await result.fetchall()
        return len(rows)


async def cleanup_expired_oauth_tokens() -> int:
    """Delete expired and revoked tokens older than 7 days."""
    async with get_connection() as conn:
        result = await conn.execute(
            """
            DELETE FROM oauth_tokens
            WHERE (data->>'revoked')::boolean = true
              AND (data->>'expires_at')::timestamp < NOW() - INTERVAL '7 days'
            RETURNING uid
            """
        )
        rows = await result.fetchall()
        return len(rows)


# Rating CRUD


async def upsert_rating(rating: Rating) -> None:
    """Insert or update a rating."""
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO ratings (uid, data) VALUES (%s, %s)
            ON CONFLICT (uid) DO UPDATE SET data = EXCLUDED.data
            """,
            (rating.uid, encode_json(rating)),
        )


async def get_rating_by_user_uid(user_uid: str) -> Rating | None:
    """Get a rating by user UID."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM ratings WHERE data->>'user_uid' = %s LIMIT 1",
            (user_uid,),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], Rating)
        return None


async def delete_rating(uid: str) -> None:
    """Delete a rating from the database."""
    async with get_connection() as conn:
        await conn.execute("DELETE FROM ratings WHERE uid = %s", (uid,))


def stream_ratings(
    since: str | None = None, batch_size: int = 1000
) -> AsyncIterator[tuple[list[Rating], str | None]]:
    """Stream ratings from DB."""
    return stream_objects("ratings", Rating, since=since, batch_size=batch_size)


async def get_tournament_by_external_id(platform: str, ext_id: str) -> Tournament | None:
    """Get a tournament by external ID (e.g., platform='vekn', ext_id='123')."""
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM tournaments WHERE data->'external_ids'->>%s = %s LIMIT 1",
            (platform, ext_id),
        )
        row = await result.fetchone()
        if row:
            return decode_json(row[0], Tournament)
        return None


async def get_finished_tournaments_for_category(
    format_value: str, online: bool, since_date: str
) -> list[Tournament]:
    """Get all FINISHED tournaments matching format/online within date window."""
    async with get_connection() as conn:
        result = await conn.execute(
            """
            SELECT data FROM tournaments
            WHERE data->>'state' = 'Finished'
              AND data->>'format' = %s
              AND (data->>'online')::boolean = %s
              AND (data->>'finish')::timestamp >= %s::timestamp
            """,
            (format_value, online, since_date),
        )
        rows = await result.fetchall()
        return [decode_json(row[0], Tournament) for row in rows]
