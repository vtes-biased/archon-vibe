import jwt
from fastapi import HTTPException, Request

from ..jwt_config import JWT_ALGORITHM, JWT_SECRET
from ..models import OAuthScope
from .db import get_connection

_CHALLENGE = {"WWW-Authenticate": "Bearer"}


async def _require_live_token(payload: dict) -> None:
    jti = payload.get("jti")
    if not jti:
        raise HTTPException(401, "Invalid token payload", _CHALLENGE)

    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT data->>'revoked' FROM oauth_tokens WHERE data->>'token_jti' = %s",
            (jti,),
        )
        row = await cursor.fetchone()
    if not row or row[0] == "true":
        raise HTTPException(401, "Token has been revoked", _CHALLENGE)


async def _require_active_client(payload: dict) -> None:
    client_id = payload.get("client_id")
    if not client_id or OAuthScope.API_READ not in payload.get("scope", "").split():
        raise HTTPException(401, "Invalid token payload", _CHALLENGE)

    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT data->>'active' FROM oauth_clients WHERE data->>'client_id' = %s",
            (client_id,),
        )
        row = await cursor.fetchone()
    if not row or row[0] != "true":
        raise HTTPException(401, "Client is no longer active", _CHALLENGE)


async def require_api_token(request: Request) -> None:
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header", _CHALLENGE)

    try:
        payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(401, "Token expired", _CHALLENGE) from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(401, "Invalid token", _CHALLENGE) from err

    match payload.get("type"):
        case "oauth_client":
            await _require_active_client(payload)
        case "oauth_access":
            await _require_live_token(payload)
        case _:
            raise HTTPException(401, "Invalid token type", _CHALLENGE)
