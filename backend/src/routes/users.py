import logging
from datetime import UTC, datetime
from uuid import uuid7

import msgspec
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import community_links, permissions
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
from ..geonames import stored_country
from ..middleware.auth import CurrentUser, OptionalUser
from ..models import Role, User
from .auth import send_invite_email

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger(__name__)
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
    """Auto-allocates a VEKN ID. If email is provided, sends an invite email so
    the new member can log in."""
    name = body.name
    country = stored_country(body.country)
    if body.country and country is None:
        raise HTTPException(status_code=422, detail=f"Invalid country: {body.country}")
    city, city_geoname_id = body.city, body.city_geoname_id
    state, nickname, email, roles = body.state, body.nickname, body.email, body.roles
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not permissions.can_sponsor_member(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only IC, NC, or Prince can create users",
        )

    validated_roles: list[Role] = []
    if roles is not None:
        for role_str in roles:
            if not role_str:
                continue
            try:
                validated_roles.append(Role(role_str))
            except ValueError as err:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid role: {role_str}. Valid roles: {[r.value for r in Role]}",
                ) from err

    # Door-dedup: an existing email match 409s with the matched uid instead of
    # minting a duplicate, so the caller pivots to sponsor+register that account.
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

    for role in validated_roles:
        if not permissions.can_change_role(current_user, user, role):
            raise HTTPException(
                status_code=403,
                detail=f"You don't have permission to assign the {role.value} role",
            )

    bd = await db_save_user(user)

    if email:
        try:
            await send_invite_email(email.lower(), user.uid, user.name)
            logger.info(f"Invite email sent to {email} for user {user.uid}")
        except Exception as e:
            logger.error(f"Failed to send invite email to {email}: {e}")
            # Don't fail the request, user is already created

    # Fire-and-forget; batch_push catches failures.
    import asyncio

    from ..vekn_push import push_member_background

    asyncio.create_task(push_member_background(user))

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
    name = body.name
    country = stored_country(body.country)
    if body.country and country is None:
        raise HTTPException(status_code=422, detail=f"Invalid country: {body.country}")
    city, city_geoname_id = body.city, body.city_geoname_id
    state, nickname, roles = body.state, body.nickname, body.roles
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    user = await get_user_by_uid(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Profile fields and roles are gated separately: a Rulemonger/PTC-only roles
    # request must pass even without edit authority, but any profile field turns it away.
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

    # Changing country moves an official's FULL-data overlay scope, so it needs the
    # authority that could change their role — gated on the target's CURRENT roles.
    if (
        country is not None
        and country != old_country
        and not permissions.can_change_country(current_user, user)
    ):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to change this official's country",
        )

    local_mods = set(user.local_modifications)

    validated_roles: list[Role] | None = None
    if roles is not None:
        validated_roles = []
        # An empty string in the list signals "clear all roles".
        for role_str in roles:
            if not role_str:
                continue
            try:
                validated_roles.append(Role(role_str))
            except ValueError as err:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid role: {role_str}. Valid roles: {[r.value for r in Role]}",
                ) from err

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

        if validated_roles and not user.vekn_id:
            raise HTTPException(
                status_code=400,
                detail="User must have a VEKN ID to be assigned roles",
            )

        local_mods.add("roles")

    if (
        name is not None
        or country is not None
        or city is not None
        or city_geoname_id is not None
        or state is not None
        or nickname is not None
        or validated_roles is not None
    ):
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
        # nickname is in the legacy merge's ARCHON_USER_FIELDS; untracked, it
        # reverts at the next nightly merge (mirrors PATCH /auth/me).
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

    bd = await db_save_user(user)

    # Only NC/IC role changes or an NC's country change move the access-version
    # fingerprint — must stay in lockstep with db._OVERLAY_ROLES and broadcast.entitled_level.
    new_roles = set(user.roles)
    access_roles = {Role.NC, Role.IC}
    roles_access_changed = (old_roles & access_roles) != (new_roles & access_roles)
    country_overlay_changed = (
        country is not None and country != old_country and Role.NC in old_roles
    )
    if roles_access_changed or country_overlay_changed:
        await broadcast_resync(user.uid)
    if new_roles != old_roles:
        # Any role delta, not just access-affecting ones.
        import asyncio

        from ..roles_hook import sync_user_discord_roles

        asyncio.create_task(sync_user_discord_roles(user.uid))

    broadcast_precomputed(bd)

    return Response(
        content=encoder.encode(user),
        media_type="application/json",
    )


MAX_AVATAR_SIZE = 1024 * 1024


@router.post("/{uid}/avatar")
async def upload_avatar(
    uid: str,
    file: UploadFile,
    current_user: OptionalUser = None,
) -> Response:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if current_user.uid != uid:
        raise HTTPException(status_code=403, detail="Can only upload your own avatar")

    if file.content_type not in ("image/webp", "image/png", "image/jpeg"):
        raise HTTPException(
            status_code=400,
            detail="Avatar must be webp, png, or jpeg",
        )

    data = await file.read()
    if len(data) > MAX_AVATAR_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Avatar too large. Max size: {MAX_AVATAR_SIZE // 1024}KB",
        )

    await db_upsert_avatar(uid, data, file.content_type or "image/webp")

    # Versioned avatar_path: a re-upload gets a new URL so SSE propagates the change
    # and clients refetch, while each version stays long-cacheable (see get_avatar).
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

        broadcast_precomputed(bd)

    return Response(
        content=b'{"success": true}',
        media_type="application/json",
    )


@router.get("/{uid}/avatar")
async def get_avatar(uid: str, request: Request) -> Response:
    """A versioned (?v=) URL is immutable content, cached for a year; a legacy
    unversioned request gets a short TTL and revalidates hourly."""
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
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if current_user.uid != uid:
        raise HTTPException(status_code=403, detail="Can only delete your own avatar")

    deleted = await db_delete_avatar(uid)
    if not deleted:
        raise HTTPException(status_code=404, detail="Avatar not found")

    user = await get_user_by_uid(uid)
    if user:
        updated_user = msgspec.structs.replace(
            user,
            modified=datetime.now(UTC),
            avatar_path=None,
        )
        bd = await db_save_user(updated_user)

        broadcast_precomputed(bd)

    return Response(
        content=b'{"success": true}',
        media_type="application/json",
    )


class LinkEditRequest(BaseModel):
    """Curate a link on another member's profile, addressed by its URL.

    The URL is the identity moderation is keyed on and is never rewritten.
    """

    url: str
    type: str | None = None
    label: str | None = None
    languages: list[str] | None = None
    country: str | None = None
    state: str | None = None


@router.patch("/{user_uid}/community-link-moderation")
async def edit_community_link(
    user_uid: str,
    request: LinkEditRequest,
    current_user: CurrentUser,
) -> Response:
    """Curate a link on another member's profile."""
    target = await get_user_by_uid(user_uid)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    prior = next((el for el in target.community_links if el.url == request.url), None)
    if prior is None:
        raise HTTPException(status_code=404, detail="Link not found on target user")

    # A move needs authority over where it lands as well as where it sits.
    if not permissions.can_moderate_link(current_user, prior.country or target.country):
        raise HTTPException(
            status_code=403, detail="Can only moderate links in your country"
        )
    country = community_links.validated_country(
        request.country, prior.country or target.country
    )
    if country != prior.country and not permissions.can_moderate_link(
        current_user, country
    ):
        raise HTTPException(
            status_code=403, detail="Can only move a link into your own country"
        )

    link_type = (
        community_links.validated_type(request.type) if request.type else prior.type
    )
    languages = community_links.validated_languages(
        prior.languages if request.languages is None else request.languages,
        link_type,
        prior,
    )
    mod = prior.moderation
    if request.state is not None:
        mod = community_links.moderation_for(current_user, request.state, country, mod)

    edited = msgspec.structs.replace(
        prior,
        type=link_type,
        label=prior.label if request.label is None else request.label,
        languages=languages,
        country=country,
        moderation=mod,
    )
    target.community_links = [
        edited if link.url == request.url else link for link in target.community_links
    ]
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
    """Mark or clear a member's deceased status. Not a soft-delete: history
    and ratings are preserved. Reversible."""
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

    # Block only SETTING on a VEKN-less member (delete instead) — clearing a
    # legacy mis-mark stays allowed so it can't get stuck.
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
    """Soft-delete a VEKN-less member (IC only). A VEKN-bearing member is
    refused: the next VEKN sync would just recreate a tombstoned one."""
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
