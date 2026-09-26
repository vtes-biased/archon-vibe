"""Promo catalog API endpoints (IC-only writes; reads sync via SSE)."""

import logging
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import uuid7

import msgspec
from litestar import Request, Response, Router, delete, get, post, put
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.exceptions import HTTPException
from litestar.params import Body, FromPath

from .. import permissions
from ..broadcast import broadcast_precomputed
from ..db import (
    count_promo_references,
    delete_promo_image,
    get_all_promos,
    get_league_by_uid,
    get_promo_by_uid,
    get_promo_image,
    get_promo_ledger_entries,
    get_user_by_uid,
    insert_promo_ledger_entries,
    save_promo,
    upsert_promo_image,
)
from ..middleware.auth import get_optional_user
from ..models import (
    Promo,
    PromoKind,
    PromoLedgerEntry,
    PromoLedgerKind,
    TournamentRank,
    User,
)
from ..promo_stock import schedule_recompute

logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()


class PromoCreate(msgspec.Struct):
    name: str
    kind: PromoKind = PromoKind.CARD
    description: str = ""
    release_date: date | None = None
    active: bool = True
    allowed_ranks: list[TournamentRank] = []
    league_uids: list[str] = []


class PromoUpdate(msgspec.Struct):
    # Catalog fields only: `holdings` is server-written (ledger recompute) and
    # `image_path` is set by the image upload endpoint.
    name: str | msgspec.UnsetType = msgspec.UNSET
    kind: PromoKind | msgspec.UnsetType = msgspec.UNSET
    description: str | msgspec.UnsetType = msgspec.UNSET
    release_date: date | None | msgspec.UnsetType = msgspec.UNSET
    active: bool | msgspec.UnsetType = msgspec.UNSET
    allowed_ranks: list[TournamentRank] | msgspec.UnsetType = msgspec.UNSET
    league_uids: list[str] | msgspec.UnsetType = msgspec.UNSET


def _require_ic(user: User | None) -> None:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not permissions.can_manage_promos(user):
        raise HTTPException(status_code=403, detail="Only IC can manage promos")


async def _validate_league_uids(league_uids: list[str]) -> None:
    for league_uid in league_uids:
        if not await get_league_by_uid(league_uid):
            raise HTTPException(
                status_code=400, detail=f"League not found: {league_uid}"
            )


@post("/")
async def create_promo(request: Request, data: PromoCreate) -> Response:
    """Create a new promo item. IC only."""
    user = await get_optional_user(request)
    _require_ic(user)
    await _validate_league_uids(data.league_uids)

    promo = Promo(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name=data.name,
        kind=data.kind,
        description=data.description,
        release_date=datetime(d.year, d.month, d.day)
        if (d := data.release_date)
        else None,
        active=data.active,
        allowed_ranks=data.allowed_ranks,
        league_uids=data.league_uids,
    )
    bd = await save_promo(promo)
    broadcast_precomputed(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(promo)),
        media_type="application/json",
    )


@put("/{uid:str}")
async def update_promo(
    request: Request, uid: FromPath[str], data: PromoUpdate
) -> Response:
    """Update a promo's catalog fields. IC only."""
    user = await get_optional_user(request)
    _require_ic(user)
    promo = await get_promo_by_uid(uid)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo not found")

    updates = {
        f: v
        for f in data.__struct_fields__
        if (v := getattr(data, f)) is not msgspec.UNSET
    }
    if "league_uids" in updates and updates["league_uids"]:
        await _validate_league_uids(updates["league_uids"])
    for field, value in updates.items():
        if isinstance(value, date):
            value = datetime(value.year, value.month, value.day)
        setattr(promo, field, value)

    promo.modified = datetime.now(UTC)
    bd = await save_promo(promo)
    broadcast_precomputed(bd)
    # Self-heal: this read-modify-write may overlap a concurrent holdings
    # recompute; re-deriving from source data always converges.
    schedule_recompute([uid])
    return Response(
        content=encoder.encode(msgspec.to_builtins(promo)),
        media_type="application/json",
    )


@delete("/{uid:str}")
async def delete_promo(request: Request, uid: FromPath[str]) -> None:
    """Soft-delete an unreferenced promo. IC only.

    A referenced promo must be retired (active=false) instead: the universal
    soft-delete tombstone hard-deletes it client-side, which would dangle the
    historical distribution rows and raffle prizes pointing at it.
    """
    user = await get_optional_user(request)
    _require_ic(user)
    promo = await get_promo_by_uid(uid)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo not found")
    if await count_promo_references(uid):
        raise HTTPException(
            status_code=409,
            detail="Promo is referenced by tournament reports — retire it instead",
        )

    promo.deleted_at = datetime.now(UTC)
    promo.modified = datetime.now(UTC)
    bd = await save_promo(promo)
    broadcast_precomputed(bd)


# Ledger movements (promo_ledger, not synced) are officials-only back office.
# Stock is recomputed server-side and streamed via Promo/User, never derived client-side.


class LedgerLine(msgspec.Struct):
    promo_uid: str
    qty: int


class LedgerEntryCreate(msgspec.Struct):
    kind: PromoLedgerKind
    lines: list[LedgerLine]
    to_uid: str | None = None
    from_uid: str | None = None  # IC only; defaults to the actor
    note: str = ""
    happened_at: datetime | None = None


@post("/ledger")
async def create_ledger_entries(request: Request, data: LedgerEntryCreate) -> Response:
    """Record one inventory movement across several promos — one row per line,
    written all-or-nothing. Self-sourced (own stock) for anyone; IC may record
    for another holder (unrecorded supply needs no prior stock). Intake (batch
    received from BCP, from_uid = the receiving holder) is officials-only: NC
    for their own pool, IC for anyone."""
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    # Membership floor: every real holder has a VEKN ID — keeps drive-by accounts
    # from writing rows (movements stay auditable, correctable via compensating rows).
    if not user.vekn_id:
        raise HTTPException(status_code=403, detail="VEKN membership required")
    from_uid = data.from_uid or user.uid
    if from_uid != user.uid and not permissions.can_manage_promos(user):
        raise HTTPException(
            status_code=403, detail="Only IC can record movements for another holder"
        )
    # Intake creates stock from nothing: officials only (self check above
    # already restricts NC to their own pool).
    if data.kind == PromoLedgerKind.INTAKE and not permissions.can_record_promo_intake(
        user
    ):
        raise HTTPException(
            status_code=403, detail="Only IC or NC can record an intake"
        )
    if not data.lines:
        raise HTTPException(status_code=400, detail="At least one line is required")
    if any(line.qty == 0 for line in data.lines):
        raise HTTPException(status_code=400, detail="qty must be non-zero")
    promo_uids = [line.promo_uid for line in data.lines]
    if len(set(promo_uids)) != len(promo_uids):
        raise HTTPException(
            status_code=400, detail="A promo may appear only once per submission"
        )
    known = {promo.uid for promo in await get_all_promos()}
    if not set(promo_uids) <= known:
        raise HTTPException(status_code=404, detail="Promo not found")
    if data.kind == PromoLedgerKind.ASSIGNMENT:
        if not data.to_uid:
            raise HTTPException(status_code=400, detail="Assignment requires to_uid")
        # Credits and debits the same holder — nets to zero in the recompute.
        if data.to_uid == from_uid:
            raise HTTPException(
                status_code=400,
                detail="Self-assignment is a no-op — record an intake instead",
            )
        if not await get_user_by_uid(data.to_uid):
            raise HTTPException(status_code=400, detail="Assignee not found")
    elif data.to_uid:
        raise HTTPException(status_code=400, detail="Only assignments have to_uid")

    now = datetime.now(UTC)
    entries = [
        PromoLedgerEntry(
            uid=str(uuid7()),
            kind=data.kind,
            promo_uid=line.promo_uid,
            qty=line.qty,
            from_uid=from_uid,
            to_uid=data.to_uid,
            note=data.note,
            happened_at=data.happened_at or now,
            created_by=user.uid,
            created_at=now,
        )
        for line in data.lines
    ]
    await insert_promo_ledger_entries(entries)
    schedule_recompute(promo_uids)
    return Response(
        content=encoder.encode(msgspec.to_builtins(entries)),
        media_type="application/json",
    )


@get("/ledger")
async def list_ledger_entries(request: Request) -> Response:
    """The whole role-scoped ledger, oldest first — no pagination by design
    (small dataset; filtering/aggregation happen client-side)."""
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    whole_ledger = permissions.can_view_full_promo_ledger(user)
    entries = await get_promo_ledger_entries(None if whole_ledger else user.uid)
    return Response(
        content=encoder.encode(msgspec.to_builtins(entries)),
        media_type="application/json",
    )


# Served UNAUTHENTICATED by design: the service worker never caches JWT-bearing
# responses, and these images must be cacheable for offline display.
MAX_PROMO_IMAGE_SIZE = 1024 * 1024


@post("/{uid:str}/image")
async def upload_promo_image(
    request: Request,
    uid: FromPath[str],
    data: Annotated[UploadFile, Body(media_type=RequestEncodingType.MULTI_PART)],
) -> Response:
    """Upload or replace a promo image. IC only. Max 1MB webp/png/jpeg."""
    user = await get_optional_user(request)
    _require_ic(user)
    promo = await get_promo_by_uid(uid)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo not found")

    if data.content_type not in ("image/webp", "image/png", "image/jpeg"):
        raise HTTPException(status_code=400, detail="Image must be webp, png, or jpeg")

    image_bytes = await data.read()
    if len(image_bytes) > MAX_PROMO_IMAGE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Image too large. Max size: {MAX_PROMO_IMAGE_SIZE // 1024}KB",
        )

    await upsert_promo_image(uid, image_bytes, data.content_type or "image/webp")

    now = datetime.now(UTC)
    version = int(now.timestamp() * 1000)  # cache-busting token baked into the URL
    promo.image_path = f"/api/promos/{uid}/image?v={version}"
    promo.modified = now
    bd = await save_promo(promo)
    broadcast_precomputed(bd)

    return Response(content=b'{"success": true}', media_type="application/json")


@get("/{uid:str}/image")
async def get_promo_image_endpoint(uid: FromPath[str], request: Request) -> Response:
    """Serve a promo image. A versioned (?v=) URL is immutable, so it can be
    cached aggressively; an unversioned request gets a short TTL."""
    result = await get_promo_image(uid)
    if not result:
        raise HTTPException(status_code=404, detail="Promo image not found")

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


@delete("/{uid:str}/image")
async def delete_promo_image_endpoint(request: Request, uid: FromPath[str]) -> None:
    """Delete a promo image. IC only."""
    user = await get_optional_user(request)
    _require_ic(user)
    promo = await get_promo_by_uid(uid)
    if not promo:
        raise HTTPException(status_code=404, detail="Promo not found")

    await delete_promo_image(uid)
    promo.image_path = None
    promo.modified = datetime.now(UTC)
    bd = await save_promo(promo)
    broadcast_precomputed(bd)


router = Router(
    "/api/promos",
    route_handlers=[
        create_promo,
        update_promo,
        delete_promo,
        create_ledger_entries,
        list_ledger_entries,
        upload_promo_image,
        get_promo_image_endpoint,
        delete_promo_image_endpoint,
    ],
)
