"""Passkey (WebAuthn) authentication endpoints."""

import base64
import json
import os
from datetime import UTC, datetime, timedelta

import msgspec
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
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

from ...db import (
    delete_transient_token,
    get_auth_method_by_identifier,
    get_auth_methods_for_user,
    get_transient_token,
    get_user_by_uid,
    insert_auth_method,
    insert_user,
    store_transient_token,
    update_auth_method,
)
from ...models import AuthMethod, AuthMethodType, User
from ._tokens import TokenResponse, create_access_token, create_refresh_token, verify_token

router = APIRouter()
encoder = msgspec.json.Encoder()

# WebAuthn settings
WEBAUTHN_RP_ID = os.getenv("WEBAUTHN_RP_ID", "localhost")
WEBAUTHN_RP_NAME = os.getenv("WEBAUTHN_RP_NAME", "Archon")
WEBAUTHN_ORIGIN = os.getenv("WEBAUTHN_ORIGIN", "http://localhost:5173")


class PasskeyRegisterVerifyRequest(BaseModel):
    """Passkey registration verification request."""

    credential: dict  # Raw credential from navigator.credentials.create()


class PasskeyLoginVerifyRequest(BaseModel):
    """Passkey login verification request."""

    credential: dict  # Raw credential from navigator.credentials.get()


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
