"""Admin API routes."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import msgspec
from litestar import Request, Response, Router, get, post
from litestar.exceptions import HTTPException

from .. import permissions
from ..accounts import merge_users
from ..broadcast import broadcast_precomputed
from ..db import get_user_by_uid, remap_promo_ledger_user
from ..middleware.auth import get_current_user
from ..promo_stock import schedule_recompute
from ..vekn_status import get_status

logger = logging.getLogger(__name__)

encoder = msgspec.json.Encoder()

# Recorded background runners injected by main.py.
_runners: dict[str, Callable[[], Awaitable[None]]] = {}
# In-flight admin-dispatched jobs, keyed by job name — keeps the task referenced
# (so it isn't GC'd) and lets a re-trigger see a run is already going.
_running_tasks: dict[str, asyncio.Task] = {}


def set_sync_runners(**runners: Callable[[], Awaitable[None]]) -> None:
    _runners.update(runners)


def _dispatch(job: str, make_coro: Callable[[], Awaitable[None]]) -> dict:
    """Awaiting inline would block the HTTP response until the reverse proxy
    times the request out mid-query; poll /admin/vekn-status for the outcome.
    """
    existing = _running_tasks.get(job)
    if existing and not existing.done():
        return {"status": "already_running"}
    _running_tasks[job] = asyncio.create_task(make_coro())
    return {"status": "started"}


class MergeRequest(msgspec.Struct):
    keep_uid: str
    delete_uid: str


@get("/vekn-status")
async def vekn_status(request: Request) -> dict:
    manager = await get_current_user(request)
    if not permissions.can_run_admin_sync(manager):
        raise HTTPException(status_code=403, detail="Only IC can view sync status")

    return {"jobs": get_status()}


@post("/sync-judges")
async def trigger_judge_sync(request: Request) -> dict:
    """Returns immediately; the outcome lands on the vekn-status panel as
    `judge_sync`.
    """
    manager = await get_current_user(request)
    if not permissions.can_run_admin_sync(manager):
        raise HTTPException(status_code=403, detail="Only IC can trigger sync")

    runner = _runners.get("judge_sync")
    if not runner:
        raise HTTPException(status_code=503, detail="Judge sync is not available")

    logger.info("Manual judge directory sync dispatched via admin endpoint")
    return _dispatch("judge_sync", runner)


@post("/users/merge")
async def merge_user_accounts(request: Request, data: MergeRequest) -> Response:
    manager = await get_current_user(request)
    if not permissions.can_merge_accounts(manager):
        raise HTTPException(status_code=403, detail="Only IC can merge users")

    keep_user = await get_user_by_uid(data.keep_uid)
    delete_user = await get_user_by_uid(data.delete_uid)

    if not keep_user:
        raise HTTPException(status_code=404, detail="Keep user not found")
    if not delete_user:
        raise HTTPException(status_code=404, detail="Delete user not found")

    # merge_users refuses to absorb a VEKN-bearing account; surface that as a
    # 400 rather than a generic 500.
    try:
        result = await merge_users(data.keep_uid, data.delete_uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    if not result:
        raise HTTPException(status_code=500, detail="Failed to merge users")
    merged, merge_bds = result
    for bd in merge_bds:
        broadcast_precomputed(bd)

    # The absorbed account's tombstone keeps stale promo_stock keys after the
    # recompute — moot, since tombstones are client-evicted.
    await remap_promo_ledger_user(data.delete_uid, data.keep_uid)
    schedule_recompute()

    logger.info(f"Merged users {data.delete_uid} into {data.keep_uid} by {manager.uid}")

    return Response(
        content=encoder.encode(
            {
                "user": msgspec.to_builtins(merged),
                "message": "Users merged successfully",
            }
        ),
        media_type="application/json",
    )


router = Router(
    "/admin",
    route_handlers=[
        vekn_status,
        trigger_judge_sync,
        merge_user_accounts,
    ],
)
