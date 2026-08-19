"""Profile endpoints: /me GET, /me PATCH, calendar token."""

import os
import secrets
import time
from datetime import UTC, datetime

import msgspec
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ... import permissions
from ...broadcast import broadcast_precomputed
from ...community_links import (
    moderation_for,
    validated_country,
    validated_languages,
    validated_type,
)
from ...db import (
    get_auth_methods_for_user,
    get_calendar_token,
    save_user,
)
from ...link_preview import LinkPreviewError, fetch_link_title
from ...middleware.auth import CurrentUser
from ...models import CommunityLink

router = APIRouter()
encoder = msgspec.json.Encoder()


class CommunityLinkInput(BaseModel):
    type: str
    url: str
    label: str = ""
    languages: list[str] = []
    country: str | None = None
    state: str | None = None


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    nickname: str | None = None
    country: str | None = None
    city: str | None = None
    city_geoname_id: int | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    phone_is_whatsapp: bool | None = None
    community_links: list[CommunityLinkInput] | None = None


@router.get("/me")
async def get_me(current_user: CurrentUser) -> Response:
    user = current_user

    # Surface the owner's calendar feed token (kept out of all projections).
    user.calendar_token = await get_calendar_token(user.uid)

    auth_methods = await get_auth_methods_for_user(user.uid)
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
    current_user: CurrentUser,
) -> Response:
    user = current_user

    # Self-edits must land in local_modifications, or the VEKN sync and the
    # legacy-archon merge — both skip locally-modified fields — silently revert them.
    local_mods = set(user.local_modifications)

    if request.name is not None:
        user.name = request.name
        local_mods.add("name")
    if request.nickname is not None:
        user.nickname = request.nickname if request.nickname else None
        local_mods.add("nickname")
    if request.country is not None:
        new_country = request.country.upper() if request.country else None
        # An NC/Prince can't change their own country: it scopes their FULL-data
        # overlay, so a self-edit would be an unauthorized scope change.
        if new_country != user.country and not permissions.can_change_country(
            user, user
        ):
            raise HTTPException(
                status_code=403,
                detail="An NC or Prince cannot change their own country; "
                "it must be changed by IC (or the country's NC for a Prince).",
            )
        user.country = new_country
        local_mods.add("country")
    if request.city is not None:
        user.city = request.city if request.city else None
        local_mods.add("city")
        if not request.city:
            user.city_geoname_id = None
            local_mods.add("city_geoname_id")
    if request.city_geoname_id is not None:
        user.city_geoname_id = (
            request.city_geoname_id if request.city_geoname_id else None
        )
        local_mods.add("city_geoname_id")
    if request.contact_email is not None:
        user.contact_email = request.contact_email if request.contact_email else None
        local_mods.add("contact_email")
    if request.contact_phone is not None:
        user.contact_phone = request.contact_phone if request.contact_phone else None
        local_mods.add("contact_phone")
    if request.phone_is_whatsapp is not None:
        user.phone_is_whatsapp = request.phone_is_whatsapp
        local_mods.add("phone_is_whatsapp")
    if request.community_links is not None:
        if not user.vekn_id:
            raise HTTPException(
                status_code=403,
                detail="VEKN membership required to add community links",
            )
        is_official = permissions.is_official(user)
        max_links = 10 if is_official else 5
        if len(request.community_links) > max_links:
            raise HTTPException(
                status_code=422,
                detail=f"Maximum {max_links} community links allowed",
            )
        links = []
        existing_by_url = {existing.url: existing for existing in user.community_links}
        for link in request.community_links:
            link_type = validated_type(link.type)
            if not link.url.startswith(("http://", "https://")):
                raise HTTPException(status_code=422, detail=f"Invalid URL: {link.url}")
            prior = existing_by_url.get(link.url)
            languages = validated_languages(link.languages, link_type, prior)
            country = validated_country(link.country, user.country)
            mod = prior.moderation if prior else None
            if link.state is not None:
                mod = moderation_for(user, link.state, country, mod)
            links.append(
                CommunityLink(
                    type=link_type,
                    url=link.url,
                    label=link.label,
                    languages=languages,
                    country=country,
                    moderation=mod,
                )
            )
        user.community_links = links

    user.modified = datetime.now(UTC)
    user.local_modifications = local_mods

    bd = await save_user(user)
    broadcast_precomputed(bd)

    # Surface the owner's calendar feed token (preserved by COALESCE, not in "full").
    user.calendar_token = await get_calendar_token(user.uid)

    auth_methods = await get_auth_methods_for_user(user.uid)
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


# In-process (per-worker) quota on the one route that fetches an address a
# member typed. Generous enough to edit a full set of links in one sitting.
_TITLE_BURST = 10
_TITLE_DAILY_CAP = 100
_title_calls: dict[str, list[float]] = {}


def _title_quota_exceeded(user_uid: str) -> bool:
    now = time.monotonic()
    times = [t for t in _title_calls.get(user_uid, []) if now - t < 86400]
    exceeded = (
        len(times) >= _TITLE_DAILY_CAP
        or len([t for t in times if now - t < 60]) >= _TITLE_BURST
    )
    if not exceeded:
        times.append(now)
    _title_calls[user_uid] = times
    return exceeded


@router.get("/me/link-title")
async def read_link_title(url: str, current_user: CurrentUser) -> Response:
    """Suggest a label for a community link from the target's own title."""
    if not current_user.vekn_id:
        raise HTTPException(
            status_code=403, detail="VEKN membership required to add community links"
        )
    if _title_quota_exceeded(current_user.uid):
        raise HTTPException(
            status_code=429, detail="Too many link lookups — try again in a minute"
        )
    try:
        title = await fetch_link_title(url)
    except LinkPreviewError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return Response(
        content=encoder.encode({"title": title}), media_type="application/json"
    )


@router.post("/me/calendar-token")
async def generate_calendar_token(current_user: CurrentUser) -> Response:
    user = current_user

    cal_token = secrets.token_urlsafe(32)
    user.calendar_token = cal_token
    user.modified = datetime.now(UTC)
    await save_user(user)

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
