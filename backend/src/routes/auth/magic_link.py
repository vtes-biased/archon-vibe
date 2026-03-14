"""Magic link email authentication and set-password endpoints."""

import os
import secrets
from datetime import UTC, datetime, timedelta

import msgspec
from argon2 import PasswordHasher
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, EmailStr
from uuid6 import uuid7

from ...db import (
    delete_transient_token,
    get_auth_method_by_identifier,
    get_transient_token,
    get_user_by_contact_email,
    insert_auth_method,
    insert_user,
    store_transient_token,
    update_auth_method,
)
from ...email_service import send_magic_link_email
from ...models import AuthMethod, AuthMethodType, User
from ._tokens import TokenResponse, create_access_token, create_refresh_token, verify_token

router = APIRouter()
encoder = msgspec.json.Encoder()
ph = PasswordHasher()

# Magic link settings
MAGIC_LINK_EXPIRE_MINUTES = 15
SET_PASSWORD_EXPIRE_MINUTES = 10


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
            pass  # Invalid token is fine -- treat as unauthenticated

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

    # Generate a set-password token (magic token stays valid until password is set)
    set_password_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=SET_PASSWORD_EXPIRE_MINUTES)
    await store_transient_token(
        f"setpwd:{set_password_token}",
        {
            "email": stored["email"],
            "purpose": stored["purpose"],
            "discord_user_uid": stored.get("discord_user_uid"),
            "user_uid": stored.get("user_uid"),  # For invite flow
            "magic_token": request.token,  # To clean up when password is set
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

    # Clean up both tokens (single use)
    await delete_transient_token(f"setpwd:{request.token}")
    if magic_token := stored.get("magic_token"):
        await delete_transient_token(f"magic:{magic_token}")

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
