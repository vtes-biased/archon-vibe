"""Leagues API endpoints."""

import logging
from datetime import UTC, date, datetime
from uuid import uuid7

import msgspec
from litestar import Request, Response, Router, delete, post, put
from litestar.exceptions import HTTPException
from litestar.params import FromPath

from .. import permissions
from ..broadcast import broadcast_precomputed
from ..db import (
    get_child_leagues,
    get_league_by_uid,
    get_user_by_uid,
    save_league,
)
from ..geonames import stored_country
from ..middleware.auth import get_optional_user
from ..models import League, LeagueKind, LeagueStandingsMode

logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()


class LeagueCreate(msgspec.Struct):
    name: str
    kind: LeagueKind = LeagueKind.LEAGUE
    standings_mode: LeagueStandingsMode = LeagueStandingsMode.RTP
    format: str | None = None
    country: str | None = None
    start: date | None = None
    finish: date | None = None
    description: str = ""
    parent_uid: str | None = None
    open_to_country_princes: bool = False


class LeagueUpdate(msgspec.Struct):
    name: str | msgspec.UnsetType = msgspec.UNSET
    standings_mode: LeagueStandingsMode | msgspec.UnsetType = msgspec.UNSET
    format: str | None | msgspec.UnsetType = msgspec.UNSET
    country: str | None | msgspec.UnsetType = msgspec.UNSET
    start: date | None | msgspec.UnsetType = msgspec.UNSET
    finish: date | None | msgspec.UnsetType = msgspec.UNSET
    description: str | msgspec.UnsetType = msgspec.UNSET
    parent_uid: str | None | msgspec.UnsetType = msgspec.UNSET
    open_to_country_princes: bool | msgspec.UnsetType = msgspec.UNSET


@post("/")
async def create_league(request: Request, data: LeagueCreate) -> Response:
    """Create a new league. NC/IC only."""
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not permissions.can_manage_leagues(user):
        raise HTTPException(status_code=403, detail="Only NC and IC can create leagues")

    if data.parent_uid:
        parent = await get_league_by_uid(data.parent_uid)
        if not parent:
            raise HTTPException(status_code=400, detail="Parent league not found")
        if parent.kind != LeagueKind.META:
            raise HTTPException(status_code=400, detail="Parent must be a Meta-League")
        if parent.parent_uid:
            raise HTTPException(
                status_code=400, detail="Cannot nest more than 2 levels"
            )

    if data.kind == LeagueKind.META and data.parent_uid:
        raise HTTPException(status_code=400, detail="Meta-League cannot have a parent")

    country = stored_country(data.country)
    if data.country and country is None:
        raise HTTPException(status_code=422, detail=f"Invalid country: {data.country}")

    now = datetime.now(UTC)
    league = League(
        uid=str(uuid7()),
        modified=now,
        name=data.name,
        kind=data.kind,
        standings_mode=data.standings_mode,
        format=data.format,
        country=country,
        start=datetime(d.year, d.month, d.day) if (d := data.start) else None,
        finish=datetime(d.year, d.month, d.day) if (d := data.finish) else None,
        description=data.description,
        organizers_uids=[user.uid],
        parent_uid=data.parent_uid,
        # Inert without a country — keep stored state canonical.
        open_to_country_princes=(
            data.open_to_country_princes if data.country else False
        ),
    )
    bd = await save_league(league)
    broadcast_precomputed(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(league)),
        media_type="application/json",
    )


@put("/{uid:str}")
async def update_league_endpoint(
    request: Request, uid: FromPath[str], data: LeagueUpdate
) -> Response:
    """Update a league."""
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    league = await get_league_by_uid(uid)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not permissions.can_edit_league(user, league):
        raise HTTPException(
            status_code=403, detail="Not authorized to edit this league"
        )

    updates = {
        f: v
        for f in data.__struct_fields__
        if (v := getattr(data, f)) is not msgspec.UNSET
    }
    if "country" in updates:
        updates["country"] = stored_country(updates["country"])
        if data.country and updates["country"] is None:
            raise HTTPException(
                status_code=422, detail=f"Invalid country: {data.country}"
            )
    if "parent_uid" in updates:
        new_parent = updates["parent_uid"]
        if league.kind == LeagueKind.META:
            raise HTTPException(
                status_code=400, detail="Meta-League cannot have a parent"
            )
        if new_parent:
            if new_parent == uid:
                raise HTTPException(
                    status_code=400, detail="League cannot be its own parent"
                )
            parent = await get_league_by_uid(new_parent)
            if not parent:
                raise HTTPException(status_code=400, detail="Parent league not found")
            if parent.kind != LeagueKind.META:
                raise HTTPException(
                    status_code=400, detail="Parent must be a Meta-League"
                )
            if parent.parent_uid:
                raise HTTPException(
                    status_code=400, detail="Cannot nest more than 2 levels"
                )

    for field, value in updates.items():
        if isinstance(value, date):
            value = datetime(value.year, value.month, value.day)
        setattr(league, field, value)

    # Inert without a country — keep stored state canonical.
    if not league.country:
        league.open_to_country_princes = False

    league.modified = datetime.now(UTC)
    bd = await save_league(league)
    broadcast_precomputed(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(league)),
        media_type="application/json",
    )


@delete("/{uid:str}")
async def delete_league_endpoint(request: Request, uid: FromPath[str]) -> None:
    """Soft-delete a league."""
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    league = await get_league_by_uid(uid)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not permissions.can_edit_league(user, league):
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this league"
        )

    if league.kind == LeagueKind.META:
        children = await get_child_leagues(uid)
        active_children = [c for c in children if not c.deleted_at]
        if active_children:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete Meta-League with active child leagues",
            )

    league.deleted_at = datetime.now(UTC)
    league.modified = datetime.now(UTC)
    bd = await save_league(league)
    broadcast_precomputed(bd)


class OrganizerAction(msgspec.Struct):
    user_uid: str


@post("/{uid:str}/organizers")
async def add_organizer(
    request: Request, uid: FromPath[str], data: OrganizerAction
) -> Response:
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    league = await get_league_by_uid(uid)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not permissions.can_edit_league(user, league):
        raise HTTPException(status_code=403, detail="Not authorized")

    # A non-member sits at public level, where the league projection carries no
    # roster — they would never see the league they nominally organize.
    organizer = await get_user_by_uid(data.user_uid)
    if not organizer or not organizer.vekn_id:
        raise HTTPException(status_code=400, detail="Organizer must be a VEKN member")

    if data.user_uid not in league.organizers_uids:
        league.organizers_uids.append(data.user_uid)
        league.modified = datetime.now(UTC)
        bd = await save_league(league)
        broadcast_precomputed(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(league)),
        media_type="application/json",
    )


@delete("/{uid:str}/organizers/{organizer_uid:str}", status_code=200)
async def remove_organizer(
    request: Request, uid: FromPath[str], organizer_uid: FromPath[str]
) -> Response:
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    league = await get_league_by_uid(uid)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    if not permissions.can_edit_league(user, league):
        raise HTTPException(status_code=403, detail="Not authorized")

    if organizer_uid in league.organizers_uids:
        if len(league.organizers_uids) <= 1:
            raise HTTPException(
                status_code=400, detail="Cannot remove the last organizer"
            )
        league.organizers_uids.remove(organizer_uid)
        league.modified = datetime.now(UTC)
        bd = await save_league(league)
        broadcast_precomputed(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(league)),
        media_type="application/json",
    )


router = Router(
    "/api/leagues",
    route_handlers=[
        create_league,
        update_league_endpoint,
        delete_league_endpoint,
        add_organizer,
        remove_organizer,
    ],
)
