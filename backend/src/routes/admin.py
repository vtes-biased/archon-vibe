"""Admin API routes."""

import logging

import msgspec
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..db import get_user_by_uid, merge_users
from ..middleware.auth import CurrentUser
from ..models import Role, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
encoder = msgspec.json.Encoder()

# Will be set by main.py
_sync_service = None


def set_sync_service(sync_service) -> None:
    """Set the sync service instance."""
    global _sync_service
    _sync_service = sync_service


def _can_manage_country(manager: User, target_country: str | None) -> bool:
    """Check if manager can manage users from target_country."""
    if Role.IC in manager.roles:
        return True
    if Role.NC in manager.roles or Role.PRINCE in manager.roles:
        return manager.country == target_country
    return False


class MergeRequest(BaseModel):
    """Request to merge two user accounts."""

    keep_uid: str
    delete_uid: str


@router.post("/sync-vekn")
async def trigger_vekn_sync(
    manager: CurrentUser,
) -> dict:
    """Manually trigger VEKN member synchronization. Requires IC role."""
    if Role.IC not in manager.roles:
        raise HTTPException(status_code=403, detail="Only IC can trigger sync")

    if not _sync_service:
        raise HTTPException(
            status_code=503, detail="VEKN sync service is not available"
        )

    try:
        logger.info("Manual VEKN sync triggered via admin endpoint")
        stats = await _sync_service.sync_all_members()
        return {"status": "success", "stats": stats}
    except Exception as e:
        logger.error(f"Error during manual VEKN sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}") from e


@router.post("/sync-vekn-tournaments")
async def trigger_vekn_tournament_sync(
    manager: CurrentUser,
) -> dict:
    """Manually trigger VEKN tournament synchronization. Requires IC role."""
    if Role.IC not in manager.roles:
        raise HTTPException(status_code=403, detail="Only IC can trigger sync")

    if not _sync_service:
        raise HTTPException(
            status_code=503, detail="VEKN sync service is not available"
        )

    try:
        from ..vekn_tournament_sync import sync_all_tournaments

        logger.info("Manual VEKN tournament sync triggered via admin endpoint")
        stats = await sync_all_tournaments(_sync_service.client)
        return {"status": "success", "stats": stats}
    except Exception as e:
        logger.error(f"Error during manual VEKN tournament sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}") from e


@router.post("/sync-twda-decks")
async def trigger_twda_deck_import(
    manager: CurrentUser,
) -> dict:
    """Manually trigger TWDA winner decklist import. Requires IC role."""
    if Role.IC not in manager.roles:
        raise HTTPException(status_code=403, detail="Only IC can trigger sync")

    try:
        from ..twda_import import import_twda_decks

        logger.info("Manual TWDA deck import triggered via admin endpoint")
        stats = await import_twda_decks()
        return {"status": "success", "stats": stats}
    except Exception as e:
        logger.error(f"Error during manual TWDA deck import: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"TWDA import failed: {str(e)}"
        ) from e


@router.post("/users/merge")
async def merge_user_accounts(
    request: MergeRequest,
    manager: CurrentUser,
) -> Response:
    """Merge two user accounts.

    Requires IC, or NC/Prince for same country (both users must be same country).
    Transfers auth methods, sanctions from delete_uid to keep_uid.
    """

    # Check manager has appropriate role
    if not (
        Role.IC in manager.roles
        or Role.NC in manager.roles
        or Role.PRINCE in manager.roles
    ):
        raise HTTPException(
            status_code=403, detail="Only IC, NC, or Prince can merge users"
        )

    # Get both users
    keep_user = await get_user_by_uid(request.keep_uid)
    delete_user = await get_user_by_uid(request.delete_uid)

    if not keep_user:
        raise HTTPException(status_code=404, detail="Keep user not found")
    if not delete_user:
        raise HTTPException(status_code=404, detail="Delete user not found")

    # Check manager can manage both users' countries
    if not _can_manage_country(manager, keep_user.country):
        raise HTTPException(
            status_code=403, detail="Cannot manage keep user from other country"
        )
    if not _can_manage_country(manager, delete_user.country):
        raise HTTPException(
            status_code=403, detail="Cannot manage delete user from other country"
        )

    # Perform merge
    merged = await merge_users(request.keep_uid, request.delete_uid)
    if not merged:
        raise HTTPException(status_code=500, detail="Failed to merge users")

    logger.info(
        f"Merged users {request.delete_uid} into {request.keep_uid} by {manager.uid}"
    )

    return Response(
        content=encoder.encode(
            {
                "user": msgspec.to_builtins(merged),
                "message": "Users merged successfully",
            }
        ),
        media_type="application/json",
    )
