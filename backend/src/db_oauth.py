"""OAuth database CRUD operations."""

from .db import decode_json, encode_json, get_connection
from .models import (
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    OAuthToken,
)


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
                    uid=t.uid,
                    modified=t.modified,
                    token_jti=t.token_jti,
                    client_id=t.client_id,
                    user_uid=t.user_uid,
                    scopes=t.scopes,
                    token_type=t.token_type,
                    expires_at=t.expires_at,
                    revoked=True,
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
