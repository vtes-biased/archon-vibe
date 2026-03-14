"""Profile endpoints: /me GET, /me PATCH, calendar token."""

import os
import secrets
from datetime import UTC, datetime

import msgspec
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel

from ...broadcast import broadcast_precomputed
from ...db import get_auth_methods_for_user, get_user_by_uid, update_user
from ...models import CommunityLink, CommunityLinkType, Role
from ._tokens import TokenResponse, create_access_token, create_refresh_token, verify_token

router = APIRouter()
encoder = msgspec.json.Encoder()


class CommunityLinkInput(BaseModel):
    """Community link input for profile update."""

    type: str
    url: str
    label: str = ""


class ProfileUpdateRequest(BaseModel):
    """Profile update request payload."""

    name: str | None = None
    nickname: str | None = None
    country: str | None = None
    city: str | None = None
    city_geoname_id: int | None = None
    contact_email: str | None = None
    contact_discord: str | None = None
    contact_phone: str | None = None
    phone_is_whatsapp: bool | None = None
    community_links: list[CommunityLinkInput] | None = None


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
        if not request.city:
            user.city_geoname_id = None
    if request.city_geoname_id is not None:
        user.city_geoname_id = request.city_geoname_id if request.city_geoname_id else None
    if request.contact_email is not None:
        user.contact_email = request.contact_email if request.contact_email else None
    if request.contact_discord is not None:
        user.contact_discord = request.contact_discord if request.contact_discord else None
    if request.contact_phone is not None:
        user.contact_phone = request.contact_phone if request.contact_phone else None
    if request.phone_is_whatsapp is not None:
        user.phone_is_whatsapp = request.phone_is_whatsapp
    if request.community_links is not None:
        # Only officials can set community links
        is_official = any(
            r in (Role.IC, Role.NC, Role.PRINCE) for r in user.roles
        )
        if not is_official:
            raise HTTPException(
                status_code=403,
                detail="Only officials (IC/NC/Prince) can manage community links",
            )
        if len(request.community_links) > 10:
            raise HTTPException(
                status_code=422, detail="Maximum 10 community links allowed"
            )
        links = []
        for link in request.community_links:
            try:
                link_type = CommunityLinkType(link.type)
            except ValueError:
                raise HTTPException(
                    status_code=422, detail=f"Invalid link type: {link.type}"
                )
            if not link.url.startswith(("http://", "https://")):
                raise HTTPException(
                    status_code=422, detail=f"Invalid URL: {link.url}"
                )
            links.append(CommunityLink(type=link_type, url=link.url, label=link.label))
        user.community_links = links

    # Update modified timestamp
    user.modified = datetime.now(UTC)

    bd = await update_user(user)
    broadcast_precomputed(bd)

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
