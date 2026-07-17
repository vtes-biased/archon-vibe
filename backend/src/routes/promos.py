"""Promo catalog API endpoints (IC-only writes; reads sync via SSE)."""

import logging
from datetime import UTC, datetime
from uuid import uuid7

import msgspec
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from ..broadcast import broadcast_precomputed
from ..db import (
    count_promo_references,
    get_league_by_uid,
    get_promo_by_uid,
    save_promo,
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
