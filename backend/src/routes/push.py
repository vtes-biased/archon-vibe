"""Web Push subscription endpoints (#314).

The frontend fetches the per-env VAPID public key, then POSTs the browser's
PushSubscription (authenticated, so it's tied to the current user). Unsubscribe and the
lazy reconcile after ``pushsubscriptionchange`` both route through the authenticated
subscribe/unsubscribe pair — there is deliberately no unauthenticated rotate endpoint
(an endpoint-only rewrite would let a leaked endpoint hijack a user's notifications).
Dead rows are pruned lazily on 404/410 at send time (see push_service).
"""

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .. import db, push_service
from ..middleware.auth import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/push", tags=["push"])


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribeRequest(BaseModel):
    endpoint: str
    keys: PushKeys


class UnsubscribeRequest(BaseModel):
    endpoint: str


@router.get("/vapid-key")
async def get_vapid_key() -> dict:
    """The applicationServerKey the browser needs to subscribe (public, per-env)."""
    key = push_service.vapid_public_key()
    if not key:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"key": key}


@router.post("/subscribe", status_code=204)
async def subscribe(
    body: SubscribeRequest, request: Request, user: CurrentUser
) -> Response:
    """Register (or refresh) the current user's subscription for this browser."""
    if not push_service.is_configured():
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    await db.save_push_subscription(
        endpoint=body.endpoint,
        user_uid=user.uid,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        ua=request.headers.get("user-agent"),
    )
    return Response(status_code=204)


@router.post("/unsubscribe", status_code=204)
async def unsubscribe(body: UnsubscribeRequest, user: CurrentUser) -> Response:
    """Drop the current user's subscription for this browser (toggle off)."""
    await db.delete_push_subscription(body.endpoint, user_uid=user.uid)
    return Response(status_code=204)
