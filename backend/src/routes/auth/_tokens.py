"""Token creation, verification, and refresh."""

from datetime import UTC, datetime, timedelta

import jwt
import msgspec
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ...db import get_user_by_uid
from ...jwt_config import AUDIENCE_APP, decode, sign

router = APIRouter()
encoder = msgspec.json.Encoder()

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


def create_access_token(user_uid: str) -> tuple[str, int]:
    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(UTC) + expires_delta
    payload = {
        "sub": user_uid,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return sign(payload, AUDIENCE_APP), int(expires_delta.total_seconds())


def create_refresh_token(user_uid: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_uid,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return sign(payload, AUDIENCE_APP)


def verify_token(token: str, expected_type: str = "access") -> str:
    try:
        payload = decode(token, AUDIENCE_APP)
        if payload.get("type") != expected_type:
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_uid = payload.get("sub")
        if not user_uid:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return user_uid
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(status_code=401, detail="Token expired") from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err


async def assert_account_active(user_uid: str) -> None:
    """A soft-deleted user keeps its auth_method rows, so a surviving credential
    must re-check deleted_at before minting — the same guard get_current_user
    and /auth/refresh apply."""
    user = await get_user_by_uid(user_uid)
    if not user or user.deleted_at:
        raise HTTPException(status_code=403, detail="This account is no longer active")


@router.post("/refresh")
async def refresh_token_endpoint(request: RefreshRequest) -> Response:
    user_uid = verify_token(request.refresh_token, expected_type="refresh")

    # Refresh mints a fresh 7d token pair, so an IC-deleted/merge-absorbed
    # account must not renew here.
    user = await get_user_by_uid(user_uid)
    if not user or user.deleted_at:
        raise HTTPException(status_code=401, detail="User not found")

    access_token, expires_in = create_access_token(user_uid)
    new_refresh_token = create_refresh_token(user_uid)

    response = TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=expires_in,
    )
    return Response(
        content=response.model_dump_json(),
        media_type="application/json",
    )
