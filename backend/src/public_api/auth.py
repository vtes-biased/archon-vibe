import math
import time

import jwt
from litestar.connection import ASGIConnection
from litestar.exceptions import HTTPException
from litestar.handlers import BaseRouteHandler

from ..jwt_config import AUDIENCE_API, decode
from ..models import OAuthScope
from .db import get_connection

_CHALLENGE = {"WWW-Authenticate": "Bearer"}


async def _require_live_token(payload: dict) -> None:
    jti = payload.get("jti")
    if not jti:
        raise HTTPException(
            status_code=401, detail="Invalid token payload", headers=_CHALLENGE
        )

    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT data->>'revoked' FROM oauth_tokens WHERE data->>'token_jti' = %s",
            (jti,),
        )
        row = await cursor.fetchone()
    if not row or row[0] == "true":
        raise HTTPException(
            status_code=401, detail="Token has been revoked", headers=_CHALLENGE
        )


async def _require_active_client(payload: dict) -> None:
    client_id = payload.get("client_id")
    if not client_id or OAuthScope.API_READ not in payload.get("scope", "").split():
        raise HTTPException(
            status_code=401, detail="Invalid token payload", headers=_CHALLENGE
        )

    async with get_connection() as conn:
        cursor = await conn.execute(
            "SELECT data->>'active' FROM oauth_clients WHERE data->>'client_id' = %s",
            (client_id,),
        )
        row = await cursor.fetchone()
    if not row or row[0] != "true":
        raise HTTPException(
            status_code=401, detail="Client is no longer active", headers=_CHALLENGE
        )


async def require_api_token(connection: ASGIConnection) -> str:
    authorization = connection.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header",
            headers=_CHALLENGE,
        )

    try:
        payload = decode(authorization[7:], AUDIENCE_API)
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=401, detail="Token expired", headers=_CHALLENGE
        ) from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=401, detail="Invalid token", headers=_CHALLENGE
        ) from err

    match payload.get("type"):
        case "oauth_client":
            await _require_active_client(payload)
        case "oauth_access":
            await _require_live_token(payload)
        case _:
            raise HTTPException(
                status_code=401, detail="Invalid token type", headers=_CHALLENGE
            )
    connection.state.app_token = payload["type"] == "oauth_client"
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
            raise HTTPException(
                status_code=429,
                detail="Too many requests",
                headers={"Retry-After": str(wait)},
            )
        self.spent[client_id] = (excess, now)


_LOOKUP = _Budget(per_minute=600, burst=100)
_STREAM = _Budget(per_minute=20, burst=10)


async def lookup_budget(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    _LOOKUP.spend(await require_api_token(connection))


async def stream_budget(connection: ASGIConnection, _: BaseRouteHandler) -> None:
    client_id = await require_api_token(connection)
    _LOOKUP.spend(client_id)
    _STREAM.spend(client_id)
