"""VEKN ID management API endpoints."""

import asyncio
import logging
from datetime import UTC, datetime

import msgspec
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .. import permissions
from ..accounts import (
    detach_user_from_vekn,
    merge_users,
    user_has_active_suspension,
)
from ..broadcast import broadcast_precomputed, broadcast_resync
from ..db import (
    allocate_next_vekn_id,
    get_auth_methods_for_user,
    get_user_by_uid,
    get_user_by_vekn_id,
    is_vekn_id_claimed,
    save_user,
)
from ..middleware.auth import CurrentUser
from ..models import User
from ..roles_hook import sync_user_discord_roles
from .auth import create_access_token, create_refresh_token

router = APIRouter(prefix="/vekn", tags=["vekn"])
encoder = msgspec.json.Encoder()
logger = logging.getLogger(__name__)


def _require_manager_for_user(manager: User, target: User) -> None:
    """Raise 403 if manager cannot manage target's VEKN ID."""
    if not permissions.can_manage_vekn(manager, target):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to manage this user's VEKN ID",
        )


class ClaimRequest(BaseModel):
    """Request to claim an unclaimed VEKN ID."""

    vekn_id: str


class LinkRequest(BaseModel):
    """Request to link a VEKN ID to a user (may displace current holder)."""

    vekn_id: str
    user_uid: str


class SponsorRequest(BaseModel):
    """Request to sponsor a new VEKN member."""

    user_uid: str


class ForceAbandonRequest(BaseModel):
    """Request to force-abandon a user's VEKN ID."""

    user_uid: str


@router.post("/claim")
async def claim_vekn_id(
    request: ClaimRequest,
    current_user: CurrentUser,
) -> Response:
    """User claims an unclaimed VEKN ID.

    The VEKN ID must exist and not be claimed (no auth_methods).
    The current user must not already have a VEKN ID.
    On success, merges the VEKN user into the current user's account.
    """

    # Check current user doesn't already have a VEKN ID
    if current_user.vekn_id:
        raise HTTPException(status_code=400, detail="You already have a VEKN ID")

    # Find the VEKN user
    vekn_user = await get_user_by_vekn_id(request.vekn_id)
    if not vekn_user:
        raise HTTPException(status_code=404, detail="VEKN ID not found")

    # Check if it's claimed (has auth methods)
    if await is_vekn_id_claimed(request.vekn_id):
        raise HTTPException(
            status_code=400, detail="This VEKN ID is already claimed by another user"
        )

    # Merge: keep the VEKN user_uid (stable reference), transfer auth from current
    result = await merge_users(vekn_user.uid, current_user.uid)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to merge accounts")
    merged, merge_bds = result

    # Push the merge to other clients' caches live, then resync the
    # owner (their data level changed — they gained a vekn_id).
    for bd in merge_bds:
        broadcast_precomputed(bd)
    logger.info(f"User claimed VEKN ID {request.vekn_id}: {merged.uid}")
    await broadcast_resync(merged.uid)

    # Update Discord Linked Roles (vekn_id changes org level)
    asyncio.create_task(sync_user_discord_roles(merged.uid))

    # Issue new tokens for the VEKN user's uid (different from the old user).
    # Consumed by the SPA (session rotation) AND the Discord bot, which fires
    # one follow-up tournament action with this access_token after a bot-side
    # claim tombstones its stored OAuth identity (bot commands/player.py).
    access_token, expires_in = create_access_token(merged.uid)
    refresh_token = create_refresh_token(merged.uid)

    return Response(
        content=encoder.encode(
            {
                "user": msgspec.to_builtins(merged),
                "message": f"Successfully claimed VEKN ID {request.vekn_id}",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
            }
        ),
        media_type="application/json",
    )


@router.post("/abandon")
async def abandon_vekn_id(
    current_user: CurrentUser,
) -> Response:
    """User voluntarily abandons their VEKN ID.

    Splits the user: creates a new user with auth methods and personal data,
    orphans the old VEKN record. Returns new tokens for the new user.
    """

    if not current_user.vekn_id:
        raise HTTPException(
            status_code=400, detail="You don't have a VEKN ID to abandon"
        )

    # You can't abandon your way out of a suspension — the sanction stays with
    # the VEKN record, so block the self-service detach while one is active.
    if await user_has_active_suspension(current_user.uid):
        raise HTTPException(
            status_code=403,
            detail="Cannot abandon a VEKN ID while you hold an active suspension or probation",
        )

    result = await detach_user_from_vekn(current_user.uid)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to abandon VEKN ID")
    new_user, _vekn_record, detach_bds = result

    logger.info(
        f"User abandoned VEKN ID {current_user.vekn_id}: old={current_user.uid} new={new_user.uid}"
    )
    # Push the orphaned record's nulled PII to other clients' caches live.
    for bd in detach_bds:
        broadcast_precomputed(bd)
    await broadcast_resync(new_user.uid)

    # Update Discord Linked Roles (lost vekn_id)
    asyncio.create_task(sync_user_discord_roles(new_user.uid))

    # Issue new tokens for the new user
    access_token, expires_in = create_access_token(new_user.uid)
    refresh_token = create_refresh_token(new_user.uid)

    return Response(
        content=encoder.encode(
            {
                "message": "VEKN ID abandoned successfully",
                "user": msgspec.to_builtins(new_user),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
            }
        ),
        media_type="application/json",
    )


@router.post("/sponsor")
async def sponsor_new_member(
    request: SponsorRequest,
    manager: CurrentUser,
) -> Response:
    """Sponsor a new VEKN member.

    Allocates a new sequential VEKN ID to the target user.
    Requires an official role (IC, NC, or Prince) — any country: a visiting
    official can sponsor newcomers abroad (they won't be able to edit that
    member's profile afterwards; profile edits stay country-scoped).
    Target user must not already have a VEKN ID.
    """

    # Check manager has appropriate role
    if not permissions.can_sponsor_member(manager):
        raise HTTPException(
            status_code=403, detail="Only IC, NC, or Prince can sponsor new members"
        )

    # Get target user
    target = await get_user_by_uid(request.user_uid)
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    # Check target doesn't already have a VEKN ID
    if target.vekn_id:
        raise HTTPException(status_code=400, detail="User already has a VEKN ID")

    # Allocate new VEKN ID
    new_vekn_id = await allocate_next_vekn_id()
    now = datetime.now(UTC)

    # Update target user
    updated = msgspec.structs.replace(
        target,
        modified=now,
        vekn_id=new_vekn_id,
        coopted_by=manager.uid,
        coopted_at=now,
        vekn_synced=False,
        vekn_synced_at=None,
    )

    bd = await save_user(updated)
    broadcast_precomputed(bd)
    logger.info(
        f"Sponsored new VEKN member {new_vekn_id} for user {target.uid} by {manager.uid}"
    )
    await broadcast_resync(updated.uid)

    # Update Discord Linked Roles (gained vekn_id)
    asyncio.create_task(sync_user_discord_roles(updated.uid))

    # Push new member to VEKN registry. Background task — the response must not
    # wait on vekn.net (30-120s timeouts when it is down); batch_push retries.
    from ..vekn_push import push_member_background

    asyncio.create_task(push_member_background(updated))

    return Response(
        content=encoder.encode(
            {
                "user": msgspec.to_builtins(updated),
                "vekn_id": new_vekn_id,
                "message": f"Sponsored user with VEKN ID {new_vekn_id}",
            }
        ),
        media_type="application/json",
    )


@router.post("/link")
async def link_vekn_to_user(
    request: LinkRequest,
    manager: CurrentUser,
) -> Response:
    """Link a VEKN ID to a user account.

    If the VEKN ID is unclaimed, merges directly.
    If claimed by another user, displaces them first (strips their account).
    Requires IC, or NC/Prince for same country (both users must be same country).
    """

    # Get target user
    target = await get_user_by_uid(request.user_uid)
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    # Check manager can manage target's country
    _require_manager_for_user(manager, target)

    # Check target doesn't already have a different VEKN ID
    if target.vekn_id and target.vekn_id != request.vekn_id:
        raise HTTPException(
            status_code=400, detail="User already has a different VEKN ID"
        )

    # Find the VEKN user
    vekn_user = await get_user_by_vekn_id(request.vekn_id)
    if not vekn_user:
        raise HTTPException(status_code=404, detail="VEKN ID not found")

    # Check manager can manage VEKN user's country too
    _require_manager_for_user(manager, vekn_user)

    displaced_user = None
    message = f"Linked VEKN ID {request.vekn_id}"

    # Check if VEKN ID is currently claimed
    if await is_vekn_id_claimed(request.vekn_id):
        # Need to displace the current holder
        result = await detach_user_from_vekn(vekn_user.uid)
        if result:
            displaced_user, _vekn_record, displace_bds = result
            # The displaced personal account + the freed record (the merge below
            # repopulates the latter) propagate to other caches live.
            for bd in displace_bds:
                broadcast_precomputed(bd)
            message = (
                f"Displaced from {vekn_user.name} and linked VEKN ID {request.vekn_id}"
            )
            logger.info(
                f"Displaced user {vekn_user.uid} from VEKN ID {request.vekn_id}"
            )

    # Merge: keep the VEKN user_uid, transfer auth from target
    result = await merge_users(vekn_user.uid, target.uid)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to link accounts")
    merged, merge_bds = result
    for bd in merge_bds:
        broadcast_precomputed(bd)

    logger.info(
        f"Linked VEKN ID {request.vekn_id} to user {merged.uid} by {manager.uid}"
    )

    # Trigger resync for affected users
    await broadcast_resync(merged.uid)
    asyncio.create_task(sync_user_discord_roles(merged.uid))
    if displaced_user:
        await broadcast_resync(displaced_user.uid)
        asyncio.create_task(sync_user_discord_roles(displaced_user.uid))

    response_data = {
        "user": msgspec.to_builtins(merged),
        "message": message,
    }
    if displaced_user:
        response_data["displaced_user"] = msgspec.to_builtins(displaced_user)

    return Response(
        content=encoder.encode(response_data),
        media_type="application/json",
    )


@router.post("/force-abandon")
async def force_abandon_vekn_id(
    request: ForceAbandonRequest,
    manager: CurrentUser,
) -> Response:
    """Force-abandon a user's VEKN ID.

    Requires IC, or NC/Prince for same country.
    Same effect as user abandoning themselves.
    """

    # Get target user
    target = await get_user_by_uid(request.user_uid)
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    # Check manager can manage target's country
    _require_manager_for_user(manager, target)

    if not target.vekn_id:
        raise HTTPException(
            status_code=400, detail="User doesn't have a VEKN ID to abandon"
        )

    # Don't split unclaimed users — nobody is behind this account,
    # so force-abandon would just create an empty orphan user.
    auth_methods = await get_auth_methods_for_user(target.uid)
    if not auth_methods:
        raise HTTPException(
            status_code=400,
            detail="This VEKN ID is not claimed by anyone — no need to abandon",
        )

    # Admin force-abandon is exempt from the active-suspension guard that blocks
    # self-service /abandon — officials act deliberately.
    result = await detach_user_from_vekn(target.uid)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to abandon VEKN ID")
    new_user, _vekn_record, detach_bds = result

    logger.info(
        f"Force-abandoned VEKN ID {target.vekn_id} for user {target.uid} by {manager.uid}"
    )
    # Push the orphaned record's nulled PII to other clients' caches live.
    for bd in detach_bds:
        broadcast_precomputed(bd)
    await broadcast_resync(new_user.uid)

    # Update Discord Linked Roles (lost vekn_id + roles)
    asyncio.create_task(sync_user_discord_roles(new_user.uid))

    return Response(
        content=encoder.encode(
            {
                "message": f"VEKN ID {target.vekn_id} abandoned for {target.name}",
                "user": msgspec.to_builtins(new_user),
            }
        ),
        media_type="application/json",
    )
