"""There is deliberately no unauthenticated rotate endpoint: an endpoint-only
rewrite would let a leaked endpoint hijack a user's notifications. Dead rows
are pruned lazily on 404/410 at send time, in push_service.
"""

import logging

import msgspec
from litestar import Request, Router, get, post
from litestar.exceptions import HTTPException

from .. import db, push_service
from ..middleware.auth import get_current_user

logger = logging.getLogger(__name__)


class PushKeys(msgspec.Struct):
    p256dh: str
    auth: str


class SubscribeRequest(msgspec.Struct):
    endpoint: str
    keys: PushKeys
    locale: str = "en"  # browser UI language; payload bodies render per-subscription


class UnsubscribeRequest(msgspec.Struct):
    endpoint: str


@get("/vapid-key")
async def get_vapid_key() -> dict:
    """The applicationServerKey the browser needs to subscribe (public, per-env)."""
    key = push_service.vapid_public_key()
    if not key:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"key": key}


@post("/subscribe", status_code=204)
async def subscribe(data: SubscribeRequest, request: Request) -> None:
    user = await get_current_user(request)
    if not push_service.is_configured():
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    await db.save_push_subscription(
        endpoint=data.endpoint,
        user_uid=user.uid,
        p256dh=data.keys.p256dh,
        auth=data.keys.auth,
        ua=request.headers.get("user-agent"),
        locale=data.locale,
    )


@post("/unsubscribe", status_code=204)
async def unsubscribe(data: UnsubscribeRequest, request: Request) -> None:
    user = await get_current_user(request)
    await db.delete_push_subscription(data.endpoint, user_uid=user.uid)


router = Router(
    "/api/push",
    route_handlers=[get_vapid_key, subscribe, unsubscribe],
)
