import math
import time

import jwt
from fastapi import Depends, HTTPException, Request

from ..jwt_config import AUDIENCE_API, decode
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


async def require_api_token(request: Request) -> str:
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid authorization header", _CHALLENGE)

    try:
        payload = decode(authorization[7:], AUDIENCE_API)
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
    return payload["client_id"]


class _Budget:
    def __init__(self, per_minute: int, burst: int) -> None:
        self.rate = per_minute / 60
        self.burst = burst
        self.spent: dict[str, tuple[float, float]] = {}

    def spend(self, client_id: str) -> None:
        now = time.monotonic()
        excess, then = self.spent.get(client_id, (-1.0, now))
        excess = max(-1.0, excess - (now - then) * self.rate) + 1
        if excess > self.burst:
            wait = math.ceil((excess - self.burst) / self.rate)
            raise HTTPException(429, "Too many requests", {"Retry-After": str(wait)})
        self.spent[client_id] = (excess, now)


_LOOKUP = _Budget(per_minute=600, burst=100)
_STREAM = _Budget(per_minute=20, burst=10)


async def lookup_budget(client_id: str = Depends(require_api_token)) -> None:
    _LOOKUP.spend(client_id)


async def stream_budget(client_id: str = Depends(require_api_token)) -> None:
    _STREAM.spend(client_id)
