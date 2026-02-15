"""OAuth 2.0 Authorization Server (RFC 6749 + RFC 7636 PKCE)."""

import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import jwt
import msgspec
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from uuid6 import uuid7

from ..db import get_user_by_uid
from ..db_oauth import (
    get_oauth_client_by_client_id,
    get_oauth_clients_by_owner,
    get_oauth_code,
    get_oauth_consent,
    get_oauth_token_by_jti,
    insert_oauth_client,
    insert_oauth_code,
    insert_oauth_token,
    revoke_oauth_token_chain,
    update_oauth_client,
    update_oauth_code,
    update_oauth_token,
    upsert_oauth_consent,
)
from ..middleware.auth import JWT_ALGORITHM, JWT_SECRET, CurrentUser, require_role
from ..models import (
    User,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    OAuthScope,
    OAuthToken,
    Role,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])

ph = PasswordHasher()

# Token lifetimes
ACCESS_TOKEN_LIFETIME = timedelta(hours=1)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)
AUTH_CODE_LIFETIME = timedelta(seconds=60)


# --- Helpers ---


def _generate_client_id() -> str:
    return secrets.token_urlsafe(24)[:32]


def _generate_client_secret() -> str:
    return secrets.token_urlsafe(48)


def _generate_auth_code() -> str:
    return secrets.token_urlsafe(48)[:64]


def _verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """Verify PKCE S256 challenge."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    import base64
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return computed == code_challenge


def _create_oauth_jwt(
    user_uid: str,
    token_type: str,
    scopes: list[OAuthScope],
    client_id: str,
    jti: str,
    lifetime: timedelta,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_uid,
        "type": f"oauth_{token_type}",
        "scope": " ".join(scopes),
        "client_id": client_id,
        "jti": jti,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _parse_scopes(scope_str: str) -> list[OAuthScope]:
    """Parse space-separated scope string into validated OAuthScope list."""
    scopes = []
    for s in scope_str.split():
        try:
            scopes.append(OAuthScope(s))
        except ValueError:
            raise HTTPException(400, f"Invalid scope: {s}")
    return scopes


# --- Authorization Endpoints ---


@router.get("/authorize")
async def authorize_get(
    request: Request,
    user: CurrentUser,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "",
):
    """Validate OAuth authorization request parameters. Returns JSON with authorization details
    or redirects with code if consent already exists."""
    # Validate response_type
    if response_type != "code":
        raise HTTPException(400, "Only response_type=code is supported")

    # Validate PKCE
    if not code_challenge or code_challenge_method != "S256":
        raise HTTPException(400, "PKCE with S256 is required")

    # Validate client
    client = await get_oauth_client_by_client_id(client_id)
    if not client or not client.active:
        raise HTTPException(400, "Invalid client_id")

    # Validate redirect_uri (exact match)
    if redirect_uri not in client.redirect_uris:
        raise HTTPException(400, "Invalid redirect_uri")

    # Validate scopes
    requested_scopes = _parse_scopes(scope)
    for s in requested_scopes:
        if s not in client.scopes:
            raise HTTPException(400, f"Scope {s} not allowed for this client")

    # Check existing consent
    consent = await get_oauth_consent(user.uid, client_id)
    if consent and set(requested_scopes).issubset(set(consent.scopes)):
        # Auto-approve: generate code and redirect
        code_value = _generate_auth_code()
        now = datetime.now(UTC)
        auth_code = OAuthAuthorizationCode(
            uid=str(uuid7()),
            modified=now,
            code=code_value,
            client_id=client_id,
            user_uid=user.uid,
            redirect_uri=redirect_uri,
            scopes=requested_scopes,
            code_challenge=code_challenge,
            expires_at=now + AUTH_CODE_LIFETIME,
        )
        await insert_oauth_code(auth_code)

        params = {"code": code_value}
        if state:
            params["state"] = state
        return RedirectResponse(
            url=f"{redirect_uri}?{urlencode(params)}", status_code=302
        )

    # No consent yet — return authorization details for consent screen
    return {
        "client_name": client.name,
        "scopes": [s.value for s in requested_scopes],
        "scope_descriptions": {
            OAuthScope.PROFILE_READ.value: "Read your basic profile (roles, VEKN ID)",
            OAuthScope.USER_IMPERSONATE.value: "Act on your behalf on API endpoints",
        },
        "redirect_uri": redirect_uri,
        "state": state,
        "client_id": client_id,
        "code_challenge": code_challenge,
    }


class AuthorizeApproval(msgspec.Struct):
    client_id: str
    redirect_uri: str
    scope: str
    state: str = ""
    code_challenge: str = ""
    approved: bool = True


@router.post("/authorize")
async def authorize_post(user: CurrentUser, body: dict):
    """User approves or denies the authorization request."""
    client_id = body.get("client_id", "")
    redirect_uri = body.get("redirect_uri", "")
    scope = body.get("scope", "")
    state = body.get("state", "")
    code_challenge = body.get("code_challenge", "")
    approved = body.get("approved", True)

    # Validate client
    client = await get_oauth_client_by_client_id(client_id)
    if not client or not client.active:
        raise HTTPException(400, "Invalid client_id")

    if redirect_uri not in client.redirect_uris:
        raise HTTPException(400, "Invalid redirect_uri")

    requested_scopes = _parse_scopes(scope)

    if not approved:
        params = {"error": "access_denied"}
        if state:
            params["state"] = state
        return RedirectResponse(
            url=f"{redirect_uri}?{urlencode(params)}", status_code=302
        )

    if not code_challenge:
        raise HTTPException(400, "PKCE code_challenge is required")

    # Save consent
    now = datetime.now(UTC)
    consent = OAuthConsent(
        uid=str(uuid7()),
        modified=now,
        user_uid=user.uid,
        client_id=client_id,
        scopes=requested_scopes,
    )
    await upsert_oauth_consent(consent)

    # Generate authorization code
    code_value = _generate_auth_code()
    auth_code = OAuthAuthorizationCode(
        uid=str(uuid7()),
        modified=now,
        code=code_value,
        client_id=client_id,
        user_uid=user.uid,
        redirect_uri=redirect_uri,
        scopes=requested_scopes,
        code_challenge=code_challenge,
        expires_at=now + AUTH_CODE_LIFETIME,
    )
    await insert_oauth_code(auth_code)

    params = {"code": code_value}
    if state:
        params["state"] = state
    return {"redirect_url": f"{redirect_uri}?{urlencode(params)}"}


# --- Token Endpoint ---


@router.post("/token")
async def token_endpoint(body: dict):
    """Exchange authorization code for tokens, or refresh tokens.

    Client authenticates via client_id + client_secret in the body.
    """
    grant_type = body.get("grant_type", "")
    client_id = body.get("client_id", "")
    client_secret = body.get("client_secret", "")

    # Authenticate client
    client = await get_oauth_client_by_client_id(client_id)
    if not client or not client.active:
        raise HTTPException(401, "Invalid client credentials")

    try:
        ph.verify(client.client_secret_hash, client_secret)
    except VerifyMismatchError:
        raise HTTPException(401, "Invalid client credentials")

    if grant_type == "authorization_code":
        return await _handle_authorization_code(body, client)
    elif grant_type == "refresh_token":
        return await _handle_refresh_token(body, client)
    else:
        raise HTTPException(400, "Unsupported grant_type")


async def _handle_authorization_code(body: dict, client: OAuthClient) -> dict:
    code_value = body.get("code", "")
    redirect_uri = body.get("redirect_uri", "")
    code_verifier = body.get("code_verifier", "")

    if not code_value or not redirect_uri or not code_verifier:
        raise HTTPException(400, "Missing required parameters")

    # Look up code
    auth_code = await get_oauth_code(code_value)
    if not auth_code:
        raise HTTPException(400, "Invalid authorization code")

    # Validate
    if auth_code.used:
        raise HTTPException(400, "Authorization code already used")

    if auth_code.client_id != client.client_id:
        raise HTTPException(400, "Client mismatch")

    if auth_code.redirect_uri != redirect_uri:
        raise HTTPException(400, "Redirect URI mismatch")

    now = datetime.now(UTC)
    if auth_code.expires_at < now:
        raise HTTPException(400, "Authorization code expired")

    # Verify PKCE
    if not _verify_pkce(code_verifier, auth_code.code_challenge):
        raise HTTPException(400, "Invalid code_verifier (PKCE)")

    # Mark code as used
    used_code = OAuthAuthorizationCode(
        uid=auth_code.uid, modified=now, code=auth_code.code,
        client_id=auth_code.client_id, user_uid=auth_code.user_uid,
        redirect_uri=auth_code.redirect_uri, scopes=auth_code.scopes,
        code_challenge=auth_code.code_challenge, expires_at=auth_code.expires_at,
        used=True,
    )
    await update_oauth_code(used_code)

    # Generate tokens
    return await _issue_token_pair(
        user_uid=auth_code.user_uid,
        client_id=client.client_id,
        scopes=auth_code.scopes,
        parent_token_uid=None,
    )


async def _handle_refresh_token(body: dict, client: OAuthClient) -> dict:
    refresh_token_str = body.get("refresh_token", "")
    if not refresh_token_str:
        raise HTTPException(400, "Missing refresh_token")

    # Decode JWT
    try:
        payload = jwt.decode(refresh_token_str, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(400, "Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(400, "Invalid refresh token")

    if payload.get("type") != "oauth_refresh":
        raise HTTPException(400, "Invalid token type")

    if payload.get("client_id") != client.client_id:
        raise HTTPException(400, "Client mismatch")

    jti = payload.get("jti", "")
    token_record = await get_oauth_token_by_jti(jti)
    if not token_record:
        raise HTTPException(400, "Unknown refresh token")

    if token_record.revoked:
        # Reuse of revoked token → revoke entire chain
        if token_record.parent_token_uid:
            await revoke_oauth_token_chain(token_record.parent_token_uid)
        logger.warning(f"Revoked refresh token reuse detected: jti={jti}")
        raise HTTPException(400, "Refresh token has been revoked")

    # Revoke old refresh token
    now = datetime.now(UTC)
    revoked = OAuthToken(
        uid=token_record.uid, modified=now, token_jti=token_record.token_jti,
        client_id=token_record.client_id, user_uid=token_record.user_uid,
        scopes=token_record.scopes, token_type=token_record.token_type,
        expires_at=token_record.expires_at, revoked=True,
        parent_token_uid=token_record.parent_token_uid,
    )
    await update_oauth_token(revoked)

    # Issue new pair (chain to the same parent)
    parent = token_record.parent_token_uid or token_record.uid
    scopes = [OAuthScope(s) for s in payload.get("scope", "").split()]

    return await _issue_token_pair(
        user_uid=payload["sub"],
        client_id=client.client_id,
        scopes=scopes,
        parent_token_uid=parent,
    )


async def _issue_token_pair(
    user_uid: str,
    client_id: str,
    scopes: list[OAuthScope],
    parent_token_uid: str | None,
) -> dict:
    now = datetime.now(UTC)
    access_jti = str(uuid7())
    refresh_jti = str(uuid7())

    access_token = _create_oauth_jwt(
        user_uid, "access", scopes, client_id, access_jti, ACCESS_TOKEN_LIFETIME
    )
    refresh_token = _create_oauth_jwt(
        user_uid, "refresh", scopes, client_id, refresh_jti, REFRESH_TOKEN_LIFETIME
    )

    # Record tokens for revocation tracking
    access_record = OAuthToken(
        uid=str(uuid7()), modified=now, token_jti=access_jti,
        client_id=client_id, user_uid=user_uid, scopes=scopes,
        token_type="access", expires_at=now + ACCESS_TOKEN_LIFETIME,
        parent_token_uid=parent_token_uid,
    )
    refresh_record = OAuthToken(
        uid=str(uuid7()), modified=now, token_jti=refresh_jti,
        client_id=client_id, user_uid=user_uid, scopes=scopes,
        token_type="refresh", expires_at=now + REFRESH_TOKEN_LIFETIME,
        parent_token_uid=parent_token_uid or access_record.uid,
    )
    await insert_oauth_token(access_record)
    await insert_oauth_token(refresh_record)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": int(ACCESS_TOKEN_LIFETIME.total_seconds()),
        "scope": " ".join(scopes),
    }


# --- Revocation ---


@router.post("/revoke")
async def revoke_token(body: dict):
    """Revoke a token by JTI (RFC 7009). Client authenticates via body."""
    client_id = body.get("client_id", "")
    client_secret = body.get("client_secret", "")
    token_jti = body.get("token_jti", "")

    if not token_jti:
        raise HTTPException(400, "Missing token_jti")

    client = await get_oauth_client_by_client_id(client_id)
    if not client or not client.active:
        raise HTTPException(401, "Invalid client credentials")

    try:
        ph.verify(client.client_secret_hash, client_secret)
    except VerifyMismatchError:
        raise HTTPException(401, "Invalid client credentials")

    token_record = await get_oauth_token_by_jti(token_jti)
    if not token_record or token_record.client_id != client.client_id:
        # Per RFC 7009, return 200 even if token not found
        return {"status": "ok"}

    if not token_record.revoked:
        now = datetime.now(UTC)
        revoked = OAuthToken(
            uid=token_record.uid, modified=now, token_jti=token_record.token_jti,
            client_id=token_record.client_id, user_uid=token_record.user_uid,
            scopes=token_record.scopes, token_type=token_record.token_type,
            expires_at=token_record.expires_at, revoked=True,
            parent_token_uid=token_record.parent_token_uid,
        )
        await update_oauth_token(revoked)

    return {"status": "ok"}


# --- UserInfo ---


@router.get("/userinfo")
async def userinfo(user: CurrentUser, request: Request):
    """Returns basic profile info for OAuth token holders.

    The middleware already validates the token and loads the user.
    We just need to check that this is an OAuth token with profile:read scope.
    """
    # The token type check is done in middleware; here we just return the profile
    # Middleware sets request.state.oauth_scopes if it's an OAuth token
    oauth_scopes = getattr(request.state, "oauth_scopes", None)
    if oauth_scopes is None:
        # Regular auth token — also allowed for convenience
        pass
    elif OAuthScope.PROFILE_READ.value not in oauth_scopes:
        raise HTTPException(403, "Requires profile:read scope")

    return {
        "sub": user.uid,
        "roles": [r.value for r in user.roles],
        "vekn_id": user.vekn_id,
    }


# --- Client Management (DEV role) ---


class RegisterClientRequest(msgspec.Struct):
    name: str
    redirect_uris: list[str]
    scopes: list[str]


@router.post("/clients")
async def register_client(
    body: dict,
    user: User = Depends(require_role(Role.DEV)),
):
    """Register a new OAuth client. Returns client_secret once."""
    name = body.get("name", "").strip()
    redirect_uris = body.get("redirect_uris", [])
    scope_strs = body.get("scopes", [])

    if not name:
        raise HTTPException(400, "Client name is required")
    if not redirect_uris:
        raise HTTPException(400, "At least one redirect_uri is required")

    # Validate scopes
    scopes = []
    for s in scope_strs:
        try:
            scopes.append(OAuthScope(s))
        except ValueError:
            raise HTTPException(400, f"Invalid scope: {s}")

    client_id = _generate_client_id()
    client_secret = _generate_client_secret()
    secret_hash = ph.hash(client_secret)

    now = datetime.now(UTC)
    client = OAuthClient(
        uid=str(uuid7()),
        modified=now,
        name=name,
        client_id=client_id,
        client_secret_hash=secret_hash,
        redirect_uris=redirect_uris,
        scopes=scopes,
        created_by_uid=user.uid,
    )
    await insert_oauth_client(client)

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "name": name,
        "redirect_uris": redirect_uris,
        "scopes": [s.value for s in scopes],
        "warning": "Save the client_secret now. It will not be shown again.",
    }


@router.get("/clients")
async def list_clients(user: User = Depends(require_role(Role.DEV))):
    """List own OAuth clients."""
    clients = await get_oauth_clients_by_owner(user.uid)
    return [
        {
            "uid": c.uid,
            "name": c.name,
            "client_id": c.client_id,
            "redirect_uris": c.redirect_uris,
            "scopes": [s.value for s in c.scopes],
            "active": c.active,
            "modified": c.modified.isoformat(),
        }
        for c in clients
    ]


@router.get("/clients/{client_id}")
async def get_client(
    client_id: str,
    user: User = Depends(require_role(Role.DEV)),
):
    """Get details of own OAuth client."""
    client = await get_oauth_client_by_client_id(client_id)
    if not client or client.created_by_uid != user.uid:
        raise HTTPException(404, "Client not found")

    return {
        "uid": client.uid,
        "name": client.name,
        "client_id": client.client_id,
        "redirect_uris": client.redirect_uris,
        "scopes": [s.value for s in client.scopes],
        "active": client.active,
        "modified": client.modified.isoformat(),
    }


@router.post("/clients/{client_id}/regenerate-secret")
async def regenerate_secret(
    client_id: str,
    user: User = Depends(require_role(Role.DEV)),
):
    """Regenerate client secret. Old secret is invalidated."""
    client = await get_oauth_client_by_client_id(client_id)
    if not client or client.created_by_uid != user.uid:
        raise HTTPException(404, "Client not found")

    new_secret = _generate_client_secret()
    now = datetime.now(UTC)
    updated = OAuthClient(
        uid=client.uid, modified=now, name=client.name,
        client_id=client.client_id, client_secret_hash=ph.hash(new_secret),
        redirect_uris=client.redirect_uris, scopes=client.scopes,
        created_by_uid=client.created_by_uid, active=client.active,
    )
    await update_oauth_client(updated)

    return {
        "client_id": client_id,
        "client_secret": new_secret,
        "warning": "Save the new client_secret now. It will not be shown again.",
    }


@router.delete("/clients/{client_id}")
async def deactivate_client(
    client_id: str,
    user: User = Depends(require_role(Role.DEV)),
):
    """Deactivate an OAuth client."""
    client = await get_oauth_client_by_client_id(client_id)
    if not client or client.created_by_uid != user.uid:
        raise HTTPException(404, "Client not found")

    now = datetime.now(UTC)
    updated = OAuthClient(
        uid=client.uid, modified=now, name=client.name,
        client_id=client.client_id, client_secret_hash=client.client_secret_hash,
        redirect_uris=client.redirect_uris, scopes=client.scopes,
        created_by_uid=client.created_by_uid, active=False,
    )
    await update_oauth_client(updated)

    return {"status": "deactivated", "client_id": client_id}
