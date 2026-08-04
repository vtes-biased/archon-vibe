"""Admin API routes."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import msgspec
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .. import permissions
from ..accounts import merge_users
from ..broadcast import broadcast_precomputed
from ..db import get_user_by_uid, remap_promo_ledger_user
from ..middleware.auth import CurrentUser
from ..promo_stock import schedule_recompute

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
encoder = msgspec.json.Encoder()

# Will be set by main.py
_sync_service = None
# Recorded background runners injected by main.py (member_sync / tournament_sync).
_runners: dict[str, Callable[[], Awaitable[None]]] = {}
# In-flight admin-dispatched jobs, keyed by job name — keeps the task referenced
# (so it isn't GC'd) and lets a re-trigger see a run is already going.
_running_tasks: dict[str, asyncio.Task] = {}


def set_sync_service(sync_service) -> None:
    """Set the sync service instance."""
    global _sync_service
    _sync_service = sync_service


def set_sync_runners(**runners: Callable[[], Awaitable[None]]) -> None:
    """Register the recorded sync runners the admin endpoints dispatch."""
    _runners.update(runners)


def _dispatch(job: str, make_coro: Callable[[], Awaitable[None]]) -> dict:
    """Fire a job in the background and return immediately.

    The job is long-running (a full VEKN pull is minutes); awaiting it inline
    would block the HTTP response until the reverse proxy times the request out
    and cancels it mid-query. Instead we launch it as a task and let the caller
    poll /admin/vekn-status for the outcome.
    """
    existing = _running_tasks.get(job)
    if existing and not existing.done():
        return {"status": "already_running"}
    _running_tasks[job] = asyncio.create_task(make_coro())
    return {"status": "started"}


class MergeRequest(BaseModel):
    """Request to merge two user accounts."""

    keep_uid: str
    delete_uid: str


@router.post("/sync-vekn")
async def trigger_vekn_sync(
    manager: CurrentUser,
) -> dict:
    """Dispatch a VEKN member sync in the background. Requires IC role.

    Returns immediately ({"status": "started"} or "already_running"); the
    outcome lands in /admin/vekn-status under member_sync.
    """
    if not permissions.can_run_admin_sync(manager):
        raise HTTPException(status_code=403, detail="Only IC can trigger sync")

    runner = _runners.get("member_sync")
    if not runner:
        raise HTTPException(
            status_code=503, detail="VEKN sync service is not available"
        )

    logger.info("Manual VEKN member sync dispatched via admin endpoint")
    return _dispatch("member_sync", runner)


@router.post("/sync-vekn-tournaments")
async def trigger_vekn_tournament_sync(
    manager: CurrentUser,
) -> dict:
    """Dispatch a VEKN tournament sync in the background. Requires IC role.

    Returns immediately; the outcome lands in /admin/vekn-status under
    tournament_sync.
    """
    if not permissions.can_run_admin_sync(manager):
        raise HTTPException(status_code=403, detail="Only IC can trigger sync")

    runner = _runners.get("tournament_sync")
    if not runner:
        raise HTTPException(
            status_code=503, detail="VEKN sync service is not available"
        )

    logger.info("Manual VEKN tournament sync dispatched via admin endpoint")
    return _dispatch("tournament_sync", runner)


@router.get("/vekn-status")
async def vekn_status(
    manager: CurrentUser,
) -> dict:
    """Last success/error of VEKN sync & push jobs. Requires IC role.

    Lets admins spot a days-long vekn.net outage without grepping logs. State is
    in-process (resets on restart); keys: member_sync, tournament_sync, batch_push.
    """
    if not permissions.can_run_admin_sync(manager):
        raise HTTPException(status_code=403, detail="Only IC can view VEKN status")

    from ..vekn_status import get_status

    return {"jobs": get_status()}


async def _run_twda_import() -> None:
    """TWDA import wrapped for background dispatch (logs its own outcome)."""
    from ..twda_import import import_twda_decks

    try:
        logger.info("Starting TWDA deck import")
        stats = await import_twda_decks()
        logger.info(f"TWDA deck import: {stats}")
    except Exception as e:
        logger.error(f"Error during TWDA deck import: {e}", exc_info=True)


@router.post("/sync-twda-decks")
async def trigger_twda_deck_import(
    manager: CurrentUser,
) -> dict:
    """Dispatch a TWDA winner-decklist import in the background. Requires IC role.

    Returns immediately; the outcome is logged (TWDA has no vekn-status panel
    entry).
    """
    if not permissions.can_run_admin_sync(manager):
        raise HTTPException(status_code=403, detail="Only IC can trigger sync")

    logger.info("Manual TWDA deck import dispatched via admin endpoint")
    return _dispatch("twda", _run_twda_import)


@router.post("/users/merge")
async def merge_user_accounts(
    request: MergeRequest,
    manager: CurrentUser,
) -> Response:
    """Merge two user accounts.

    IC only: the merge unions both accounts' roles without consulting the
    appointment matrix. Transfers auth methods, sanctions from delete_uid to
    keep_uid.
    """

    if not permissions.can_merge_accounts(manager):
        raise HTTPException(status_code=403, detail="Only IC can merge users")

    # Get both users
    keep_user = await get_user_by_uid(request.keep_uid)
    delete_user = await get_user_by_uid(request.delete_uid)

    if not keep_user:
        raise HTTPException(status_code=404, detail="Keep user not found")
    if not delete_user:
        raise HTTPException(status_code=404, detail="Delete user not found")

    # Perform merge. merge_users refuses to absorb a VEKN-bearing account
    # (invariant); surface that as a 400 rather than a generic 500.
    try:
        result = await merge_users(request.keep_uid, request.delete_uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    if not result:
        raise HTTPException(status_code=500, detail="Failed to merge users")
    merged, merge_bds = result
    # Propagate the merge to other clients' caches live.
    for bd in merge_bds:
        broadcast_precomputed(bd)

    # Promo ledger rows point at the survivor; the full recompute then rebuilds
    # the survivor's stock aggregates (the absorbed account's tombstone keeps
    # its stale keys, moot — tombstones are client-evicted).
    await remap_promo_ledger_user(request.delete_uid, request.keep_uid)
    schedule_recompute()

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
