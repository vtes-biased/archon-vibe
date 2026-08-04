"""User API endpoints."""

import logging
from datetime import UTC, datetime
from uuid import uuid7

import msgspec
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import permissions
from ..broadcast import broadcast_precomputed, broadcast_resync
from ..db import (
    allocate_next_vekn_id,
    get_user_by_contact_email,
    get_user_by_uid,
    soft_delete_user,
)
from ..db import delete_avatar as db_delete_avatar
from ..db import get_avatar as db_get_avatar
from ..db import save_user as db_save_user
from ..db import upsert_avatar as db_upsert_avatar
from ..middleware.auth import CurrentUser, OptionalUser
from ..models import LinkModeration, Role, User
from .auth import send_invite_email

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger(__name__)
# Encoder with decimal_format to handle all types properly
encoder = msgspec.json.Encoder()


class CreateUserRequest(BaseModel):
    """JSON body for POST /api/users/."""

    name: str
    country: str
    city: str | None = None
    city_geoname_id: int | None = None
    state: str | None = None
    nickname: str | None = None
    email: str | None = None
    roles: list[str] | None = None


class UpdateUserRequest(BaseModel):
    """JSON body for PUT /api/users/{uid}. All fields optional (omit = leave unchanged)."""

    name: str | None = None
    country: str | None = None
    city: str | None = None
    city_geoname_id: int | None = None
    state: str | None = None
    nickname: str | None = None
    roles: list[str] | None = None


@router.post("/", status_code=201)
async def create_user(
    body: CreateUserRequest, current_user: OptionalUser = None
) -> Response:
    """Create a new user.

    Auto-allocates a VEKN ID for the new user.
    If email is provided, sends an invite email so they can log in.
    """
    name = body.name
    # Normalize country casing: storage + the same-country overlay match
    # (broadcast.py) compare exact, so a raw lower-case payload would corrupt it.
    country = body.country.upper() if body.country else body.country
    city, city_geoname_id = body.city, body.city_geoname_id
    state, nickname, email, roles = body.state, body.nickname, body.email, body.roles
    # Authenticate current user
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Only IC, NC, or Prince can create users
    if not permissions.can_create_member(current_user):
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

    # Door-dedup: an email already on a live member means this person almost
    # certainly already has an account. Don't mint a duplicate — 409 with the
    # matched uid so the caller pivots to sponsor+register that account instead.
    # The client resolves name/vekn from its local member projection (which
    # carries every user), so only the uid is needed on the wire.
    if email:
        existing = await get_user_by_contact_email(email)
        if existing:
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "A member with this email already exists",
                    "code": "user.email_exists",
                    "params": {"uid": existing.uid},
                },
            )

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
        if not permissions.can_change_role(current_user, user, role):
            raise HTTPException(
                status_code=403,
                detail=f"You don't have permission to assign the {role.value} role",
            )

    bd = await db_save_user(user)

    # Send invite email if provided
    if email:
        try:
            await send_invite_email(email.lower(), user.uid, user.name)
            logger.info(f"Invite email sent to {email} for user {user.uid}")
        except Exception as e:
            logger.error(f"Failed to send invite email to {email}: {e}")
            # Don't fail the request, user is already created

    # Push new member to VEKN (fire-and-forget, batch_push catches failures)
    import asyncio

    from ..vekn_push import push_member_background

    asyncio.create_task(push_member_background(user))

    # Broadcast to SSE clients
    broadcast_precomputed(bd)

    return Response(
        content=encoder.encode(user),
        media_type="application/json",
        status_code=201,
    )


@router.put("/{uid}")
async def update_user(
    uid: str, body: UpdateUserRequest, current_user: OptionalUser = None
) -> Response:
    """Update an existing user."""
    name = body.name
    # Normalize country casing: storage + the same-country overlay match
    # (broadcast.py) compare exact, so a raw lower-case payload would corrupt it.
    country = body.country.upper() if body.country else body.country
    city, city_geoname_id = body.city, body.city_geoname_id
    state, nickname, roles = body.state, body.nickname, body.roles
    # Authenticate current user
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Fetch existing user
    user = await get_user_by_uid(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Two independent gates over one endpoint: profile fields take edit
    # authority, roles take the appointment matrix. A Rulemonger or PTC holds
    # the second without the first, so a roles-only request must not be turned
    # away here — but any profile field they send still is.
    edits_profile = any(
        field is not None
        for field in (name, country, city, city_geoname_id, state, nickname)
    )
    if not permissions.can_edit_user(current_user, user) and (
        edits_profile or roles is None
    ):
        raise HTTPException(
            status_code=403, detail="You don't have permission to edit this user"
        )

    old_roles = set(user.roles)
    old_country = user.country

    # Country scopes an official's FULL-data overlay, so changing an official's
    # country takes the authority that could change their official role. Gated on
    # the target's current roles (what they are), not any roles in this request.
    if (
        country is not None
        and country != old_country
        and not permissions.can_change_country(current_user, user)
    ):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to change this official's country",
        )

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
            if not permissions.can_change_role(current_user, user, role):
                raise HTTPException(
                    status_code=403,
                    detail=f"You don't have permission to change the {role.value} role",
                )

        # Ensure target has VEKN ID if any roles are being set
        if validated_roles and not user.vekn_id:
            raise HTTPException(
                status_code=400,
                detail="User must have a VEKN ID to be assigned roles",
            )

        local_mods.add("roles")

    # Update fields - only if at least one field is being updated
    if (
        name is not None
        or country is not None
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
        # nickname is in the legacy merge's ARCHON_USER_FIELDS, so an untracked
        # official-set nickname is reverted at the next nightly merge (the twin
        # PATCH /auth/me tracks it for the same reason).
        if nickname is not None:
            local_mods.add("nickname")

        user = msgspec.structs.replace(
            user,
            modified=datetime.now(UTC),
            name=name if name is not None else user.name,
            country=country if country is not None else user.country,
            city=city if city is not None else user.city,
            city_geoname_id=city_geoname_id
            if city_geoname_id is not None
            else user.city_geoname_id,
            state=state if state is not None else user.state,
            nickname=nickname if nickname is not None else user.nickname,
            roles=validated_roles if validated_roles is not None else user.roles,
            local_modifications=local_mods,
        )

    # Save to database
    bd = await db_save_user(user)

    # Resync when the user's access-affecting entitlement changes: the overlay
    # roles they hold (NC/Prince/IC), or — for an NC/Prince — their country,
    # which scopes their FULL-level overlay (IC sees full everywhere, so an IC
    # country change is overlay-neutral). _viewer_level and the access_levels
    # projections branch solely on these; other roles (PT/Judge/...) change no
    # projection, so resyncing on them just empties caches for ~10s for nothing.
    # Offline clients self-heal via the access-version fingerprint at connect;
    # this is the online nudge.
    new_roles = set(user.roles)
    access_roles = {Role.NC, Role.PRINCE, Role.IC}
    roles_access_changed = (old_roles & access_roles) != (new_roles & access_roles)
    country_overlay_changed = (
        country is not None
        and country != old_country
        and bool(old_roles & {Role.NC, Role.PRINCE})
    )
    if roles_access_changed or country_overlay_changed:
        await broadcast_resync(user.uid)
    if new_roles != old_roles:
        # Update Discord Linked Roles metadata (any role change, access-affecting or not)
        import asyncio

        from ..roles_hook import sync_user_discord_roles

        asyncio.create_task(sync_user_discord_roles(user.uid))

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

    # Update user's avatar_path with a versioned URL: a re-upload yields a new
    # URL, so SSE propagates the change and every client refetches at once,
    # while each version stays long-cacheable (see get_avatar cache headers).
    user = await get_user_by_uid(uid)
    if user:
        now = datetime.now(UTC)
        version = int(now.timestamp() * 1000)
        updated_user = msgspec.structs.replace(
            user,
            modified=now,
            avatar_path=f"/api/users/{uid}/avatar?v={version}",
        )
        bd = await db_save_user(updated_user)

        # Broadcast user update via SSE
        broadcast_precomputed(bd)

    return Response(
        content=b'{"success": true}',
        media_type="application/json",
    )


@router.get("/{uid}/avatar")
async def get_avatar(uid: str, request: Request) -> Response:
    """Get user avatar image.

    A versioned (?v=) URL is immutable content, so it can be cached for a year;
    a legacy unversioned request gets a short TTL and revalidates hourly.
    """
    result = await db_get_avatar(uid)
    if not result:
        raise HTTPException(status_code=404, detail="Avatar not found")

    data, content_type = result
    cache = (
        "public, max-age=31536000, immutable"
        if request.query_params.get("v")
        else "public, max-age=3600"
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": cache, "Content-Length": str(len(data))},
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
        bd = await db_save_user(updated_user)

        # Broadcast user update via SSE
        broadcast_precomputed(bd)

    return Response(
        content=b'{"success": true}',
        media_type="application/json",
    )


class LinkModerationRequest(BaseModel):
    url: str  # link URL to moderate
    action: str  # "hide" | "promote_national" | "promote_global" | "clear"


@router.patch("/{user_uid}/community-link-moderation")
async def moderate_community_link(
    user_uid: str,
    request: LinkModerationRequest,
    current_user: CurrentUser,
) -> Response:
    """Moderate a community link on a target user.

    Hide/clear: IC anywhere, NC in the same country as the target.
    promote_national: same, but never delegated further down.
    promote_global: IC only.
    Self-moderation is allowed: officials pin their own links this way.
    """
    # Get target user
    target = await get_user_by_uid(user_uid)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    mod: LinkModeration | None
    match request.action:
        case "hide" | "clear":
            if not permissions.can_moderate_link(current_user, target):
                raise HTTPException(
                    status_code=403,
                    detail="Can only moderate links in your country",
                )
            mod = (
                LinkModeration(
                    status="hidden", by=current_user.uid, at=datetime.now(UTC)
                )
                if request.action == "hide"
                else None
            )
        case "promote_national":
            if not permissions.can_promote_link_national(current_user, target):
                raise HTTPException(
                    status_code=403,
                    detail="Only IC, or the country's NC, can promote nationally",
                )
            mod = LinkModeration(
                status="promoted",
                by=current_user.uid,
                at=datetime.now(UTC),
                scope="national",
            )
        case "promote_global":
            if not permissions.can_promote_link_global(current_user):
                raise HTTPException(
                    status_code=403, detail="Only IC can promote globally"
                )
            mod = LinkModeration(
                status="promoted",
                by=current_user.uid,
                at=datetime.now(UTC),
                scope="global",
            )
        case _:
            raise HTTPException(
                status_code=422,
                detail="Action must be 'hide', 'promote_national',"
                " 'promote_global', or 'clear'",
            )

    # Find and update the link
    updated_links = []
    found = False
    for link in target.community_links:
        if link.url == request.url:
            found = True
            updated_links.append(msgspec.structs.replace(link, moderation=mod))
        else:
            updated_links.append(link)

    if not found:
        raise HTTPException(status_code=404, detail="Link not found on target user")

    target.community_links = updated_links
    target.modified = datetime.now(UTC)
    bd = await db_save_user(target)
    broadcast_precomputed(bd)

    return Response(content=b'{"success": true}', media_type="application/json")


class DeceasedRequest(BaseModel):
    """JSON body for PATCH /api/users/{uid}/deceased."""

    deceased: bool


@router.patch("/{uid}/deceased")
async def set_deceased(
    uid: str, body: DeceasedRequest, current_user: CurrentUser
) -> Response:
    """Mark or clear a member's deceased status.

    IC anywhere, NC in the same country as the target (Prince excluded).
    Not a soft-delete: history and ratings are preserved. Reversible.
    """
    if current_user.uid == uid:
        raise HTTPException(
            status_code=403, detail="You cannot change your own deceased status"
        )

    target = await get_user_by_uid(uid)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if not permissions.can_mark_deceased(current_user, target.country):
        raise HTTPException(
            status_code=403,
            detail="Only IC, or the member's national coordinator, can change deceased status",
        )

    # Symmetric with delete: deceased is for VEKN members (real people); a
    # VEKN-less member is local junk, removed via delete instead. Block only
    # SETTING — clearing a legacy mis-mark stays allowed so it can't get stuck.
    if body.deceased and not target.vekn_id:
        raise HTTPException(
            status_code=400,
            detail="VEKN-less members cannot be marked deceased; delete them instead",
        )

    # Deceased is archon-local and must always win over VEKN, set or cleared —
    # so the field stays flagged local even on clear (append-only is intentional).
    local_mods = set(target.local_modifications)
    local_mods.add("deceased_at")
    target = msgspec.structs.replace(
        target,
        modified=datetime.now(UTC),
        deceased_at=datetime.now(UTC) if body.deceased else None,
        deceased_by_uid=current_user.uid if body.deceased else None,
        local_modifications=local_mods,
    )

    bd = await db_save_user(target)
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(target), media_type="application/json")


@router.delete("/{uid}")
async def delete_member(uid: str, current_user: CurrentUser) -> Response:
    """Soft-delete a VEKN-less member (IC only).

    Soft, never hard: historical tournament references must still resolve, so
    the row stays cached and is only filtered out of listings. The inverse of
    marking deceased — VEKN-bearing members are upstream-authoritative (the next
    VEKN sync would recreate a tombstoned one), so they're refused here and
    handled via deceased status instead.
    """
    if current_user.uid == uid:
        raise HTTPException(
            status_code=403, detail="You cannot delete your own account"
        )

    if not permissions.can_delete_member(current_user):
        raise HTTPException(status_code=403, detail="Only IC can delete members")

    target = await get_user_by_uid(uid)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.vekn_id:
        raise HTTPException(
            status_code=400,
            detail="VEKN members cannot be deleted; mark them deceased instead",
        )

    result = await soft_delete_user(uid)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    user, bd = result
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(user), media_type="application/json")
