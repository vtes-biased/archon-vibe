"""Authentication API endpoints."""

import base64
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import aiohttp
import jwt
import msgspec
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from uuid6 import uuid7
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..db import (
    delete_transient_token,
    get_auth_method_by_identifier,
    get_auth_methods_for_user,
    get_transient_token,
    get_user_by_contact_email,
    get_user_by_uid,
    insert_auth_method,
    insert_user,
    merge_users,
    store_transient_token,
    update_auth_method,
    update_user,
)
from ..email_service import send_magic_link_email
from ..jwt_config import JWT_ALGORITHM, JWT_SECRET
from ..models import AuthMethod, AuthMethodType, User

router = APIRouter(prefix="/auth", tags=["auth"])
encoder = msgspec.json.Encoder()

# Password hasher
ph = PasswordHasher()

# JWT settings
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# WebAuthn settings
WEBAUTHN_RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
WEBAUTHN_RP_NAME = os.getenv("WEBAUTHN_RP_NAME", "Archon")
WEBAUTHN_ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost:5173")


def _get_discord_config() -> tuple[str, str, str, str]:
    """Get Discord OAuth config lazily (after dotenv is loaded)."""
    return (
        os.getenv("DISCORD_CLIENTID", ""),
        os.getenv("DISCORD_SECRET", ""),
        os.getenv(
            "DISCORD_REDIRECT_URI", "http://localhost:8000/auth/discord/callback"
        ),
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
    )


# Magic link settings
MAGIC_LINK_EXPIRE_MINUTES = 15
SET_PASSWORD_EXPIRE_MINUTES = 10

logger = logging.getLogger(__name__)


class RegisterRequest(BaseModel):
    """Registration request payload."""

    email: EmailStr
    password: str
    name: str


class LoginRequest(BaseModel):
    """Login request payload."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response payload."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires


class RefreshRequest(BaseModel):
    """Token refresh request payload."""

    refresh_token: str


class PasskeyRegisterVerifyRequest(BaseModel):
    """Passkey registration verification request."""

    credential: dict  # Raw credential from navigator.credentials.create()


class PasskeyLoginVerifyRequest(BaseModel):
    """Passkey login verification request."""

    credential: dict  # Raw credential from navigator.credentials.get()


class ProfileUpdateRequest(BaseModel):
    """Profile update request payload."""

    name: str | None = None
    nickname: str | None = None
    country: str | None = None
    city: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


class MagicLinkRequest(BaseModel):
    """Magic link request payload."""

    email: EmailStr
    purpose: str = "signup"  # "signup" or "reset"


class MagicLinkVerifyRequest(BaseModel):
    """Magic link verification request payload."""

    token: str


class SetPasswordRequest(BaseModel):
    """Set password request payload (after magic link verification)."""

    token: str
    password: str


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


# =============================================================================
# Magic Link (Email) Authentication Endpoints
# =============================================================================


def _get_frontend_url() -> str:
    """Get frontend URL from environment."""
    return os.getenv("FRONTEND_URL", "http://localhost:5173")


async def send_invite_email(email: str, user_uid: str, user_name: str) -> bool:
    """Send an invite email to a newly created user.

    Creates a magic link that allows the user to set their password
    and activate their account.

    Args:
        email: Recipient email address
        user_uid: The UID of the user to link to
        user_name: The user's name for the email

    Returns:
        True if email was sent successfully
    """
    # Generate token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES)
    await store_transient_token(
        f"magic:{token}",
        {
            "email": email,
            "purpose": "invite",
            "user_uid": user_uid,
        },
        expires_at,
    )

    # Build magic link URL
    frontend_url = _get_frontend_url()
    magic_link = f"{frontend_url}/auth/email/verify?token={token}"

    # Send email
    sent = await send_magic_link_email(email, magic_link, purpose="invite")
    if not sent:
        await delete_transient_token(f"magic:{token}")
        raise RuntimeError(f"Failed to send invite email to {email}")

    return True


@router.post("/email/request")
async def request_magic_link(
    request: MagicLinkRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Request a magic link email for signup or password reset.

    Purpose:
    - "signup": Create new account or link email to existing account
    - "reset": Reset password (fails if email not registered)

    If Authorization header is provided with a valid Bearer token,
    the email will be linked to the authenticated user's account.
    """
    email = request.email.lower()
    purpose = request.purpose

    if purpose not in ("signup", "reset"):
        raise HTTPException(status_code=400, detail="Invalid purpose")

    # If authenticated, extract user_uid for account linking
    link_user_uid = None
    if authorization and authorization.startswith("Bearer "):
        try:
            link_user_uid = verify_token(authorization[7:], expected_type="access")
        except Exception:
            pass  # Invalid token is fine — treat as unauthenticated

    # Check if EMAIL auth already exists
    existing_email_auth = await get_auth_method_by_identifier("email", email)

    # Check if there's a Discord user with this contact_email (for merging)
    discord_user = await get_user_by_contact_email(email)
    discord_user_uid = discord_user.uid if discord_user else None

    if purpose == "signup":
        if existing_email_auth:
            raise HTTPException(
                status_code=409,
                detail="Email already registered. Use password login or reset.",
            )
    elif purpose == "reset":
        if not existing_email_auth and not discord_user_uid:
            raise HTTPException(
                status_code=404,
                detail="No account found with this email.",
            )

    # Generate token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES)
    await store_transient_token(
        f"magic:{token}",
        {
            "email": email,
            "purpose": purpose,
            "discord_user_uid": discord_user_uid,
            "user_uid": link_user_uid,
        },
        expires_at,
    )

    # Build magic link URL
    frontend_url = _get_frontend_url()
    magic_link = f"{frontend_url}/auth/email/verify?token={token}"

    # Send email with appropriate subject
    sent = await send_magic_link_email(email, magic_link, purpose=purpose)
    if not sent:
        await delete_transient_token(f"magic:{token}")
        raise HTTPException(status_code=500, detail="Failed to send email")

    return Response(
        content=encoder.encode(
            {
                "message": "Magic link sent",
                "email": email,
                "purpose": purpose,
            }
        ),
        media_type="application/json",
    )


@router.post("/email/verify")
async def verify_magic_link(request: MagicLinkVerifyRequest) -> Response:
    """Verify a magic link token.

    Returns a short-lived set-password token that allows the user to set their password.
    Does NOT log in directly - user must set password first.
    """
    stored = await get_transient_token(f"magic:{request.token}")
    if not stored:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Clean up magic link token (single use)
    await delete_transient_token(f"magic:{request.token}")

    # Generate a set-password token
    set_password_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=SET_PASSWORD_EXPIRE_MINUTES)
    await store_transient_token(
        f"setpwd:{set_password_token}",
        {
            "email": stored["email"],
            "purpose": stored["purpose"],
            "discord_user_uid": stored.get("discord_user_uid"),
            "user_uid": stored.get("user_uid"),  # For invite flow
        },
        expires_at,
    )

    return Response(
        content=encoder.encode(
            {
                "set_password_token": set_password_token,
                "email": stored["email"],
                "purpose": stored["purpose"],
                "expires_in": SET_PASSWORD_EXPIRE_MINUTES * 60,
            }
        ),
        media_type="application/json",
    )


@router.post("/email/set-password")
async def set_password(request: SetPasswordRequest) -> Response:
    """Set password after magic link verification.

    Creates user/auth method if signup, updates password if reset.
    Returns authentication tokens on success.
    """
    stored = await get_transient_token(f"setpwd:{request.token}")
    if not stored:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    # Clean up token (single use)
    await delete_transient_token(f"setpwd:{request.token}")

    email = stored["email"]
    purpose = stored["purpose"]
    discord_user_uid = stored.get("discord_user_uid")
    now = datetime.now(UTC)

    # Hash the password
    password_hash = ph.hash(request.password)

    # Check existing auth
    existing_email_auth = await get_auth_method_by_identifier("email", email)

    if purpose == "signup":
        if existing_email_auth:
            # Race condition: email was registered while user was setting password
            raise HTTPException(status_code=409, detail="Email already registered")

        link_user_uid = stored.get("user_uid")
        if link_user_uid:
            # Authenticated user linking email to their existing account
            user_uid = link_user_uid
        elif discord_user_uid:
            # Merge into Discord user: add EMAIL auth to existing user
            user_uid = discord_user_uid
        else:
            # Create new user
            user = User(
                uid=str(uuid7()),
                modified=now,
                name="",
                contact_email=email,
            )
            await insert_user(user)
            user_uid = user.uid

        # Create EMAIL auth method with password
        auth_method = AuthMethod(
            uid=str(uuid7()),
            modified=now,
            user_uid=user_uid,
            method_type=AuthMethodType.EMAIL,
            identifier=email,
            credential_hash=password_hash,
            verified=True,
            created_at=now,
            last_used_at=now,
        )
        await insert_auth_method(auth_method)

    elif purpose == "reset":
        if existing_email_auth:
            # Update existing EMAIL auth with new password
            user_uid = existing_email_auth.user_uid
            updated_auth = AuthMethod(
                uid=existing_email_auth.uid,
                modified=now,
                user_uid=existing_email_auth.user_uid,
                method_type=existing_email_auth.method_type,
                identifier=existing_email_auth.identifier,
                credential_hash=password_hash,
                verified=True,
                created_at=existing_email_auth.created_at,
                last_used_at=now,
            )
            await update_auth_method(updated_auth)

        elif discord_user_uid:
            # Discord user resetting: create EMAIL auth for them
            user_uid = discord_user_uid
            auth_method = AuthMethod(
                uid=str(uuid7()),
                modified=now,
                user_uid=user_uid,
                method_type=AuthMethodType.EMAIL,
                identifier=email,
                credential_hash=password_hash,
                verified=True,
                created_at=now,
                last_used_at=now,
            )
            await insert_auth_method(auth_method)

        else:
            raise HTTPException(status_code=404, detail="Account not found")

    elif purpose == "invite":
        # Invited user setting password for first time
        invite_user_uid = stored.get("user_uid")
        if not invite_user_uid:
            raise HTTPException(status_code=400, detail="Invalid invite token")

        if existing_email_auth:
            # Email already registered to another account
            raise HTTPException(status_code=409, detail="Email already registered")

        user_uid = invite_user_uid

        # Create EMAIL auth method linked to the existing user
        auth_method = AuthMethod(
            uid=str(uuid7()),
            modified=now,
            user_uid=user_uid,
            method_type=AuthMethodType.EMAIL,
            identifier=email,
            credential_hash=password_hash,
            verified=True,
            created_at=now,
            last_used_at=now,
        )
        await insert_auth_method(auth_method)

    else:
        raise HTTPException(status_code=400, detail="Invalid purpose")

    # Generate authentication tokens
    access_token, expires_in = create_access_token(user_uid)
    refresh_token = create_refresh_token(user_uid)

    response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
    return Response(
        content=response.model_dump_json(),
        media_type="application/json",
    )


@router.post("/me/calendar-token")
async def generate_calendar_token(
    authorization: str | None = Header(default=None),
) -> Response:
    """Generate or regenerate a calendar subscription token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )

    token = authorization[7:]
    user_uid = verify_token(token, expected_type="access")

    user = await get_user_by_uid(user_uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate new token
    cal_token = secrets.token_urlsafe(32)
    user.calendar_token = cal_token
    user.modified = datetime.now(UTC)
    await update_user(user)

    api_base = os.getenv("API_BASE_URL", "http://localhost:8000")
    calendar_url = f"{api_base}/api/calendar/tournaments.ics?token={cal_token}"

    return Response(
        content=encoder.encode(
            {
                "calendar_token": cal_token,
                "calendar_url": calendar_url,
            }
        ),
        media_type="application/json",
    )


@router.post("/refresh")
async def refresh_token(request: RefreshRequest) -> Response:
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


@router.get("/me")
async def get_current_user(
    authorization: str | None = Header(default=None),
) -> Response:
    """Get the current authenticated user.

    Requires Authorization header with Bearer token.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )

    token = authorization[7:]  # Remove "Bearer " prefix
    user_uid = verify_token(token, expected_type="access")

    user = await get_user_by_uid(user_uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get auth methods for this user (without credential hashes)
    auth_methods = await get_auth_methods_for_user(user_uid)
    methods_info = [
        {
            "type": m.method_type.value,
            "identifier": m.identifier,
            "verified": m.verified,
        }
        for m in auth_methods
    ]

    response_data = {
        "user": msgspec.to_builtins(user),
        "auth_methods": methods_info,
    }
    return Response(
        content=encoder.encode(response_data),
        media_type="application/json",
    )


@router.patch("/me")
async def update_current_user(
    request: ProfileUpdateRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Update the current authenticated user's profile.

    Only updates fields that are provided (non-None).
    Requires Authorization header with Bearer token.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )

    token = authorization[7:]
    user_uid = verify_token(token, expected_type="access")

    user = await get_user_by_uid(user_uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update only provided fields
    if request.name is not None:
        user.name = request.name
    if request.nickname is not None:
        user.nickname = request.nickname if request.nickname else None
    if request.country is not None:
        user.country = request.country.upper() if request.country else None
    if request.city is not None:
        user.city = request.city if request.city else None
    if request.contact_email is not None:
        user.contact_email = request.contact_email if request.contact_email else None
    if request.contact_phone is not None:
        user.contact_phone = request.contact_phone if request.contact_phone else None

    # Update modified timestamp
    user.modified = datetime.now(UTC)

    await update_user(user)

    # Return updated user with auth methods
    auth_methods = await get_auth_methods_for_user(user_uid)
    methods_info = [
        {
            "type": m.method_type.value,
            "identifier": m.identifier,
            "verified": m.verified,
        }
        for m in auth_methods
    ]

    response_data = {
        "user": msgspec.to_builtins(user),
        "auth_methods": methods_info,
    }
    return Response(
        content=encoder.encode(response_data),
        media_type="application/json",
    )


# =============================================================================
# Passkey (WebAuthn) Endpoints
# =============================================================================


@router.post("/passkey/register/options")
async def passkey_register_options(
    authorization: str = Header(..., description="Bearer token"),
) -> Response:
    """Generate passkey registration options for an authenticated user.

    User must be logged in to register a passkey.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[7:]
    user_uid = verify_token(token, expected_type="access")

    user = await get_user_by_uid(user_uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get existing passkey credentials to exclude
    auth_methods = await get_auth_methods_for_user(user_uid)
    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(m.identifier + "=="))
        for m in auth_methods
        if m.method_type == AuthMethodType.PASSKEY
    ]

    options = generate_registration_options(
        rp_id=WEBAUTHN_RP_ID,
        rp_name=WEBAUTHN_RP_NAME,
        user_id=user_uid.encode("utf-8"),
        user_name=user.name,
        user_display_name=user.name,
        exclude_credentials=exclude_credentials,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    # Store challenge for verification
    challenge_b64 = (
        base64.urlsafe_b64encode(options.challenge).decode("utf-8").rstrip("=")
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    await store_transient_token(
        f"challenge:{challenge_b64}",
        {
            "user_uid": user_uid,
            "type": "registration",
        },
        expires_at,
    )

    return Response(
        content=options_to_json(options),
        media_type="application/json",
    )


@router.post("/passkey/register/verify")
async def passkey_register_verify(
    request: PasskeyRegisterVerifyRequest,
    authorization: str = Header(..., description="Bearer token"),
) -> Response:
    """Verify passkey registration and save the credential."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[7:]
    user_uid = verify_token(token, expected_type="access")

    # Find the challenge
    client_data_json = base64.urlsafe_b64decode(
        request.credential["response"]["clientDataJSON"] + "=="
    )
    import json

    client_data = json.loads(client_data_json)
    challenge_b64 = client_data["challenge"]

    stored = await get_transient_token(f"challenge:{challenge_b64}")
    if not stored:
        raise HTTPException(status_code=400, detail="Challenge not found or expired")
    if stored["user_uid"] != user_uid:
        raise HTTPException(status_code=400, detail="Challenge mismatch")
    if stored["type"] != "registration":
        raise HTTPException(status_code=400, detail="Invalid challenge type")

    # Verify the registration
    try:
        verification = verify_registration_response(
            credential=request.credential,
            expected_challenge=base64.urlsafe_b64decode(challenge_b64 + "=="),
            expected_rp_id=WEBAUTHN_RP_ID,
            expected_origin=WEBAUTHN_ORIGIN,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Verification failed: {e}") from e

    # Clean up challenge
    await delete_transient_token(f"challenge:{challenge_b64}")

    # Store the credential
    credential_id_b64 = (
        base64.urlsafe_b64encode(verification.credential_id).decode("utf-8").rstrip("=")
    )
    public_key_b64 = (
        base64.urlsafe_b64encode(verification.credential_public_key)
        .decode("utf-8")
        .rstrip("=")
    )

    now = datetime.now(UTC)
    auth_method = AuthMethod(
        uid=str(uuid7()),
        modified=now,
        user_uid=user_uid,
        method_type=AuthMethodType.PASSKEY,
        identifier=credential_id_b64,  # Credential ID as identifier
        credential_hash=public_key_b64,  # Public key stored here
        verified=True,  # Passkeys are verified by definition
        created_at=now,
        last_used_at=now,
    )
    await insert_auth_method(auth_method)

    return Response(
        content=encoder.encode({"success": True}),
        media_type="application/json",
    )


@router.post("/passkey/create/options")
async def passkey_create_options() -> Response:
    """Generate passkey registration options for a new user.

    No authentication required - this creates a new account.
    Name is not required upfront; user will complete profile later.
    """
    # Generate a temporary user UID for the registration
    temp_user_uid = str(uuid7())

    # Use a placeholder name - will be updated when user completes profile
    placeholder_name = "VEKN User"

    options = generate_registration_options(
        rp_id=WEBAUTHN_RP_ID,
        rp_name=WEBAUTHN_RP_NAME,
        user_id=temp_user_uid.encode("utf-8"),
        user_name=placeholder_name,
        user_display_name=placeholder_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    # Store challenge for verification
    challenge_b64 = (
        base64.urlsafe_b64encode(options.challenge).decode("utf-8").rstrip("=")
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    await store_transient_token(
        f"challenge:{challenge_b64}",
        {
            "temp_user_uid": temp_user_uid,
            "type": "create",
        },
        expires_at,
    )

    return Response(
        content=options_to_json(options),
        media_type="application/json",
    )


@router.post("/passkey/create/verify")
async def passkey_create_verify(request: PasskeyRegisterVerifyRequest) -> Response:
    """Verify passkey registration and create new user account."""
    # Find the challenge
    client_data_json = base64.urlsafe_b64decode(
        request.credential["response"]["clientDataJSON"] + "=="
    )
    import json

    client_data = json.loads(client_data_json)
    challenge_b64 = client_data["challenge"]

    stored = await get_transient_token(f"challenge:{challenge_b64}")
    if not stored:
        raise HTTPException(status_code=400, detail="Challenge not found or expired")
    if stored["type"] != "create":
        raise HTTPException(status_code=400, detail="Invalid challenge type")

    # Verify the registration
    try:
        verification = verify_registration_response(
            credential=request.credential,
            expected_challenge=base64.urlsafe_b64decode(challenge_b64 + "=="),
            expected_rp_id=WEBAUTHN_RP_ID,
            expected_origin=WEBAUTHN_ORIGIN,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Verification failed: {e}") from e

    # Clean up challenge
    await delete_transient_token(f"challenge:{challenge_b64}")

    # Create the user with placeholder name
    now = datetime.now(UTC)
    user = User(
        uid=stored["temp_user_uid"],
        modified=now,
        name="",  # Empty name - user will complete profile later
    )
    await insert_user(user)

    # Store the credential
    credential_id_b64 = (
        base64.urlsafe_b64encode(verification.credential_id).decode("utf-8").rstrip("=")
    )
    public_key_b64 = (
        base64.urlsafe_b64encode(verification.credential_public_key)
        .decode("utf-8")
        .rstrip("=")
    )

    auth_method = AuthMethod(
        uid=str(uuid7()),
        modified=now,
        user_uid=user.uid,
        method_type=AuthMethodType.PASSKEY,
        identifier=credential_id_b64,
        credential_hash=public_key_b64,
        verified=True,
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


@router.post("/passkey/login/options")
async def passkey_login_options() -> Response:
    """Generate passkey authentication options.

    Uses discoverable credentials (resident keys) so no user identification needed.
    """
    options = generate_authentication_options(
        rp_id=WEBAUTHN_RP_ID,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    # Store challenge for verification
    challenge_b64 = (
        base64.urlsafe_b64encode(options.challenge).decode("utf-8").rstrip("=")
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    await store_transient_token(
        f"challenge:{challenge_b64}",
        {
            "type": "authentication",
        },
        expires_at,
    )

    return Response(
        content=options_to_json(options),
        media_type="application/json",
    )


@router.post("/passkey/login/verify")
async def passkey_login_verify(request: PasskeyLoginVerifyRequest) -> Response:
    """Verify passkey authentication and issue tokens."""
    # Extract credential ID to find the user
    credential_id_raw = request.credential.get("id", "")
    # The id is already base64url encoded from the browser
    credential_id_b64 = credential_id_raw.rstrip("=")

    # Find the auth method by credential ID
    auth_method = await get_auth_method_by_identifier("passkey", credential_id_b64)
    if not auth_method:
        raise HTTPException(status_code=401, detail="Passkey not found")

    # Find the challenge
    client_data_json = base64.urlsafe_b64decode(
        request.credential["response"]["clientDataJSON"] + "=="
    )
    import json

    client_data = json.loads(client_data_json)
    challenge_b64 = client_data["challenge"]

    stored = await get_transient_token(f"challenge:{challenge_b64}")
    if not stored:
        raise HTTPException(status_code=400, detail="Challenge not found or expired")
    if stored["type"] != "authentication":
        raise HTTPException(status_code=400, detail="Invalid challenge type")

    # Verify the authentication
    assert auth_method.credential_hash is not None
    try:
        public_key = base64.urlsafe_b64decode(auth_method.credential_hash + "==")
        verification = verify_authentication_response(
            credential=request.credential,
            expected_challenge=base64.urlsafe_b64decode(challenge_b64 + "=="),
            expected_rp_id=WEBAUTHN_RP_ID,
            expected_origin=WEBAUTHN_ORIGIN,
            credential_public_key=public_key,
            credential_current_sign_count=auth_method.sign_count,
        )
    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Authentication failed: {e}"
        ) from e

    # Clean up challenge
    await delete_transient_token(f"challenge:{challenge_b64}")

    # Update last_used_at and sign_count
    now = datetime.now(UTC)
    updated_auth_method = AuthMethod(
        uid=auth_method.uid,
        modified=now,
        user_uid=auth_method.user_uid,
        method_type=auth_method.method_type,
        identifier=auth_method.identifier,
        credential_hash=auth_method.credential_hash,
        verified=auth_method.verified,
        created_at=auth_method.created_at,
        last_used_at=now,
        sign_count=verification.new_sign_count,
    )
    await update_auth_method(updated_auth_method)

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


# =============================================================================
# Discord OAuth Endpoints
# =============================================================================


@router.get("/discord/authorize")
async def discord_authorize(
    link: bool = Query(
        False, description="Set to true to link Discord to existing account"
    ),
    redirect: str = Query(
        "/profile", description="Frontend path to redirect after OAuth"
    ),
    token: str | None = Query(
        None,
        description="Access token for link mode (since headers can't be sent during redirect)",
    ),
    authorization: str | None = Header(default=None),
) -> RedirectResponse:
    """Initiate Discord OAuth flow.

    If link=true and user is authenticated, links Discord to their account.
    Otherwise, creates a new account or logs in with Discord.
    """
    client_id, client_secret, redirect_uri, frontend_url = _get_discord_config()

    if not client_id:
        raise HTTPException(status_code=500, detail="Discord OAuth not configured")

    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state with optional user_uid for linking
    state_data: dict = {
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        "link_mode": link,
        "redirect": redirect,
    }

    # If linking, verify user is authenticated (accept token from query param or header)
    if link:
        auth_token = token
        if not auth_token and authorization and authorization.startswith("Bearer "):
            auth_token = authorization[7:]

        if not auth_token:
            raise HTTPException(
                status_code=401,
                detail="Must be authenticated to link Discord account",
            )
        user_uid = verify_token(auth_token, expected_type="access")
        state_data["user_uid"] = user_uid

    expires_at = state_data.pop("expires_at", datetime.now(UTC) + timedelta(minutes=5))
    await store_transient_token(f"discord:{state}", state_data, expires_at)

    # Build Discord OAuth URL
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify email",
        "state": state,
    }
    discord_auth_url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"

    return RedirectResponse(url=discord_auth_url, status_code=302)


@router.get("/discord/callback")
async def discord_callback(
    code: str = Query(..., description="Authorization code from Discord"),
    state: str = Query(..., description="CSRF state token"),
) -> RedirectResponse:
    """Handle Discord OAuth callback.

    Exchanges code for tokens, fetches user info, and either:
    - Links Discord to existing account (if link mode)
    - Logs in existing user (if Discord ID found)
    - Creates new account (if Discord ID not found)
    """
    client_id, client_secret, redirect_uri, frontend_url = _get_discord_config()

    # Validate state
    stored = await get_transient_token(f"discord:{state}")
    if not stored:
        return RedirectResponse(
            url=f"{frontend_url}/login?error=invalid_state", status_code=302
        )

    # Clean up state (single use)
    await delete_transient_token(f"discord:{state}")

    link_mode = stored.get("link_mode", False)
    user_uid_from_state = stored.get("user_uid")
    redirect_path = stored.get("redirect", "/profile" if link_mode else "/")

    # Exchange code for Discord tokens
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            ) as token_response:
                if token_response.status != 200:
                    error_text = await token_response.text()
                    logger.error(f"Discord token exchange failed: {error_text}")
                    return RedirectResponse(
                        url=f"{frontend_url}/login?error=discord_token_failed",
                        status_code=302,
                    )
                discord_tokens = await token_response.json()
        except Exception as e:
            logger.error(f"Discord token exchange error: {e}")
            return RedirectResponse(
                url=f"{frontend_url}/login?error=discord_error", status_code=302
            )

        # Fetch Discord user info
        try:
            async with session.get(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {discord_tokens['access_token']}"},
            ) as user_response:
                if user_response.status != 200:
                    error_text = await user_response.text()
                    logger.error(f"Discord user fetch failed: {error_text}")
                    return RedirectResponse(
                        url=f"{frontend_url}/login?error=discord_user_failed",
                        status_code=302,
                    )
                discord_user = await user_response.json()
        except Exception as e:
            logger.error(f"Discord user fetch error: {e}")
            return RedirectResponse(
                url=f"{frontend_url}/login?error=discord_error", status_code=302
            )

    discord_id = discord_user["id"]
    discord_username = discord_user.get("username", "")
    discord_global_name = discord_user.get("global_name")  # Display name, may be None
    # Only use Discord email if verified
    discord_email_verified = discord_user.get("verified", False)
    discord_email = discord_user.get("email") if discord_email_verified else None

    # Check if Discord ID is already linked to an account
    existing_auth = await get_auth_method_by_identifier("discord", discord_id)

    if link_mode and user_uid_from_state:
        # === LINK MODE ===
        if existing_auth:
            if existing_auth.user_uid == user_uid_from_state:
                # Already linked to this user
                return RedirectResponse(
                    url=f"{frontend_url}{redirect_path}?discord_linked=already",
                    status_code=302,
                )
            else:
                # Discord is linked to another account - merge accounts
                # This reassigns all auth methods (including Discord) to keep_uid
                merged = await merge_users(user_uid_from_state, existing_auth.user_uid)
                if not merged:
                    return RedirectResponse(
                        url=f"{frontend_url}{redirect_path}?error=merge_failed",
                        status_code=302,
                    )
                # Auth method already reassigned by merge - don't create new one
        else:
            # No existing auth - create new auth method linking Discord to this user
            now = datetime.now(UTC)
            auth_method = AuthMethod(
                uid=str(uuid7()),
                modified=now,
                user_uid=user_uid_from_state,
                method_type=AuthMethodType.DISCORD,
                identifier=discord_id,
                credential_hash=None,
                verified=True,
                created_at=now,
                last_used_at=now,
            )
            await insert_auth_method(auth_method)

        # Update user's contact_discord and nickname from Discord
        user = await get_user_by_uid(user_uid_from_state)
        if user:
            changed = False
            if not user.contact_discord:
                user.contact_discord = discord_username
                changed = True
            if not user.nickname and discord_global_name:
                user.nickname = discord_global_name
                changed = True
            if changed:
                user.modified = datetime.now(UTC)
                await update_user(user)

        return RedirectResponse(
            url=f"{frontend_url}{redirect_path}?discord_linked=success",
            status_code=302,
        )

    else:
        # === LOGIN/SIGNUP MODE ===
        if existing_auth:
            # Login to existing account
            user_uid = existing_auth.user_uid

            # Update last_used_at
            now = datetime.now(UTC)
            updated_auth = AuthMethod(
                uid=existing_auth.uid,
                modified=now,
                user_uid=existing_auth.user_uid,
                method_type=existing_auth.method_type,
                identifier=existing_auth.identifier,
                credential_hash=existing_auth.credential_hash,
                verified=existing_auth.verified,
                created_at=existing_auth.created_at,
                last_used_at=now,
            )
            await update_auth_method(updated_auth)
        else:
            # Check if verified email matches an existing EMAIL auth user
            email_auth_user_uid = None
            if discord_email:
                email_auth = await get_auth_method_by_identifier(
                    "email", discord_email.lower()
                )
                if email_auth:
                    # Merge Discord into existing email user
                    email_auth_user_uid = email_auth.user_uid

            now = datetime.now(UTC)

            if email_auth_user_uid:
                # Add Discord auth to existing email user
                user_uid = email_auth_user_uid
                auth_method = AuthMethod(
                    uid=str(uuid7()),
                    modified=now,
                    user_uid=user_uid,
                    method_type=AuthMethodType.DISCORD,
                    identifier=discord_id,
                    credential_hash=None,
                    verified=True,
                    created_at=now,
                    last_used_at=now,
                )
                await insert_auth_method(auth_method)

                # Update user's contact_discord and nickname if not set
                user = await get_user_by_uid(user_uid)
                if user:
                    changed = False
                    if not user.contact_discord:
                        user.contact_discord = discord_username
                        changed = True
                    if not user.nickname and discord_global_name:
                        user.nickname = discord_global_name
                        changed = True
                    if changed:
                        user.modified = now
                        await update_user(user)
            else:
                # Create new account
                user = User(
                    uid=str(uuid7()),
                    modified=now,
                    name=discord_username or "",
                    nickname=discord_global_name,
                    contact_discord=discord_username,
                    contact_email=discord_email,
                )
                await insert_user(user)
                user_uid = user.uid

                # Create Discord auth method
                auth_method = AuthMethod(
                    uid=str(uuid7()),
                    modified=now,
                    user_uid=user_uid,
                    method_type=AuthMethodType.DISCORD,
                    identifier=discord_id,
                    credential_hash=None,
                    verified=True,
                    created_at=now,
                    last_used_at=now,
                )
                await insert_auth_method(auth_method)

        # Generate tokens
        access_token, _ = create_access_token(user_uid)
        refresh_token = create_refresh_token(user_uid)

        # Redirect to frontend with tokens
        params = urlencode({"token": access_token, "refresh": refresh_token})
        return RedirectResponse(
            url=f"{frontend_url}/login?{params}",
            status_code=302,
        )
