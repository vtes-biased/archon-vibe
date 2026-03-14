"""Token creation, verification, and refresh."""

from datetime import UTC, datetime, timedelta

import jwt
import msgspec
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ...db import get_user_by_uid
from ...jwt_config import JWT_ALGORITHM, JWT_SECRET

router = APIRouter()
encoder = msgspec.json.Encoder()

# JWT settings
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


class TokenResponse(BaseModel):
    """Token response payload."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class RefreshRequest(BaseModel):
    """Token refresh request payload."""

    refresh_token: str


def create_access_token(user_uid: str) -> tuple[str, int]:
    """Create a short-lived access token (15 minutes)."""
    expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(UTC) + expires_delta
    payload = {
        "sub": user_uid,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, int(expires_delta.total_seconds())


def create_refresh_token(user_uid: str) -> str:
    """Create a long-lived refresh token (7 days)."""
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_uid,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str, expected_type: str = "access") -> str:
    """Verify a JWT token and return the user UID."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
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


@router.post("/refresh")
async def refresh_token_endpoint(request: RefreshRequest) -> Response:
    """Refresh an access token using a refresh token."""
    user_uid = verify_token(request.refresh_token, expected_type="refresh")

    # Verify user still exists
    user = await get_user_by_uid(user_uid)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Generate new tokens
    access_token, expires_in = create_access_token(user_uid)
    # Also issue new refresh token (token rotation for security)
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
