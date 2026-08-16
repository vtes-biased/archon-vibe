"""Authentication middleware and dependencies."""

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request

from ..db import get_user_by_uid
from ..db_oauth import get_oauth_token_by_jti
from ..jwt_config import JWT_ALGORITHM, JWT_SECRET
from ..models import User


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolves both regular access tokens and OAuth access tokens; OAuth
    tokens without user:impersonate scope are restricted to /oauth/*."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        token_type = payload.get("type")

        if token_type == "access":
            user_uid = payload.get("sub")
            if not user_uid:
                raise HTTPException(status_code=401, detail="Invalid token payload")

        elif token_type == "oauth_access":
            user_uid = payload.get("sub")
            jti = payload.get("jti")
            scope = payload.get("scope", "")
            client_id = payload.get("client_id")

            if not user_uid or not jti or not client_id:
                raise HTTPException(
                    status_code=401, detail="Invalid OAuth token payload"
                )

            token_record = await get_oauth_token_by_jti(jti)
            if not token_record or token_record.revoked:
                raise HTTPException(status_code=401, detail="Token has been revoked")

            path = request.url.path
            if path.startswith("/auth/") or path.startswith("/admin/"):
                raise HTTPException(
                    status_code=403,
                    detail="OAuth tokens cannot access auth or admin endpoints",
                )

            request.state.oauth_scopes = scope.split() if scope else []
            request.state.oauth_client_id = client_id

            scopes = scope.split() if scope else []
            if "user:impersonate" not in scopes:
                if not path.startswith("/oauth/"):
                    raise HTTPException(
                        status_code=403,
                        detail="This token only grants access to OAuth endpoints (profile:read)",
                    )

        else:
            raise HTTPException(status_code=401, detail="Invalid token type")

    except jwt.ExpiredSignatureError as err:
        raise HTTPException(
            status_code=401,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    user = await get_user_by_uid(user_uid)
    # deleted_at is set only by soft_delete_user (delete/merge) — this is the
    # single resolution point every first-party handler funnels through.
    if not user or user.deleted_at:
        raise HTTPException(status_code=401, detail="User not found")

    return user


async def get_optional_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None

    try:
        return await get_current_user(request, authorization)
    except HTTPException:
        return None


def require_permission(check: Callable[[User], bool], detail: str):
    """Only for capabilities that need nothing but the actor — anything scoped
    to a target or resource is checked inside the handler instead."""

    async def gate(user: User = Depends(get_current_user)) -> User:
        if not check(user):
            raise HTTPException(status_code=403, detail=detail)
        return user

    return gate


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
