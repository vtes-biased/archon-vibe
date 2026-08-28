"""Authentication middleware and dependencies."""

from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request

from ..db import get_user_by_uid
from ..db_oauth import get_oauth_token_by_jti
from ..jwt_config import JWT_ALGORITHM, JWT_SECRET
from ..models import User

# Sub-routes of the token's own tournament an OAuth actor never reaches, whatever
# the user's capabilities: the infrastructure of running the event, not running it.
_OAUTH_BARRED_SUBPATHS = frozenset(
    {
        "organizers",
        "push-vekn",
        "go-offline",
        "go-online",
        "force-takeover",
        "force-unlock",
        "sync-offline",
        "qr-checkin",
        "archon-import",
    }
)


def _oauth_allows(request: Request, tournament_uid: str) -> bool:
    """The whole reach of a tournament-scoped `user:impersonate` token. An
    allowlist, so a route added anywhere else in the app is refused until it is
    named here."""
    path = request.url.path
    if path.startswith("/oauth/"):
        return True
    if path == "/sanctions/":
        return request.method == "POST"
    if path == "/sanctions/reference":
        return request.method == "GET"
    if path == "/stream":
        return request.query_params.get("tournament") == tournament_uid

    segments = path.strip("/").split("/")
    if segments[:3] != ["api", "tournaments", tournament_uid]:
        return False
    if request.method == "DELETE" and len(segments) == 3:
        return False
    return len(segments) < 4 or segments[3] not in _OAUTH_BARRED_SUBPATHS


async def get_current_user(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Resolves both regular access tokens and OAuth access tokens; a
    profile:read token reaches /oauth/* only, and a user:impersonate token is
    scoped to one tournament and the allowlist above."""
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

            scopes = scope.split() if scope else []
            tournament_uid = payload.get("tournament")
            request.state.oauth_scopes = scopes
            request.state.oauth_client_id = client_id
            request.state.oauth_tournament = tournament_uid

            if "user:impersonate" not in scopes:
                if not request.url.path.startswith("/oauth/"):
                    raise HTTPException(
                        status_code=403,
                        detail="This token only grants access to OAuth endpoints (profile:read)",
                    )
            elif not tournament_uid or not _oauth_allows(request, tournament_uid):
                raise HTTPException(
                    status_code=403,
                    detail="This token acts only on the tournament it was granted for",
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


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
