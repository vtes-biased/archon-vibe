"""Email/password register and login endpoints."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid7

import msgspec
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from litestar import Response, post
from litestar.exceptions import HTTPException

from ...db import (
    get_auth_method_by_identifier,
    insert_auth_method,
    save_user,
    update_auth_method,
)
from ...models import AuthMethod, AuthMethodType, User
from ._tokens import (
    TokenResponse,
    assert_account_active,
    create_access_token,
    create_refresh_token,
)

encoder = msgspec.json.Encoder()
ph = PasswordHasher()

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterRequest(msgspec.Struct):
    email: Annotated[str, msgspec.Meta(pattern=EMAIL_PATTERN)]
    password: str
    name: str


class LoginRequest(msgspec.Struct):
    email: Annotated[str, msgspec.Meta(pattern=EMAIL_PATTERN)]
    password: str


@post("/register")
async def register(data: RegisterRequest) -> Response:
    existing = await get_auth_method_by_identifier("email", data.email.lower())
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    now = datetime.now(UTC)
    user = User(
        uid=str(uuid7()),
        modified=now,
        name=data.name,
    )
    await save_user(user)

    password_hash = ph.hash(data.password)
    auth_method = AuthMethod(
        uid=str(uuid7()),
        modified=now,
        user_uid=user.uid,
        method_type=AuthMethodType.EMAIL,
        identifier=data.email.lower(),
        credential_hash=password_hash,
        verified=False,
        created_at=now,
        last_used_at=now,
    )
    await insert_auth_method(auth_method)

    access_token, expires_in = create_access_token(user.uid)
    refresh_token = create_refresh_token(user.uid)

    response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
    return Response(
        content=encoder.encode(response),
        media_type="application/json",
    )


@post("/login")
async def login(data: LoginRequest) -> Response:
    auth_method = await get_auth_method_by_identifier("email", data.email.lower())
    if not auth_method:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    try:
        ph.verify(auth_method.credential_hash, data.password)  # ty: ignore[invalid-argument-type]
    except VerifyMismatchError as err:
        raise HTTPException(
            status_code=401, detail="Invalid email or password"
        ) from err

    if ph.check_needs_rehash(auth_method.credential_hash):  # ty: ignore[invalid-argument-type]
        auth_method = AuthMethod(
            uid=auth_method.uid,
            modified=datetime.now(UTC),
            user_uid=auth_method.user_uid,
            method_type=auth_method.method_type,
            identifier=auth_method.identifier,
            credential_hash=ph.hash(data.password),
            verified=auth_method.verified,
            created_at=auth_method.created_at,
            last_used_at=datetime.now(UTC),
        )
        await update_auth_method(auth_method)
    else:
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

    # A tombstoned account keeps its email credential — block a fresh login.
    await assert_account_active(auth_method.user_uid)

    access_token, expires_in = create_access_token(auth_method.user_uid)
    refresh_token = create_refresh_token(auth_method.user_uid)

    response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
    return Response(
        content=encoder.encode(response),
        media_type="application/json",
    )


handlers = [register, login]
