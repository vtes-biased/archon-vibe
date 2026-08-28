"""OAuth 2.0 Authorization Server (RFC 6749 + RFC 7636 PKCE)."""

import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode
from uuid import uuid7

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import permissions
from ..db import get_tournament_by_uid
from ..db_oauth import (
    delete_oauth_consent,
    get_oauth_client_by_client_id,
    get_oauth_clients_by_owner,
    get_oauth_code,
    get_oauth_consent,
    get_oauth_consents_by_user,
    get_oauth_token_by_jti,
    insert_oauth_client,
    insert_oauth_code,
    insert_oauth_token,
    revoke_oauth_token_chain,
    revoke_oauth_tokens_for_user_client,
    update_oauth_client,
    update_oauth_code,
    update_oauth_token,
    upsert_oauth_consent,
)
from ..middleware.auth import (
    JWT_ALGORITHM,
    JWT_SECRET,
    CurrentUser,
)
from ..models import (
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    OAuthScope,
    OAuthToken,
    TournamentState,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])

ph = PasswordHasher()

ACCESS_TOKEN_LIFETIME = timedelta(hours=1)
CLIENT_TOKEN_LIFETIME = timedelta(hours=1)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)
AUTH_CODE_LIFETIME = timedelta(seconds=60)


def _generate_client_id() -> str:
    return secrets.token_urlsafe(24)[:32]


def _generate_client_secret() -> str:
    return secrets.token_urlsafe(48)


def _generate_auth_code() -> str:
    return secrets.token_urlsafe(48)[:64]


def _verify_pkce(code_verifier: str, code_challenge: str) -> bool:
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
    tournament_uid: str | None = None,
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
    # Never a member of `scope`: that string round-trips through OAuthScope.
    if tournament_uid:
        payload["tournament"] = tournament_uid
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _parse_scopes(scope_str: str) -> list[OAuthScope]:
    """Parse space-separated scope string into validated OAuthScope list."""
    scopes = []
    for s in scope_str.split():
        try:
            scopes.append(OAuthScope(s))
        except ValueError:
            raise HTTPException(400, f"Invalid scope: {s}") from None
    return scopes


async def _grant_tournament(scopes: list[OAuthScope], tournament_uid: str):
    """Resolve the event a `user:impersonate` grant is scoped to, refusing a
    finished one. Returns the Tournament, or None when the grant carries no
    impersonation. Every impersonate grant names exactly one event."""
    if OAuthScope.USER_IMPERSONATE not in scopes:
        if tournament_uid:
            raise HTTPException(400, "tournament requires the user:impersonate scope")
        return None
    if not tournament_uid:
        raise HTTPException(400, "user:impersonate must name a tournament")
    tournament = await get_tournament_by_uid(tournament_uid)
    if not tournament:
        raise HTTPException(400, "Unknown tournament")
    if tournament.state == TournamentState.FINISHED:
        raise HTTPException(400, "Tournament is finished")
    return tournament


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
    tournament: str = "",
):
    """Validate OAuth authorization request parameters. Returns JSON with authorization details
    or redirects with code if consent already exists."""
    _require_first_party(request, "Consent management requires a first-party session")

    if response_type != "code":
        raise HTTPException(400, "Only response_type=code is supported")

    if not code_challenge or code_challenge_method != "S256":
        raise HTTPException(400, "PKCE with S256 is required")

    client = await get_oauth_client_by_client_id(client_id)
    if not client or not client.active:
        raise HTTPException(400, "Invalid client_id")

    # Exact match required — a prefix/substring match would allow open redirects.
    if redirect_uri not in client.redirect_uris:
        raise HTTPException(400, "Invalid redirect_uri")

    requested_scopes = _parse_scopes(scope)
    for s in requested_scopes:
        if s not in client.scopes:
            raise HTTPException(400, f"Scope {s} not allowed for this client")
    if OAuthScope.API_READ in requested_scopes:
        raise HTTPException(400, "api:read is a client_credentials scope")

    event = await _grant_tournament(requested_scopes, tournament)
    tournament_uid = event.uid if event else None

    consent = await get_oauth_consent(user.uid, client_id, tournament_uid)
    if consent and set(requested_scopes).issubset(set(consent.scopes)):
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
            tournament_uid=tournament_uid,
            code_challenge=code_challenge,
            expires_at=now + AUTH_CODE_LIFETIME,
        )
        await insert_oauth_code(auth_code)

        params = {"code": code_value}
        if state:
            params["state"] = state
        # Never a 302: the caller is a fetch, which cannot read Location.
        return {"redirect_url": f"{redirect_uri}?{urlencode(params)}"}

    return {
        "client_name": client.name,
        "scopes": [s.value for s in requested_scopes],
        "scope_descriptions": {
            OAuthScope.PROFILE_READ.value: "Read your basic profile (roles, VEKN ID)",
            OAuthScope.USER_IMPERSONATE.value: "Act on your behalf on this event",
        },
        "redirect_uri": redirect_uri,
        "state": state,
        "client_id": client_id,
        "code_challenge": code_challenge,
        "tournament": tournament_uid,
        "tournament_name": event.name if event else None,
    }


class AuthorizeApprovalRequest(BaseModel):
    """POST /authorize body (first-party consent screen). Fields default empty
    so missing values fail the endpoint's own 400s, not as a 422."""

    client_id: str = ""
    redirect_uri: str = ""
    scope: str = ""
    state: str = ""
    code_challenge: str = ""
    tournament: str = ""
    approved: bool = True


@router.post("/authorize")
async def authorize_post(
    user: CurrentUser, body: AuthorizeApprovalRequest, request: Request
):
    _require_first_party(request, "Consent management requires a first-party session")

    client_id = body.client_id
    redirect_uri = body.redirect_uri
    scope = body.scope
    state = body.state
    code_challenge = body.code_challenge
    approved = body.approved

    client = await get_oauth_client_by_client_id(client_id)
    if not client or not client.active:
        raise HTTPException(400, "Invalid client_id")

    if redirect_uri not in client.redirect_uris:
        raise HTTPException(400, "Invalid redirect_uri")

    requested_scopes = _parse_scopes(scope)
    if OAuthScope.API_READ in requested_scopes:
        raise HTTPException(400, "api:read is a client_credentials scope")

    if not approved:
        params = {"error": "access_denied"}
        if state:
            params["state"] = state
        return {"redirect_url": f"{redirect_uri}?{urlencode(params)}"}

    if not code_challenge:
        raise HTTPException(400, "PKCE code_challenge is required")

    event = await _grant_tournament(requested_scopes, body.tournament)
    tournament_uid = event.uid if event else None

    now = datetime.now(UTC)
    consent = OAuthConsent(
        uid=str(uuid7()),
        modified=now,
        user_uid=user.uid,
        client_id=client_id,
        scopes=requested_scopes,
        tournament_uid=tournament_uid,
    )
    await upsert_oauth_consent(consent)

    code_value = _generate_auth_code()
    auth_code = OAuthAuthorizationCode(
        uid=str(uuid7()),
        modified=now,
        code=code_value,
        client_id=client_id,
        user_uid=user.uid,
        redirect_uri=redirect_uri,
        scopes=requested_scopes,
        tournament_uid=tournament_uid,
        code_challenge=code_challenge,
        expires_at=now + AUTH_CODE_LIFETIME,
    )
    await insert_oauth_code(auth_code)

    params = {"code": code_value}
    if state:
        params["state"] = state
    return {"redirect_url": f"{redirect_uri}?{urlencode(params)}"}


class TokenRequest(BaseModel):
    """POST /token body. Fields default empty so a missing value fails the
    endpoint's own 400/401s, not a 422."""

    grant_type: str = ""
    client_id: str = ""
    client_secret: str = ""
    code: str = ""
    redirect_uri: str = ""
    code_verifier: str = ""
    refresh_token: str = ""
    scope: str = ""


class RevokeRequest(BaseModel):
    """POST /revoke body (RFC 7009)."""

    client_id: str = ""
    client_secret: str = ""
    token: str = ""


# Both handlers take a raw Request to accept either encoding, so FastAPI derives
# no request body of its own.
_TOKEN_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            media: {"schema": TokenRequest.model_json_schema()}
            for media in ("application/x-www-form-urlencoded", "application/json")
        },
    }
}
_REVOKE_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            media: {"schema": RevokeRequest.model_json_schema()}
            for media in ("application/x-www-form-urlencoded", "application/json")
        },
    }
}


async def _rfc_body[T: BaseModel](request: Request, model: type[T]) -> T:
    """Form-encoded as the RFCs require, or JSON with the same keys."""
    raw = await request.body()
    if request.headers.get("content-type", "").startswith(
        "application/x-www-form-urlencoded"
    ):
        fields = dict(parse_qsl(raw.decode("utf-8", "replace")))
    else:
        try:
            fields = json.loads(raw or b"{}")
        except ValueError:
            raise HTTPException(400, "Body must be form-encoded or JSON") from None
    if not isinstance(fields, dict):
        raise HTTPException(400, "Body must be form-encoded or JSON")
    known = model.model_fields
    return model(
        **{k: str(v) for k, v in fields.items() if k in known and v is not None}
    )


@router.post("/token", openapi_extra=_TOKEN_BODY)
async def token_endpoint(request: Request):
    """Exchange authorization code, refresh token or client credentials for tokens.

    The client authenticates with its client_id and client_secret in the body,
    form-encoded as RFC 6749 requires or as JSON with the same keys.
    """
    body = await _rfc_body(request, TokenRequest)
    grant_type = body.grant_type

    client = await get_oauth_client_by_client_id(body.client_id)
    if not client or not client.active:
        raise HTTPException(401, "Invalid client credentials")

    try:
        ph.verify(client.client_secret_hash, body.client_secret)
    except VerifyMismatchError:
        raise HTTPException(401, "Invalid client credentials") from None

    if grant_type == "authorization_code":
        return await _handle_authorization_code(body, client)
    elif grant_type == "refresh_token":
        return await _handle_refresh_token(body, client)
    elif grant_type == "client_credentials":
        return await _handle_client_credentials(body, client)
    else:
        raise HTTPException(400, "Unsupported grant_type")


async def _handle_authorization_code(body: TokenRequest, client: OAuthClient) -> dict:
    code_value = body.code
    redirect_uri = body.redirect_uri
    code_verifier = body.code_verifier

    if not code_value or not redirect_uri or not code_verifier:
        raise HTTPException(400, "Missing required parameters")

    auth_code = await get_oauth_code(code_value)
    if not auth_code:
        raise HTTPException(400, "Invalid authorization code")

    if auth_code.used:
        raise HTTPException(400, "Authorization code already used")

    if auth_code.client_id != client.client_id:
        raise HTTPException(400, "Client mismatch")

    if auth_code.redirect_uri != redirect_uri:
        raise HTTPException(400, "Redirect URI mismatch")

    now = datetime.now(UTC)
    if auth_code.expires_at < now:
        raise HTTPException(400, "Authorization code expired")

    if not _verify_pkce(code_verifier, auth_code.code_challenge):
        raise HTTPException(400, "Invalid code_verifier (PKCE)")

    # Consent is authoritative: a revoke between code issuance and exchange (≤60s,
    # or any auto-approve race) deletes the consent row and must block redemption.
    if not await get_oauth_consent(
        auth_code.user_uid, client.client_id, auth_code.tournament_uid
    ):
        raise HTTPException(400, "Consent has been revoked")

    used_code = OAuthAuthorizationCode(
        uid=auth_code.uid,
        modified=now,
        code=auth_code.code,
        client_id=auth_code.client_id,
        user_uid=auth_code.user_uid,
        redirect_uri=auth_code.redirect_uri,
        scopes=auth_code.scopes,
        tournament_uid=auth_code.tournament_uid,
        code_challenge=auth_code.code_challenge,
        expires_at=auth_code.expires_at,
        used=True,
    )
    await update_oauth_code(used_code)

    return await _issue_token_pair(
        user_uid=auth_code.user_uid,
        client_id=client.client_id,
        scopes=auth_code.scopes,
        tournament_uid=auth_code.tournament_uid,
        parent_token_uid=None,
    )


async def _handle_refresh_token(body: TokenRequest, client: OAuthClient) -> dict:
    refresh_token_str = body.refresh_token
    if not refresh_token_str:
        raise HTTPException(400, "Missing refresh_token")

    try:
        payload = jwt.decode(refresh_token_str, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(400, "Refresh token expired") from None
    except jwt.InvalidTokenError:
        raise HTTPException(400, "Invalid refresh token") from None

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

    # Consent is authoritative: revoking it deletes the row, so a surviving refresh
    # token (e.g. a partial revoke) still can't mint new access tokens.
    tournament_uid = payload.get("tournament")
    scope_values = payload.get("scope", "").split()
    if OAuthScope.USER_IMPERSONATE.value in scope_values and not tournament_uid:
        raise HTTPException(400, "Unscoped impersonation grants are no longer issued")

    if not await get_oauth_consent(payload["sub"], client.client_id, tournament_uid):
        raise HTTPException(400, "Consent has been revoked")

    if tournament_uid:
        event = await get_tournament_by_uid(tournament_uid)
        if not event or event.state == TournamentState.FINISHED:
            raise HTTPException(400, "Tournament is finished")

    now = datetime.now(UTC)
    revoked = OAuthToken(
        uid=token_record.uid,
        modified=now,
        token_jti=token_record.token_jti,
        client_id=token_record.client_id,
        user_uid=token_record.user_uid,
        scopes=token_record.scopes,
        tournament_uid=token_record.tournament_uid,
        token_type=token_record.token_type,
        expires_at=token_record.expires_at,
        revoked=True,
        parent_token_uid=token_record.parent_token_uid,
    )
    await update_oauth_token(revoked)

    # Chain the new pair to the same parent — preserves rotation lineage for reuse detection.
    parent = token_record.parent_token_uid or token_record.uid
    scopes = [OAuthScope(s) for s in payload.get("scope", "").split()]

    return await _issue_token_pair(
        user_uid=payload["sub"],
        client_id=client.client_id,
        scopes=scopes,
        tournament_uid=tournament_uid,
        parent_token_uid=parent,
    )


async def _handle_client_credentials(body: TokenRequest, client: OAuthClient) -> dict:
    """Stateless on purpose: no `oauth_tokens` row, because that record is keyed on
    a user and a daemon has none. Revocation is the client's `active` flag, which
    the public API checks for itself."""
    if OAuthScope.API_READ not in client.scopes:
        raise HTTPException(400, "Client is not allowed the api:read scope")
    if body.scope and _parse_scopes(body.scope) != [OAuthScope.API_READ]:
        raise HTTPException(400, "client_credentials grants api:read and nothing else")

    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "type": "oauth_client",
            "client_id": client.client_id,
            "scope": OAuthScope.API_READ.value,
            "iat": now,
            "exp": now + CLIENT_TOKEN_LIFETIME,
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": int(CLIENT_TOKEN_LIFETIME.total_seconds()),
        "scope": OAuthScope.API_READ.value,
    }


async def _issue_token_pair(
    user_uid: str,
    client_id: str,
    scopes: list[OAuthScope],
    tournament_uid: str | None,
    parent_token_uid: str | None,
) -> dict:
    now = datetime.now(UTC)
    access_jti = str(uuid7())
    refresh_jti = str(uuid7())

    access_token = _create_oauth_jwt(
        user_uid,
        "access",
        scopes,
        client_id,
        access_jti,
        ACCESS_TOKEN_LIFETIME,
        tournament_uid,
    )
    refresh_token = _create_oauth_jwt(
        user_uid,
        "refresh",
        scopes,
        client_id,
        refresh_jti,
        REFRESH_TOKEN_LIFETIME,
        tournament_uid,
    )

    access_record = OAuthToken(
        uid=str(uuid7()),
        modified=now,
        token_jti=access_jti,
        client_id=client_id,
        user_uid=user_uid,
        scopes=scopes,
        tournament_uid=tournament_uid,
        token_type="access",
        expires_at=now + ACCESS_TOKEN_LIFETIME,
        parent_token_uid=parent_token_uid,
    )
    refresh_record = OAuthToken(
        uid=str(uuid7()),
        modified=now,
        token_jti=refresh_jti,
        client_id=client_id,
        user_uid=user_uid,
        scopes=scopes,
        tournament_uid=tournament_uid,
        token_type="refresh",
        expires_at=now + REFRESH_TOKEN_LIFETIME,
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


@router.post("/revoke", openapi_extra=_REVOKE_BODY)
async def revoke_token(request: Request):
    """Revoke a token and the whole rotation lineage it belongs to (RFC 7009)."""
    body = await _rfc_body(request, RevokeRequest)

    client = await get_oauth_client_by_client_id(body.client_id)
    if not client or not client.active:
        raise HTTPException(401, "Invalid client credentials")

    try:
        ph.verify(client.client_secret_hash, body.client_secret)
    except VerifyMismatchError:
        raise HTTPException(401, "Invalid client credentials") from None

    if not body.token:
        raise HTTPException(400, "Missing token")

    try:
        payload = jwt.decode(
            body.token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": False},
        )
    except jwt.InvalidTokenError:
        return {"status": "ok"}

    record = await get_oauth_token_by_jti(payload.get("jti", ""))
    if record and record.client_id == client.client_id:
        await revoke_oauth_token_chain(record.parent_token_uid or record.uid)

    return {"status": "ok"}


@router.get("/userinfo")
async def userinfo(user: CurrentUser, request: Request):
    """Middleware validates the token and sets request.state.oauth_scopes for OAuth
    tokens (None for first-party sessions, which skip the scope check below)."""
    oauth_scopes = getattr(request.state, "oauth_scopes", None)
    if oauth_scopes is None:
        pass
    elif OAuthScope.PROFILE_READ.value not in oauth_scopes:
        raise HTTPException(403, "Requires profile:read scope")

    return {
        "sub": user.uid,
        "roles": [r.value for r in user.roles],
        "vekn_id": user.vekn_id,
        # What the holder may do, so a client need not match role strings.
        "capabilities": permissions.unconditional_capabilities(user),
    }


def _require_first_party(request: Request, detail: str) -> None:
    """The middleware admits a scoped token to every `/oauth/*` path, so each
    self-service endpoint under the prefix re-checks that it is not a third party."""
    if getattr(request.state, "oauth_scopes", None) is not None:
        raise HTTPException(403, detail)


@router.get("/consents")
async def list_consents(user: CurrentUser, request: Request):
    _require_first_party(request, "Consent management requires a first-party session")
    consents = await get_oauth_consents_by_user(user.uid)
    out = []
    for c in consents:
        client = await get_oauth_client_by_client_id(c.client_id)
        if not client:
            continue  # orphaned consent (client hard-deleted) — nothing to show
        event = (
            await get_tournament_by_uid(c.tournament_uid) if c.tournament_uid else None
        )
        out.append(
            {
                "client_id": c.client_id,
                "name": client.name,
                "scopes": [s.value for s in c.scopes],
                "tournament": c.tournament_uid,
                "tournament_name": event.name if event else None,
                "granted_at": c.modified.isoformat(),
            }
        )
    return out


@router.delete("/consents/{client_id}")
async def revoke_consent(client_id: str, user: CurrentUser, request: Request):
    """Tokens revoked first (cuts access immediately), then consent dropped — a
    failure in between leaves a re-revokable consent that can't mint new tokens."""
    _require_first_party(request, "Consent management requires a first-party session")
    revoked = await revoke_oauth_tokens_for_user_client(user.uid, client_id)
    deleted = await delete_oauth_consent(user.uid, client_id)
    if not deleted and not revoked:
        raise HTTPException(404, "No authorization found for this app")
    return {"status": "revoked", "client_id": client_id, "tokens_revoked": revoked}


# Client management is IC or DEV, and first-party only — one gate, four routes.
async def _require_oauth_admin(request: Request, user: CurrentUser) -> User:
    _require_first_party(request, "Client management requires a first-party session")
    if not permissions.can_manage_oauth_clients(user):
        raise HTTPException(403, "Only IC or DEV can manage OAuth clients")
    return user


RequireOauthAdmin = Depends(_require_oauth_admin)


class RegisterClientRequest(BaseModel):
    """POST /clients body (DEV role). Fields default empty so missing values
    fail the endpoint's own 400s, not as a 422."""

    name: str = ""
    redirect_uris: list[str] = []
    scopes: list[str] = []


@router.post("/clients")
async def register_client(
    body: RegisterClientRequest,
    user: User = RequireOauthAdmin,
):
    """Register a new OAuth client. Returns client_secret once."""
    name = body.name.strip()
    redirect_uris = body.redirect_uris
    scope_strs = body.scopes

    if not name:
        raise HTTPException(400, "Client name is required")

    scopes = []
    for scope_str in scope_strs:
        try:
            scopes.append(OAuthScope(scope_str))
        except ValueError:
            raise HTTPException(400, f"Invalid scope: {scope_str}") from None

    if not redirect_uris and set(scopes) != {OAuthScope.API_READ}:
        raise HTTPException(400, "At least one redirect_uri is required")

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
async def list_clients(user: User = RequireOauthAdmin):
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


@router.post("/clients/{client_id}/regenerate-secret")
async def regenerate_secret(
    client_id: str,
    user: User = RequireOauthAdmin,
):
    client = await get_oauth_client_by_client_id(client_id)
    if not client or client.created_by_uid != user.uid:
        raise HTTPException(404, "Client not found")

    new_secret = _generate_client_secret()
    now = datetime.now(UTC)
    updated = OAuthClient(
        uid=client.uid,
        modified=now,
        name=client.name,
        client_id=client.client_id,
        client_secret_hash=ph.hash(new_secret),
        redirect_uris=client.redirect_uris,
        scopes=client.scopes,
        created_by_uid=client.created_by_uid,
        active=client.active,
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
    user: User = RequireOauthAdmin,
):
    client = await get_oauth_client_by_client_id(client_id)
    if not client or client.created_by_uid != user.uid:
        raise HTTPException(404, "Client not found")

    now = datetime.now(UTC)
    updated = OAuthClient(
        uid=client.uid,
        modified=now,
        name=client.name,
        client_id=client.client_id,
        client_secret_hash=client.client_secret_hash,
        redirect_uris=client.redirect_uris,
        scopes=client.scopes,
        created_by_uid=client.created_by_uid,
        active=False,
    )
    await update_oauth_client(updated)

    return {"status": "deactivated", "client_id": client_id}
