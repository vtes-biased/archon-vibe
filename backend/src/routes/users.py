"""User API endpoints."""

import json
import logging
from datetime import UTC, datetime
from typing import Annotated

import msgspec
from archon_engine import PyEngine
from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from uuid6 import uuid7

from ..db import (
    allocate_next_vekn_id,
    get_user_by_uid,
    set_user_resync_after,
)
from ..db import delete_avatar as db_delete_avatar
from ..db import get_avatar as db_get_avatar
from ..db import insert_user as db_insert_user
from ..db import update_user as db_update_user
from ..db import upsert_avatar as db_upsert_avatar
from ..middleware.auth import CurrentUser, OptionalUser
from ..models import CommunityLink, LinkModeration, Role, User
from ..utils import user_to_context
from .auth import send_invite_email

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger(__name__)
# Encoder with decimal_format to handle all types properly
encoder = msgspec.json.Encoder()

from ..broadcast import broadcast_precomputed, broadcast_resync

# Rust engine for permission checks
_engine = PyEngine()


def _can_change_role(manager: User, role: Role, target_user: User) -> bool:
    """Check if manager can change a specific role on target user (uses Rust engine)."""
    result_json = _engine.can_change_role(
        json.dumps(user_to_context(manager)),
        json.dumps(user_to_context(target_user)),
        role.value,
    )
    result = json.loads(result_json)
    return result["allowed"]


@router.post("/", status_code=201)
async def create_user(
    name: str,
    country: str,
    current_user: OptionalUser = None,
    city: str | None = None,
    city_geoname_id: int | None = None,
    state: str | None = None,
    nickname: str | None = None,
    email: str | None = None,
    roles: Annotated[list[str] | None, Query()] = None,
) -> Response:
    """Create a new user.

    Auto-allocates a VEKN ID for the new user.
    If email is provided, sends an invite email so they can log in.
    """
    # Authenticate current user
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Only IC, NC, or Prince can create users
    allowed_roles = {Role.IC, Role.NC, Role.PRINCE}
    if not any(role in current_user.roles for role in allowed_roles):
        raise HTTPException(
            status_code=403,
            detail="Only IC, NC, or Prince can create users",
        )

    # Validate and convert roles if provided
    validated_roles: list[Role] = []
    if roles is not None:
        for role_str in roles:
            if not role_str:  # Skip empty strings
                continue
            try:
                validated_roles.append(Role(role_str))
            except ValueError as err:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid role: {role_str}. Valid roles: {[r.value for r in Role]}",
                ) from err

    # Auto-allocate VEKN ID
    vekn_id = await allocate_next_vekn_id()

    user = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name=name,
        country=country,
        vekn_id=vekn_id,
        city=city,
        city_geoname_id=city_geoname_id,
        state=state,
        nickname=nickname,
        contact_email=email.lower() if email else None,
        roles=validated_roles,
        coopted_by=current_user.uid,
        coopted_at=datetime.now(UTC),
    )

    # Check role permissions if assigning roles
    for role in validated_roles:
        if not _can_change_role(current_user, role, user):
            raise HTTPException(
                status_code=403,
                detail=f"You don't have permission to assign the {role.value} role",
            )

    bd = await db_insert_user(user)

    # Send invite email if provided
    if email:
        try:
            await send_invite_email(email.lower(), user.uid, user.name)
            logger.info(f"Invite email sent to {email} for user {user.uid}")
        except Exception as e:
            logger.error(f"Failed to send invite email to {email}: {e}")
            # Don't fail the request, user is already created

    # Broadcast to SSE clients
    broadcast_precomputed(bd)

    return Response(
        content=encoder.encode(user),
        media_type="application/json",
        status_code=201,
    )



@router.put("/{uid}")
async def update_user(
    uid: str,
    current_user: OptionalUser = None,
    name: str | None = None,
    country: str | None = None,
    vekn_id: str | None = None,
    city: str | None = None,
    city_geoname_id: int | None = None,
    state: str | None = None,
    nickname: str | None = None,
    roles: Annotated[list[str] | None, Query()] = None,
) -> Response:
    """Update an existing user."""
    # Authenticate current user
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Fetch existing user
    user = await get_user_by_uid(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    old_roles = set(user.roles)
    old_vekn_id = user.vekn_id

    # Track which fields are being modified locally
    local_mods = set(user.local_modifications)

    # Validate and convert roles if provided
    validated_roles: list[Role] | None = None
    if roles is not None:
        validated_roles = []
        # Filter out empty strings (used to signal "clear all roles")
        for role_str in roles:
            if not role_str:  # Skip empty strings
                continue
            try:
                validated_roles.append(Role(role_str))
            except ValueError as err:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid role: {role_str}. Valid roles: {[r.value for r in Role]}",
                ) from err

        # Check permission for each role change
        old_roles = set(user.roles)
        new_roles = set(validated_roles)
        added_roles = new_roles - old_roles
        removed_roles = old_roles - new_roles

        for role in added_roles | removed_roles:
            if not _can_change_role(current_user, role, user):
                raise HTTPException(
                    status_code=403,
                    detail=f"You don't have permission to change the {role.value} role",
                )

        # Ensure target has VEKN ID if any roles are being set
        if validated_roles and not user.vekn_id and not vekn_id:
            raise HTTPException(
                status_code=400,
                detail="User must have a VEKN ID to be assigned roles",
            )

        local_mods.add("roles")

    # Update fields - only if at least one field is being updated
    if (
        name is not None
        or country is not None
        or vekn_id is not None
        or city is not None
        or city_geoname_id is not None
        or state is not None
        or nickname is not None
        or validated_roles is not None
    ):
        # Track which fields are modified
        if name is not None:
            local_mods.add("name")
        if country is not None:
            local_mods.add("country")
        if city is not None:
            local_mods.add("city")
        if city_geoname_id is not None:
            local_mods.add("city_geoname_id")
        if state is not None:
            local_mods.add("state")
        if nickname is not None:
            local_mods.add("nickname")

        user = msgspec.structs.replace(
            user,
            modified=datetime.now(UTC),
            name=name if name is not None else user.name,
            country=country if country is not None else user.country,
            vekn_id=vekn_id if vekn_id is not None else user.vekn_id,
            city=city if city is not None else user.city,
            city_geoname_id=city_geoname_id if city_geoname_id is not None else user.city_geoname_id,
            state=state if state is not None else user.state,
            nickname=nickname if nickname is not None else user.nickname,
            roles=validated_roles if validated_roles is not None else user.roles,
            local_modifications=local_mods,
        )

    # Save to database
    bd = await db_update_user(user)

    # Trigger resync if roles or vekn_id changed
    if set(user.roles) != old_roles or user.vekn_id != old_vekn_id:
        await set_user_resync_after(user.uid)
        await broadcast_resync(user.uid)

    # Broadcast to SSE clients
    broadcast_precomputed(bd)

    return Response(
        content=encoder.encode(user),
        media_type="application/json",
    )


# Avatar endpoints
MAX_AVATAR_SIZE = 1024 * 1024  # 1MB


@router.post("/{uid}/avatar")
async def upload_avatar(
    uid: str,
    file: UploadFile,
    current_user: OptionalUser = None,
) -> Response:
    """Upload or update user avatar.

    Expects a webp image, max 1MB. Client should resize/crop before upload.
    """
    # Authenticate
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Users can only upload their own avatar
    if current_user.uid != uid:
        raise HTTPException(status_code=403, detail="Can only upload your own avatar")

    # Validate content type
    if file.content_type not in ("image/webp", "image/png", "image/jpeg"):
        raise HTTPException(
            status_code=400,
            detail="Avatar must be webp, png, or jpeg",
        )

    # Read and validate size
    data = await file.read()
    if len(data) > MAX_AVATAR_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Avatar too large. Max size: {MAX_AVATAR_SIZE // 1024}KB",
        )

    # Store in database
    await db_upsert_avatar(uid, data, file.content_type or "image/webp")

    # Update user's avatar_path
    user = await get_user_by_uid(uid)
    if user:
        updated_user = msgspec.structs.replace(
            user,
            modified=datetime.now(UTC),
            avatar_path=f"/api/users/{uid}/avatar",
        )
        bd = await db_update_user(updated_user)

        # Broadcast user update via SSE
        broadcast_precomputed(bd)

    return Response(
        content=b'{"success": true}',
        media_type="application/json",
    )


@router.get("/{uid}/avatar")
async def get_avatar(uid: str) -> Response:
    """Get user avatar image.

    Returns the binary image with appropriate content type.
    Includes cache headers for browser caching.
    """
    result = await db_get_avatar(uid)
    if not result:
        raise HTTPException(status_code=404, detail="Avatar not found")

    data, content_type = result
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            "Content-Length": str(len(data)),
        },
    )


@router.delete("/{uid}/avatar")
async def delete_avatar(
    uid: str,
    current_user: OptionalUser = None,
) -> Response:
    """Delete user avatar."""
    # Authenticate
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Users can only delete their own avatar
    if current_user.uid != uid:
        raise HTTPException(status_code=403, detail="Can only delete your own avatar")

    # Delete from database
    deleted = await db_delete_avatar(uid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Avatar not found")

    # Update user's avatar_path to None
    user = await get_user_by_uid(uid)
    if user:
        updated_user = msgspec.structs.replace(
            user,
            modified=datetime.now(UTC),
            avatar_path=None,
        )
        bd = await db_update_user(updated_user)

        # Broadcast user update via SSE
        broadcast_precomputed(bd)

    return Response(
        content=b'{"success": true}',
        media_type="application/json",
    )


class LinkModerationRequest(BaseModel):
    url: str  # link URL to moderate
    action: str  # "hide" | "promote" | "clear"


@router.patch("/{user_uid}/community-link-moderation")
async def moderate_community_link(
    user_uid: str,
    request: LinkModerationRequest,
    current_user: CurrentUser,
) -> Response:
    """Moderate a community link on a target user.

    Only IC, or NC/Prince in the same country as the target user, can moderate.
    """
    # Cannot moderate your own links
    if current_user.uid == user_uid:
        raise HTTPException(status_code=403, detail="Cannot moderate your own links")

    # Check moderator role
    is_ic = Role.IC in current_user.roles
    is_nc_prince = Role.NC in current_user.roles or Role.PRINCE in current_user.roles
    if not is_ic and not is_nc_prince:
        raise HTTPException(status_code=403, detail="Only IC/NC/Prince can moderate links")

    # Get target user
    target = await get_user_by_uid(user_uid)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # NC/Prince can only moderate in their own country
    if is_nc_prince and not is_ic and current_user.country != target.country:
        raise HTTPException(status_code=403, detail="Can only moderate links in your country")

    if request.action not in ("hide", "promote", "clear"):
        raise HTTPException(status_code=422, detail="Action must be 'hide', 'promote', or 'clear'")

    # Find and update the link
    updated_links = []
    found = False
    for link in target.community_links:
        if link.url == request.url:
            found = True
            if request.action == "clear":
                updated_links.append(CommunityLink(
                    type=link.type, url=link.url, label=link.label,
                    language=link.language, moderation=None,
                ))
            else:
                mod = LinkModeration(
                    status="hidden" if request.action == "hide" else "promoted",
                    by=current_user.uid,
                    at=datetime.now(UTC),
                )
                updated_links.append(CommunityLink(
                    type=link.type, url=link.url, label=link.label,
                    language=link.language, moderation=mod,
                ))
        else:
            updated_links.append(link)

    if not found:
        raise HTTPException(status_code=404, detail="Link not found on target user")

    target.community_links = updated_links
    target.modified = datetime.now(UTC)
    bd = await db_update_user(target)
    broadcast_precomputed(bd)

    return Response(content=b'{"success": true}', media_type="application/json")
