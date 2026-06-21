"""Sanctions API endpoints."""

import json
import logging
from datetime import UTC, date, datetime, timedelta
from uuid import uuid7

import msgspec
from archon_engine import PyEngine
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from .. import permissions
from ..broadcast import broadcast_precomputed
from ..db import (
    get_league_by_uid,
    get_sanction_by_uid,
    get_sanctions_for_tournament,
    get_tournament_by_uid,
    get_user_by_uid,
    save_sanction,
    save_tournament,
)
from ..middleware.auth import OptionalUser
from ..models import (
    SUBCATEGORIES_BY_CATEGORY,
    PlayerState,
    Role,
    Sanction,
    SanctionCategory,
    SanctionLevel,
    SanctionSubcategory,
    Tournament,
)

router = APIRouter(prefix="/sanctions", tags=["sanctions"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()
_engine = PyEngine()

# Maximum expiry for probation/suspension (18 months)
MAX_EXPIRY_MONTHS = 18


async def _can_issue_sanction(
    issuer, level: SanctionLevel, tournament_uid: str | None
) -> bool:
    """Fetch the tournament (for the organizer check) and delegate the decision
    to the engine — see permissions.can_issue_sanction."""
    tournament = await get_tournament_by_uid(tournament_uid) if tournament_uid else None
    return permissions.can_issue_sanction(issuer, level, tournament)


async def _can_lift_sanction(user, sanction: Sanction) -> bool:
    """Fetch the tournament/league context and delegate the decision to the
    engine — see permissions.can_lift_sanction."""
    tournament = (
        await get_tournament_by_uid(sanction.tournament_uid)
        if sanction.tournament_uid
        else None
    )
    league = None
    if (
        sanction.level == SanctionLevel.DISQUALIFICATION
        and tournament
        and tournament.league_uid
    ):
        league = await get_league_by_uid(tournament.league_uid)
    return permissions.can_lift_sanction(user, sanction, tournament, league)


async def _can_delete_sanction(user, sanction: Sanction) -> bool:
    """Fetch the tournament context and delegate the decision to the engine —
    see permissions.can_delete_sanction."""
    tournament = (
        await get_tournament_by_uid(sanction.tournament_uid)
        if sanction.tournament_uid
        else None
    )
    return permissions.can_delete_sanction(user, sanction, tournament)


def _validate_expiry(
    level: SanctionLevel, expires_at: datetime | None, issued_at: datetime
) -> None:
    """Validate expiry rules for sanction levels.

    Rules:
    - PROBATION: requires expires_at within 18 months
    - SUSPENSION: expires_at optional, but if set must be within 18 months
    """
    max_expiry = issued_at + timedelta(days=MAX_EXPIRY_MONTHS * 30)

    if level == SanctionLevel.PROBATION:
        if expires_at is None:
            raise HTTPException(
                status_code=400,
                detail="PROBATION requires an expiry date (expires_at)",
            )
        if expires_at > max_expiry:
            raise HTTPException(
                status_code=400,
                detail=f"PROBATION expires_at must be within {MAX_EXPIRY_MONTHS} months",
            )

    if level == SanctionLevel.SUSPENSION and expires_at is not None:
        if expires_at > max_expiry:
            raise HTTPException(
                status_code=400,
                detail=f"SUSPENSION expires_at must be within {MAX_EXPIRY_MONTHS} months",
            )


async def _set_player_dq_state(
    tournament_uid: str, user_uid: str, new_state: PlayerState
) -> None:
    """Set a player's state on a tournament (for DQ sanctions).

    Updates the tournament object and broadcasts the change.
    """
    tournament = await get_tournament_by_uid(tournament_uid)
    if not tournament:
        return
    for player in tournament.players:
        if player.user_uid == user_uid:
            player.state = new_state
            break
    else:
        return  # Player not found in tournament

    tournament.modified = datetime.now(UTC)
    bd = await save_tournament(tournament)
    broadcast_precomputed(bd)


async def _recompute_tournament_standings(tournament_uid: str) -> None:
    """Refresh a tournament's standings after a standings_adjustment (SA) changes.

    Issuing/lifting/deleting an SA is not a TournamentEvent, so standings would
    otherwise only pick up the -1 VP penalty on the next tournament action. The
    engine recompute (same update_standings every event ends with) is the single
    source of truth, so we don't re-implement SA scoring here. No-op when the
    tournament has no rounds (the engine guards that too). Call AFTER the sanction
    mutation is saved, so the refetched sanctions reflect it.
    """
    tournament = await get_tournament_by_uid(tournament_uid)
    if not tournament or not tournament.rounds:
        return
    sanctions = await get_sanctions_for_tournament(tournament_uid)
    sanctions_data = [
        {
            "user_uid": s.user_uid,
            "level": s.level.value,
            "round_number": s.round_number,
            "lifted_at": s.lifted_at.isoformat() if s.lifted_at else None,
            "deleted_at": s.deleted_at.isoformat() if s.deleted_at else None,
        }
        for s in sanctions
    ]
    tournament_json = encoder.encode(tournament).decode("utf-8")
    sanctions_json = msgspec.json.encode(sanctions_data).decode("utf-8")
    result_json = _engine.update_standings(tournament_json, sanctions_json)
    updated = msgspec.convert(json.loads(result_json), Tournament)
    updated.modified = datetime.now(UTC)
    bd = await save_tournament(updated)
    broadcast_precomputed(bd)


class CreateSanctionRequest(BaseModel):
    """Request body for creating a sanction."""

    user_uid: str
    level: str
    category: str
    subcategory: str | None = None
    round_number: int | None = None
    description: str
    expires_at: str | None = None  # ISO datetime string
    tournament_uid: str | None = None


class UpdateSanctionRequest(BaseModel):
    """Request body for updating a sanction."""

    level: str | None = None
    category: str | None = None
    subcategory: str | None = None
    round_number: int | None = None
    description: str | None = None
    expires_at: str | None = None  # YYYY-MM-DD date string
    lifted: bool | None = None


@router.post("/", status_code=201)
async def create_sanction(
    request: CreateSanctionRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Create a new sanction.

    Only IC and Ethics can issue SUSPENSION and PROBATION outside tournaments.
    """
    # Authenticate
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Validate level and category
    try:
        level = SanctionLevel(request.level)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid level: {request.level}. Valid: {[lv.value for lv in SanctionLevel]}",
        ) from e

    try:
        category = SanctionCategory(request.category)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category: {request.category}. Valid: {[c.value for c in SanctionCategory]}",
        ) from e

    # Validate subcategory if provided
    subcategory = None
    if request.subcategory is not None:
        try:
            subcategory = SanctionSubcategory(request.subcategory)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid subcategory: {request.subcategory}",
            ) from e
        # Validate subcategory belongs to parent category
        valid_subs = SUBCATEGORIES_BY_CATEGORY.get(category, [])
        if subcategory not in valid_subs:
            raise HTTPException(
                status_code=400,
                detail=f"Subcategory '{subcategory.value}' not valid for category '{category.value}'",
            )

    # Validate round_number
    round_number = request.round_number
    if level == SanctionLevel.STANDINGS_ADJUSTMENT and round_number is None:
        raise HTTPException(
            status_code=400,
            detail="round_number is required for standings_adjustment sanctions",
        )
    if round_number is not None and request.tournament_uid:
        tournament = await get_tournament_by_uid(request.tournament_uid)
        if tournament and round_number >= len(tournament.rounds):
            raise HTTPException(
                status_code=400,
                detail=f"round_number {round_number} exceeds tournament rounds ({len(tournament.rounds)})",
            )

    # Check permission
    if not await _can_issue_sanction(current_user, level, request.tournament_uid):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to issue this type of sanction",
        )

    # Validate target user exists
    target_user = await get_user_by_uid(request.user_uid)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    # Parse and validate expires_at (date-only YYYY-MM-DD, stored as UTC midnight)
    issued_at = datetime.now(UTC)
    expires_at = None
    if request.expires_at:
        try:
            d = date.fromisoformat(request.expires_at)
            expires_at = datetime(d.year, d.month, d.day, tzinfo=UTC)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid expires_at format (expected YYYY-MM-DD): {e}",
            ) from e

    _validate_expiry(level, expires_at, issued_at)

    # Create sanction
    sanction = Sanction(
        uid=str(uuid7()),
        modified=issued_at,
        user_uid=request.user_uid,
        issued_by_uid=current_user.uid,
        tournament_uid=request.tournament_uid,
        level=level,
        category=category,
        subcategory=subcategory,
        round_number=round_number,
        description=request.description,
        issued_at=issued_at,
        expires_at=expires_at,
    )

    bd = await save_sanction(sanction)
    logger.info(
        f"Sanction {sanction.uid} ({level.value}) created for user {request.user_uid} "
        f"by {current_user.uid}"
    )

    # DQ sanction: set player state to Disqualified on the tournament
    if level == SanctionLevel.DISQUALIFICATION and request.tournament_uid:
        await _set_player_dq_state(
            request.tournament_uid, request.user_uid, PlayerState.DISQUALIFIED
        )
    # SA sanction: refresh standings so the -1 VP penalty shows immediately
    elif level == SanctionLevel.STANDINGS_ADJUSTMENT and request.tournament_uid:
        await _recompute_tournament_standings(request.tournament_uid)

    # Broadcast to SSE clients
    broadcast_precomputed(bd)

    return Response(
        content=encoder.encode(sanction),
        media_type="application/json",
        status_code=201,
    )


@router.put("/{uid}")
async def update_sanction_endpoint(
    uid: str,
    request: UpdateSanctionRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Update a sanction (lift or modify).

    Permissions:
    - Suspension/Probation: IC or Ethics can modify, IC can lift
    - Tournament sanctions: IC/Ethics can modify, Rulemonger/NC/IC can lift
    """
    # Authenticate
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get existing sanction
    sanction = await get_sanction_by_uid(uid)
    if not sanction:
        raise HTTPException(status_code=404, detail="Sanction not found")

    # Check lift permission separately
    if request.lifted is True and sanction.lifted_at is None:
        if not await _can_lift_sanction(current_user, sanction):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to lift this sanction",
            )

    # Check modify permission (IC/Ethics for all modifications)
    has_modify_fields = any(
        [
            request.level is not None,
            request.category is not None,
            request.subcategory is not None,
            request.round_number is not None,
            request.description is not None,
            request.expires_at is not None,
        ]
    )
    if has_modify_fields:
        if Role.IC not in current_user.roles and Role.ETHICS not in current_user.roles:
            raise HTTPException(
                status_code=403, detail="Only IC or Ethics can modify sanctions"
            )

    # Apply updates
    now = datetime.now(UTC)
    level = sanction.level
    category = sanction.category
    subcategory = sanction.subcategory
    round_number = sanction.round_number
    description = sanction.description
    expires_at = sanction.expires_at
    lifted_at = sanction.lifted_at
    lifted_by_uid = sanction.lifted_by_uid

    # Update level if provided
    if request.level is not None:
        try:
            level = SanctionLevel(request.level)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid level: {request.level}",
            ) from e

    # Update category if provided
    if request.category is not None:
        try:
            category = SanctionCategory(request.category)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category: {request.category}",
            ) from e

    # Update subcategory if provided
    if request.subcategory is not None:
        try:
            subcategory = SanctionSubcategory(request.subcategory)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid subcategory: {request.subcategory}",
            ) from e
        valid_subs = SUBCATEGORIES_BY_CATEGORY.get(category, [])
        if subcategory not in valid_subs:
            raise HTTPException(
                status_code=400,
                detail=f"Subcategory '{subcategory.value}' not valid for category '{category.value}'",
            )

    # Update round_number if provided (mirror create: must reference an existing
    # round, else the SA is silently inert — the engine recompute no-ops it).
    if request.round_number is not None:
        round_number = request.round_number
        if sanction.tournament_uid is not None:
            tournament = await get_tournament_by_uid(sanction.tournament_uid)
            if tournament and round_number >= len(tournament.rounds):
                raise HTTPException(
                    status_code=400,
                    detail=f"round_number {round_number} exceeds tournament rounds ({len(tournament.rounds)})",
                )

    # Update description if provided
    if request.description is not None:
        description = request.description.strip()
        if not description:
            raise HTTPException(status_code=400, detail="Description cannot be empty")

    # Update expires_at if provided
    if request.expires_at is not None:
        try:
            d = date.fromisoformat(request.expires_at)
            expires_at = datetime(d.year, d.month, d.day, tzinfo=UTC)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid expires_at format (expected YYYY-MM-DD): {e}",
            ) from e
        _validate_expiry(level, expires_at, sanction.issued_at)

    # Lift sanction if requested
    if request.lifted is True and sanction.lifted_at is None:
        lifted_at = now
        lifted_by_uid = current_user.uid

    # Create updated sanction
    updated = msgspec.structs.replace(
        sanction,
        modified=now,
        level=level,
        category=category,
        subcategory=subcategory,
        round_number=round_number,
        description=description,
        expires_at=expires_at,
        lifted_at=lifted_at,
        lifted_by_uid=lifted_by_uid,
    )

    bd = await save_sanction(updated)
    logger.info(f"Sanction {uid} updated by {current_user.uid}")

    # If a DQ sanction was lifted, restore player state on the tournament
    if (
        request.lifted is True
        and sanction.lifted_at is None
        and sanction.level == SanctionLevel.DISQUALIFICATION
        and sanction.tournament_uid
    ):
        await _set_player_dq_state(
            sanction.tournament_uid, sanction.user_uid, PlayerState.FINISHED
        )

    # SA touched (lifted, round changed, or level changed to/from SA): refresh
    # standings so the -1 VP penalty appears/clears immediately.
    if sanction.tournament_uid and (
        updated.level == SanctionLevel.STANDINGS_ADJUSTMENT
        or sanction.level == SanctionLevel.STANDINGS_ADJUSTMENT
    ):
        await _recompute_tournament_standings(sanction.tournament_uid)

    # Broadcast to SSE clients
    broadcast_precomputed(bd)

    return Response(
        content=encoder.encode(updated),
        media_type="application/json",
    )


@router.delete("/{uid}")
async def delete_sanction_endpoint(
    uid: str,
    current_user: OptionalUser = None,
) -> Response:
    """Soft delete a sanction.

    Sets deleted_at timestamp. Hard delete happens via cleanup job after 30 days.

    Permissions: IC/Ethics any sanction; a tournament organizer can delete
    organizer-issuable sanctions of their own tournament while it is not
    Finished (mistake correction at the event) — see engine can_delete_sanction.
    """
    # Authenticate
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get existing sanction
    sanction = await get_sanction_by_uid(uid)
    if not sanction:
        raise HTTPException(status_code=404, detail="Sanction not found")

    if sanction.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Sanction already deleted")

    # Check permission
    if not await _can_delete_sanction(current_user, sanction):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to delete this sanction",
        )

    # Soft delete
    now = datetime.now(UTC)
    updated = msgspec.structs.replace(sanction, modified=now, deleted_at=now)

    bd = await save_sanction(updated)
    logger.info(f"Sanction {uid} soft-deleted by {current_user.uid}")

    # Deleting an active DQ sanction restores the player on the tournament,
    # mirroring the lift path
    if (
        sanction.level == SanctionLevel.DISQUALIFICATION
        and sanction.lifted_at is None
        and sanction.tournament_uid
    ):
        await _set_player_dq_state(
            sanction.tournament_uid, sanction.user_uid, PlayerState.FINISHED
        )

    # Deleting an active SA drops its -1 VP penalty: refresh standings
    if (
        sanction.level == SanctionLevel.STANDINGS_ADJUSTMENT
        and sanction.lifted_at is None
        and sanction.tournament_uid
    ):
        await _recompute_tournament_standings(sanction.tournament_uid)

    # Broadcast to SSE clients
    broadcast_precomputed(bd)

    return Response(
        content=encoder.encode({"message": "Sanction deleted"}),
        media_type="application/json",
    )
