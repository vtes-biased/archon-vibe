"""Email/password register and login endpoints."""

from datetime import UTC, datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, EmailStr
from uuid6 import uuid7

from ...db import (
    get_auth_method_by_identifier,
    insert_auth_method,
    insert_user,
    update_auth_method,
)
from ...models import AuthMethod, AuthMethodType, User
from ._tokens import TokenResponse, create_access_token, create_refresh_token

router = APIRouter()
ph = PasswordHasher()


class RegisterRequest(BaseModel):
    """Registration request payload."""

    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    """Login request payload."""

    email: EmailStr
    password: str


@router.post("/register", status_code=201)
async def register(request: RegisterRequest) -> Response:
    """Register a new user with email and password.

    Creates both a User and an AuthMethod record.
    """
    # Check if email already exists
    existing = await get_auth_method_by_identifier("email", request.email.lower())
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create user
    now = datetime.now(UTC)
    user = User(
        uid=str(uuid7()),
        modified=now,
        name=request.name,
    )
    await insert_user(user)

    # Create auth method with hashed password
    password_hash = ph.hash(request.password)
    auth_method = AuthMethod(
        uid=str(uuid7()),
        modified=now,
        user_uid=user.uid,
        method_type=AuthMethodType.EMAIL,
        identifier=request.email.lower(),
        credential_hash=password_hash,
        verified=False,  # Email verification not implemented yet
        created_at=now,
        last_used_at=now,
    )
    await insert_auth_method(auth_method)

    # Generate tokens
    access_token, expires_in = create_access_token(user.uid)
    refresh_token = create_refresh_token(user.uid)

    response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
    return Response(
        content=response.model_dump_json(),
        media_type="application/json",
        status_code=201,
    )


@router.post("/login")
async def login(request: LoginRequest) -> Response:
    """Login with email and password."""
    # Find auth method
    auth_method = await get_auth_method_by_identifier("email", request.email.lower())
    if not auth_method:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Verify password
    try:
        ph.verify(auth_method.credential_hash, request.password)  # ty: ignore[invalid-argument-type]
    except VerifyMismatchError as err:
        raise HTTPException(
            status_code=401, detail="Invalid email or password"
        ) from err

    # Check if password needs rehashing (argon2 parameter updates)
    if ph.check_needs_rehash(auth_method.credential_hash):  # ty: ignore[invalid-argument-type]
        auth_method = AuthMethod(
            uid=auth_method.uid,
            modified=datetime.now(UTC),
            user_uid=auth_method.user_uid,
            method_type=auth_method.method_type,
            identifier=auth_method.identifier,
            credential_hash=ph.hash(request.password),
            verified=auth_method.verified,
            created_at=auth_method.created_at,
            last_used_at=datetime.now(UTC),
        )
        await update_auth_method(auth_method)
    else:
        # Just update last_used_at
        auth_method = AuthMethod(
            uid=auth_method.uid,
            modified=datetime.now(UTC),
            user_uid=auth_method.user_uid,
            method_type=auth_method.method_type,
            identifier=auth_method.identifier,
            credential_hash=auth_method.credential_hash,
            verified=auth_method.verified,
            created_at=auth_method.created_at,
            last_used_at=datetime.now(UTC),
        )
        await update_auth_method(auth_method)

    # Generate tokens
    access_token, expires_in = create_access_token(auth_method.user_uid)
    refresh_token = create_refresh_token(auth_method.user_uid)

    response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
    return Response(
        content=response.model_dump_json(),
        media_type="application/json",
    )
