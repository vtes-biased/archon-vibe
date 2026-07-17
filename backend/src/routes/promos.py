"""Promo catalog API endpoints (IC-only writes; reads sync via SSE)."""

import logging
from datetime import UTC, datetime
from uuid import uuid7

import msgspec
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel

from ..broadcast import broadcast_precomputed
from ..db import (
    count_promo_references,
    delete_promo_image,
    get_league_by_uid,
    get_promo_by_uid,
    get_promo_image,
    save_promo,
    upsert_promo_image,
)
from ..middleware.auth import OptionalUser
from ..models import Promo, PromoKind, Role, TournamentRank

router = APIRouter(prefix="/api/promos", tags=["promos"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()


class PromoCreate(BaseModel):
    name: str
    kind: PromoKind = PromoKind.CARD
    description: str = ""
    release_date: datetime | None = None
    active: bool = True
    allowed_ranks: list[TournamentRank] = []
    league_uids: list[str] = []


class PromoUpdate(BaseModel):
    # Catalog fields only: `holdings` is server-written (ledger recompute) and
    # `image_path` is set by the image upload endpoint.
    name: str | None = None
    kind: PromoKind | None = None
    description: str | None = None
    release_date: datetime | None = None
    active: bool | None = None
    allowed_ranks: list[TournamentRank] | None = None
    league_uids: list[str] | None = None


def _require_ic(user: OptionalUser) -> None:
    if not user:
        raise HTTPException(401, "Authentication required")
    if Role.IC not in user.roles:
        raise HTTPException(403, "Only IC can manage promos")


async def _validate_league_uids(league_uids: list[str]) -> None:
    for league_uid in league_uids:
        if not await get_league_by_uid(league_uid):
            raise HTTPException(400, f"League not found: {league_uid}")


@router.post("/")
async def create_promo(
    body: PromoCreate,
    user: OptionalUser = None,
) -> Response:
    """Create a new promo item. IC only."""
    _require_ic(user)
    await _validate_league_uids(body.league_uids)

    promo = Promo(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name=body.name,
        kind=body.kind,
        description=body.description,
        release_date=body.release_date,
        active=body.active,
        allowed_ranks=body.allowed_ranks,
        league_uids=body.league_uids,
    )
    bd = await save_promo(promo)
    broadcast_precomputed(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(promo)),
        media_type="application/json",
        status_code=201,
    )


@router.put("/{uid}")
async def update_promo(
    uid: str,
    body: PromoUpdate,
    user: OptionalUser = None,
) -> Response:
    """Update a promo's catalog fields. IC only."""
    _require_ic(user)
    promo = await get_promo_by_uid(uid)
    if not promo:
        raise HTTPException(404, "Promo not found")

    updates = body.model_dump(exclude_unset=True)
    if "league_uids" in updates and updates["league_uids"]:
        await _validate_league_uids(updates["league_uids"])
    for field, value in updates.items():
        setattr(promo, field, value)

    promo.modified = datetime.now(UTC)
    bd = await save_promo(promo)
    broadcast_precomputed(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(promo)),
        media_type="application/json",
    )


@router.delete("/{uid}")
async def delete_promo(
    uid: str,
    user: OptionalUser = None,
) -> Response:
    """Soft-delete an unreferenced promo. IC only.

    A referenced promo must be retired (active=false) instead: the universal
    soft-delete tombstone hard-deletes it client-side, which would dangle the
    historical distribution rows and raffle prizes pointing at it.
    """
    _require_ic(user)
    promo = await get_promo_by_uid(uid)
    if not promo:
        raise HTTPException(404, "Promo not found")
    if await count_promo_references(uid):
        raise HTTPException(
            409, "Promo is referenced by tournament reports — retire it instead"
        )

    promo.deleted_at = datetime.now(UTC)
    promo.modified = datetime.now(UTC)
    bd = await save_promo(promo)
    broadcast_precomputed(bd)
    return Response(status_code=204)


# Promo image: blob in the promo_images side table; the Promo object only
# carries a versioned image_path so a re-upload propagates via SSE while each
# version stays long-cacheable. Served UNAUTHENTICATED by design — the service
# worker deliberately never caches JWT-bearing responses, and these images must
# be cacheable for offline display (raffle winner, picker).
MAX_PROMO_IMAGE_SIZE = 1024 * 1024  # 1MB


@router.post("/{uid}/image")
async def upload_promo_image(
    uid: str,
    file: UploadFile,
    user: OptionalUser = None,
) -> Response:
    """Upload or replace a promo image. IC only. Max 1MB webp/png/jpeg."""
    _require_ic(user)
    promo = await get_promo_by_uid(uid)
    if not promo:
        raise HTTPException(404, "Promo not found")

    if file.content_type not in ("image/webp", "image/png", "image/jpeg"):
        raise HTTPException(400, "Image must be webp, png, or jpeg")

    data = await file.read()
    if len(data) > MAX_PROMO_IMAGE_SIZE:
        raise HTTPException(
            400, f"Image too large. Max size: {MAX_PROMO_IMAGE_SIZE // 1024}KB"
        )

    await upsert_promo_image(uid, data, file.content_type or "image/webp")

    now = datetime.now(UTC)
    version = int(now.timestamp() * 1000)  # cache-busting token baked into the URL
    promo.image_path = f"/api/promos/{uid}/image?v={version}"
    promo.modified = now
    bd = await save_promo(promo)
    broadcast_precomputed(bd)

    return Response(content=b'{"success": true}', media_type="application/json")


@router.get("/{uid}/image")
async def get_promo_image_endpoint(uid: str, request: Request) -> Response:
    """Serve a promo image. A versioned (?v=) URL is immutable, so it can be
    cached aggressively; an unversioned request gets a short TTL."""
    result = await get_promo_image(uid)
    if not result:
        raise HTTPException(404, "Promo image not found")

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


@router.delete("/{uid}/image")
async def delete_promo_image_endpoint(
    uid: str,
    user: OptionalUser = None,
) -> Response:
    """Delete a promo image. IC only."""
    _require_ic(user)
    promo = await get_promo_by_uid(uid)
    if not promo:
        raise HTTPException(404, "Promo not found")

    await delete_promo_image(uid)
    promo.image_path = None
    promo.modified = datetime.now(UTC)
    bd = await save_promo(promo)
    broadcast_precomputed(bd)
    return Response(status_code=204)
