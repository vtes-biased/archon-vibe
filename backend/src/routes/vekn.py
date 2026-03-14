"""VEKN ID management API endpoints."""

import logging
import os
from datetime import UTC, datetime

import msgspec
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..db import (
    allocate_next_vekn_id,
    get_auth_methods_for_user,
    get_user_by_uid,
    get_user_by_vekn_id,
    is_vekn_id_claimed,
    merge_users,
    set_user_resync_after,
    split_user_from_vekn,
    strip_vekn_from_user,
    update_user,
)
from ..models import Role, User
from .auth import create_access_token, create_refresh_token, verify_token

router = APIRouter(prefix="/vekn", tags=["vekn"])
encoder = msgspec.json.Encoder()
logger = logging.getLogger(__name__)

from ..broadcast import broadcast_precomputed, broadcast_resync


async def _get_current_user_from_token(authorization: str | None) -> User:
    """Extract and verify current user from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )

    token = authorization[7:]
    user_uid = verify_token(token, expected_type="access")

    user = await get_user_by_uid(user_uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


def _can_manage_country(manager: User, target_country: str | None) -> bool:
    """Check if manager can manage users from target_country.

    IC can manage any country.
    NC/Prince can only manage their own country.
    """
    if Role.IC in manager.roles:
        return True
    if Role.NC in manager.roles or Role.PRINCE in manager.roles:
        return manager.country == target_country
    return False


def _require_manager_for_user(manager: User, target: User) -> None:
    """Raise 403 if manager cannot manage target user."""
    if not _can_manage_country(manager, target.country):
        raise HTTPException(
            status_code=403, detail="Cannot manage users from other countries"
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
    authorization: str | None = Header(default=None),
) -> Response:
    """User claims an unclaimed VEKN ID.

    The VEKN ID must exist and not be claimed (no auth_methods).
    The current user must not already have a VEKN ID.
    On success, merges the VEKN user into the current user's account.
    """
    current_user = await _get_current_user_from_token(authorization)

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
    merged = await merge_users(vekn_user.uid, current_user.uid)
    if not merged:
        raise HTTPException(status_code=500, detail="Failed to merge accounts")

    # Trigger resync — user gained a vekn_id, data level changes
    await set_user_resync_after(merged.uid)
    logger.info(f"User claimed VEKN ID {request.vekn_id}: {merged.uid}")
    await broadcast_resync(merged.uid)

    # Issue new tokens for the VEKN user's uid (different from the old user)
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
    authorization: str | None = Header(default=None),
) -> Response:
    """User voluntarily abandons their VEKN ID.

    Splits the user: creates a new user with auth methods and personal data,
    orphans the old VEKN record. Returns new tokens for the new user.
    """
    current_user = await _get_current_user_from_token(authorization)

    if not current_user.vekn_id:
        raise HTTPException(
            status_code=400, detail="You don't have a VEKN ID to abandon"
        )

    new_user = await split_user_from_vekn(current_user.uid)
    if not new_user:
        raise HTTPException(status_code=500, detail="Failed to abandon VEKN ID")

    logger.info(
        f"User abandoned VEKN ID {current_user.vekn_id}: old={current_user.uid} new={new_user.uid}"
    )
    await set_user_resync_after(new_user.uid)
    await broadcast_resync(new_user.uid)

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
    authorization: str | None = Header(default=None),
) -> Response:
    """Sponsor a new VEKN member.

    Allocates a new sequential VEKN ID to the target user.
    Requires IC, or NC/Prince for same country.
    Target user must not already have a VEKN ID.
    """
    manager = await _get_current_user_from_token(authorization)

    # Check manager has appropriate role
    if not (
        Role.IC in manager.roles
        or Role.NC in manager.roles
        or Role.PRINCE in manager.roles
    ):
        raise HTTPException(
            status_code=403, detail="Only IC, NC, or Prince can sponsor new members"
        )

    # Get target user
    target = await get_user_by_uid(request.user_uid)
    if not target:
        raise HTTPException(status_code=404, detail="Target user not found")

    # Check manager can manage target's country
    _require_manager_for_user(manager, target)

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

    bd = await update_user(updated)
    broadcast_precomputed(bd)
    await set_user_resync_after(updated.uid)
    logger.info(
        f"Sponsored new VEKN member {new_vekn_id} for user {target.uid} by {manager.uid}"
    )
    await broadcast_resync(updated.uid)

    # Push new member to VEKN registry
    if os.getenv("VEKN_PUSH", "").lower() == "true":
        try:
            from ..vekn_api import VEKNAPIClient
            from ..vekn_push import push_member

            client = VEKNAPIClient()
            try:
                await push_member(client, updated)
            finally:
                await client.close()
        except Exception:
            logger.exception("Failed to push new member to VEKN")

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
    authorization: str | None = Header(default=None),
) -> Response:
    """Link a VEKN ID to a user account.

    If the VEKN ID is unclaimed, merges directly.
    If claimed by another user, displaces them first (strips their account).
    Requires IC, or NC/Prince for same country (both users must be same country).
    """
    manager = await _get_current_user_from_token(authorization)

    # Check manager has appropriate role
    if not (
        Role.IC in manager.roles
        or Role.NC in manager.roles
        or Role.PRINCE in manager.roles
    ):
        raise HTTPException(
            status_code=403, detail="Only IC, NC, or Prince can link VEKN IDs"
        )

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
        result = await strip_vekn_from_user(vekn_user.uid)
        if result:
            displaced_user, _stripped_vekn = result
            message = (
                f"Displaced from {vekn_user.name} and linked VEKN ID {request.vekn_id}"
            )
            logger.info(
                f"Displaced user {vekn_user.uid} from VEKN ID {request.vekn_id}"
            )

    # Merge: keep the VEKN user_uid, transfer auth from target
    merged = await merge_users(vekn_user.uid, target.uid)
    if not merged:
        raise HTTPException(status_code=500, detail="Failed to link accounts")

    logger.info(
        f"Linked VEKN ID {request.vekn_id} to user {merged.uid} by {manager.uid}"
    )

    # Trigger resync for affected users
    await set_user_resync_after(merged.uid)
    await broadcast_resync(merged.uid)
    if displaced_user:
        await set_user_resync_after(displaced_user.uid)
        await broadcast_resync(displaced_user.uid)

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
    authorization: str | None = Header(default=None),
) -> Response:
    """Force-abandon a user's VEKN ID.

    Requires IC, or NC/Prince for same country.
    Same effect as user abandoning themselves.
    """
    manager = await _get_current_user_from_token(authorization)

    # Check manager has appropriate role
    if not (
        Role.IC in manager.roles
        or Role.NC in manager.roles
        or Role.PRINCE in manager.roles
    ):
        raise HTTPException(
            status_code=403, detail="Only IC, NC, or Prince can force-abandon VEKN IDs"
        )

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

    new_user = await split_user_from_vekn(target.uid)
    if not new_user:
        raise HTTPException(status_code=500, detail="Failed to abandon VEKN ID")

    logger.info(
        f"Force-abandoned VEKN ID {target.vekn_id} for user {target.uid} by {manager.uid}"
    )
    await set_user_resync_after(new_user.uid)
    await broadcast_resync(new_user.uid)

    return Response(
        content=encoder.encode(
            {
                "message": f"VEKN ID {target.vekn_id} abandoned for {target.name}",
                "user": msgspec.to_builtins(new_user),
            }
        ),
        media_type="application/json",
    )
