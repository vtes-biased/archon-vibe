"""Leagues API endpoints."""

import logging
from datetime import UTC, datetime

import msgspec
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
from uuid6 import uuid7

from ..db import (
    get_child_leagues,
    get_league_by_uid,
    get_user_by_uid,
    insert_league,
    update_league,
)
from ..models import League, LeagueKind, LeagueStandingsMode, Role
from .auth import verify_token

router = APIRouter(prefix="/api/leagues", tags=["leagues"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()

# Broadcast function will be set by main.py
broadcast_league_event = None


async def _get_current_user(authorization: str | None):
    """Extract and verify current user from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    try:
        user_uid = verify_token(token, expected_type="access")
        return await get_user_by_uid(user_uid)
    except Exception:
        return None


class LeagueCreate(BaseModel):
    name: str
    kind: LeagueKind = LeagueKind.LEAGUE
    standings_mode: LeagueStandingsMode = LeagueStandingsMode.RTP
    format: str | None = None
    country: str | None = None
    start: datetime | None = None
    finish: datetime | None = None
    description: str = ""
    parent_uid: str | None = None


class LeagueUpdate(BaseModel):
    name: str | None = None
    standings_mode: LeagueStandingsMode | None = None
    format: str | None = None
    country: str | None = None
    start: datetime | None = None
    finish: datetime | None = None
    description: str | None = None
    parent_uid: str | None = None


def _can_manage_leagues(user) -> bool:
    """Check if user can create/delete leagues (NC/IC only)."""
    return Role.IC in user.roles or Role.NC in user.roles


def _can_edit_league(user, league: League) -> bool:
    """Check if user can edit a league (organizer, NC, or IC)."""
    if Role.IC in user.roles:
        return True
    if Role.NC in user.roles and league.country == user.country:
        return True
    return user.uid in league.organizers_uids


@router.post("/")
async def create_league(
    body: LeagueCreate,
    authorization: str | None = Header(None),
) -> Response:
    """Create a new league. NC/IC only."""
    user = await _get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    if not _can_manage_leagues(user):
        raise HTTPException(403, "Only NC and IC can create leagues")

    # Validate parent for child leagues
    if body.parent_uid:
        parent = await get_league_by_uid(body.parent_uid)
        if not parent:
            raise HTTPException(400, "Parent league not found")
        if parent.kind != LeagueKind.META:
            raise HTTPException(400, "Parent must be a Meta-League")
        if parent.parent_uid:
            raise HTTPException(400, "Cannot nest more than 2 levels")

    # Meta-leagues cannot have a parent
    if body.kind == LeagueKind.META and body.parent_uid:
        raise HTTPException(400, "Meta-League cannot have a parent")

    now = datetime.now(UTC)
    league = League(
        uid=str(uuid7()),
        modified=now,
        name=body.name,
        kind=body.kind,
        standings_mode=body.standings_mode,
        format=body.format,
        country=body.country,
        start=body.start,
        finish=body.finish,
        description=body.description,
        organizers_uids=[user.uid],
        parent_uid=body.parent_uid,
    )
    bd = await insert_league(league)
    if broadcast_league_event:
        broadcast_league_event(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(league)),
        media_type="application/json",
        status_code=201,
    )


@router.get("/{uid}")
async def get_league(uid: str) -> Response:
    """Get a league by UID."""
    league = await get_league_by_uid(uid)
    if not league:
        raise HTTPException(404, "League not found")
    return Response(
        content=encoder.encode(msgspec.to_builtins(league)),
        media_type="application/json",
    )


@router.put("/{uid}")
async def update_league_endpoint(
    uid: str,
    body: LeagueUpdate,
    authorization: str | None = Header(None),
) -> Response:
    """Update a league."""
    user = await _get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    league = await get_league_by_uid(uid)
    if not league:
        raise HTTPException(404, "League not found")
    if not _can_edit_league(user, league):
        raise HTTPException(403, "Not authorized to edit this league")

    # Validate parent_uid if provided
    updates = body.model_dump(exclude_unset=True)
    if "parent_uid" in updates:
        new_parent = updates["parent_uid"]
        if league.kind == LeagueKind.META:
            raise HTTPException(400, "Meta-League cannot have a parent")
        if new_parent:
            if new_parent == uid:
                raise HTTPException(400, "League cannot be its own parent")
            parent = await get_league_by_uid(new_parent)
            if not parent:
                raise HTTPException(400, "Parent league not found")
            if parent.kind != LeagueKind.META:
                raise HTTPException(400, "Parent must be a Meta-League")
            if parent.parent_uid:
                raise HTTPException(400, "Cannot nest more than 2 levels")

    # Apply updates
    for field, value in updates.items():
        setattr(league, field, value)

    league.modified = datetime.now(UTC)
    bd = await update_league(league)
    if broadcast_league_event:
        broadcast_league_event(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(league)),
        media_type="application/json",
    )


@router.delete("/{uid}")
async def delete_league_endpoint(
    uid: str,
    authorization: str | None = Header(None),
) -> Response:
    """Soft-delete a league."""
    user = await _get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    league = await get_league_by_uid(uid)
    if not league:
        raise HTTPException(404, "League not found")
    if not _can_edit_league(user, league):
        raise HTTPException(403, "Not authorized to delete this league")

    # Block deletion of meta-league with children
    if league.kind == LeagueKind.META:
        children = await get_child_leagues(uid)
        active_children = [c for c in children if not c.deleted_at]
        if active_children:
            raise HTTPException(
                400, "Cannot delete Meta-League with active child leagues"
            )

    league.deleted_at = datetime.now(UTC)
    league.modified = datetime.now(UTC)
    bd = await update_league(league)
    if broadcast_league_event:
        broadcast_league_event(bd)
    return Response(status_code=204)


class OrganizerAction(BaseModel):
    user_uid: str


@router.post("/{uid}/organizers")
async def add_organizer(
    uid: str,
    body: OrganizerAction,
    authorization: str | None = Header(None),
) -> Response:
    """Add an organizer to a league."""
    user = await _get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    league = await get_league_by_uid(uid)
    if not league:
        raise HTTPException(404, "League not found")
    if not _can_edit_league(user, league):
        raise HTTPException(403, "Not authorized")

    if body.user_uid not in league.organizers_uids:
        league.organizers_uids.append(body.user_uid)
        league.modified = datetime.now(UTC)
        bd = await update_league(league)
        if broadcast_league_event:
            broadcast_league_event(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(league)),
        media_type="application/json",
    )


@router.delete("/{uid}/organizers/{organizer_uid}")
async def remove_organizer(
    uid: str,
    organizer_uid: str,
    authorization: str | None = Header(None),
) -> Response:
    """Remove an organizer from a league."""
    user = await _get_current_user(authorization)
    if not user:
        raise HTTPException(401, "Authentication required")
    league = await get_league_by_uid(uid)
    if not league:
        raise HTTPException(404, "League not found")
    if not _can_edit_league(user, league):
        raise HTTPException(403, "Not authorized")

    if organizer_uid in league.organizers_uids:
        if len(league.organizers_uids) <= 1:
            raise HTTPException(400, "Cannot remove the last organizer")
        league.organizers_uids.remove(organizer_uid)
        league.modified = datetime.now(UTC)
        bd = await update_league(league)
        if broadcast_league_event:
            broadcast_league_event(bd)
    return Response(
        content=encoder.encode(msgspec.to_builtins(league)),
        media_type="application/json",
    )
