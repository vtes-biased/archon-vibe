"""Sanctions API endpoints."""

import logging
from datetime import UTC, date, datetime, timedelta

import msgspec
from archon_engine import PyEngine
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
from uuid6 import uuid7

from ..db import (
    get_league_by_uid,
    get_sanction_by_uid,
    get_sanctions_for_user,
    get_tournament_by_uid,
    get_user_by_uid,
    insert_sanction,
    update_sanction,
    update_tournament,
)
from ..models import (
    SUBCATEGORIES_BY_CATEGORY,
    PlayerState,
    Role,
    Sanction,
    SanctionCategory,
    SanctionLevel,
    SanctionSubcategory,
)
from .auth import verify_token

router = APIRouter(prefix="/sanctions", tags=["sanctions"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()

# Broadcast functions will be set by main.py
broadcast_sanction_event = None
broadcast_tournament_event = None

# Rust engine for permission checks
_engine = PyEngine()

# Maximum expiry for probation/suspension (18 months)
MAX_EXPIRY_MONTHS = 18


def _user_to_context(user) -> dict:
    """Convert User to context dict for engine."""
    return {
        "roles": [r.value for r in user.roles],
        "country": user.country,
        "vekn_id": user.vekn_id,
    }


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


async def _can_issue_sanction(
    issuer, level: SanctionLevel, tournament_uid: str | None
) -> bool:
    """Check if issuer can create a sanction of this level.

    Rules:
    - SUSPENSION/PROBATION: IC or Ethics only
    - CAUTION/WARNING/SA/DQ: IC, Ethics, or tournament organizer (requires tournament_uid)
    """
    is_ic_or_ethics = Role.IC in issuer.roles or Role.ETHICS in issuer.roles

    if level in (SanctionLevel.SUSPENSION, SanctionLevel.PROBATION):
        return is_ic_or_ethics

    if is_ic_or_ethics:
        return True

    # Tournament organizers can issue in-tournament sanctions
    if tournament_uid:
        tournament = await get_tournament_by_uid(tournament_uid)
        if tournament and issuer.uid in tournament.organizers_uids:
            return True

    return False


async def _can_lift_sanction(user, sanction: Sanction) -> bool:
    """Check if user can lift a sanction.

    Rules:
    - SUSPENSION/PROBATION: IC or Ethics
    - CAUTION/WARNING/SA/DQ: IC, Rulemonger, NC (same country as tournament), or
      league organizer (for DQ in a league tournament)
    """
    if sanction.level in (SanctionLevel.SUSPENSION, SanctionLevel.PROBATION):
        return Role.IC in user.roles or Role.ETHICS in user.roles

    # Tournament-level sanctions: IC, Rulemonger always
    if Role.IC in user.roles or Role.RULEMONGER in user.roles:
        return True

    # NC can lift if same country as the tournament
    if Role.NC in user.roles and sanction.tournament_uid:
        tournament = await get_tournament_by_uid(sanction.tournament_uid)
        if tournament and tournament.country and user.country == tournament.country:
            return True

    # League organizer can lift DQ from their league tournaments
    if sanction.level == SanctionLevel.DISQUALIFICATION and sanction.tournament_uid:
        tournament = await get_tournament_by_uid(sanction.tournament_uid)
        if tournament and tournament.league_uid:
            league = await get_league_by_uid(tournament.league_uid)
            if league and user.uid in (league.organizers_uids or []):
                return True

    return False


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
    bd = await update_tournament(tournament)
    if broadcast_tournament_event:
        broadcast_tournament_event(bd)


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
    authorization: str | None = Header(default=None),
) -> Response:
    """Create a new sanction.

    Only IC and Ethics can issue SUSPENSION and PROBATION outside tournaments.
    """
    # Authenticate
    current_user = await _get_current_user(authorization)
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

    bd = await insert_sanction(sanction)
    logger.info(
        f"Sanction {sanction.uid} ({level.value}) created for user {request.user_uid} "
        f"by {current_user.uid}"
    )

    # DQ sanction: set player state to Disqualified on the tournament
    if level == SanctionLevel.DISQUALIFICATION and request.tournament_uid:
        await _set_player_dq_state(
            request.tournament_uid, request.user_uid, PlayerState.DISQUALIFIED
        )

    # Broadcast to SSE clients
    if broadcast_sanction_event:
        broadcast_sanction_event(bd)

    return Response(
        content=encoder.encode(sanction),
        media_type="application/json",
        status_code=201,
    )


@router.put("/{uid}")
async def update_sanction_endpoint(
    uid: str,
    request: UpdateSanctionRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Update a sanction (lift or modify).

    Permissions:
    - Suspension/Probation: IC or Ethics can modify, IC can lift
    - Tournament sanctions: IC/Ethics can modify, Rulemonger/NC/IC can lift
    """
    # Authenticate
    current_user = await _get_current_user(authorization)
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

    # Update round_number if provided
    if request.round_number is not None:
        round_number = request.round_number

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
    updated = Sanction(
        uid=sanction.uid,
        modified=now,
        user_uid=sanction.user_uid,
        issued_by_uid=sanction.issued_by_uid,
        tournament_uid=sanction.tournament_uid,
        level=level,
        category=category,
        subcategory=subcategory,
        round_number=round_number,
        description=description,
        issued_at=sanction.issued_at,
        expires_at=expires_at,
        lifted_at=lifted_at,
        lifted_by_uid=lifted_by_uid,
        deleted_at=sanction.deleted_at,
    )

    bd = await update_sanction(updated)
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

    # Broadcast to SSE clients
    if broadcast_sanction_event:
        broadcast_sanction_event(bd)

    return Response(
        content=encoder.encode(updated),
        media_type="application/json",
    )


@router.delete("/{uid}")
async def delete_sanction_endpoint(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Soft delete a sanction.

    Sets deleted_at timestamp. Hard delete happens via cleanup job after 30 days.
    Only IC and Ethics can delete sanctions.
    """
    # Authenticate
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Check permission
    if Role.IC not in current_user.roles and Role.ETHICS not in current_user.roles:
        raise HTTPException(
            status_code=403, detail="Only IC or Ethics can delete sanctions"
        )

    # Get existing sanction
    sanction = await get_sanction_by_uid(uid)
    if not sanction:
        raise HTTPException(status_code=404, detail="Sanction not found")

    if sanction.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Sanction already deleted")

    # Soft delete
    now = datetime.now(UTC)
    updated = Sanction(
        uid=sanction.uid,
        modified=now,
        user_uid=sanction.user_uid,
        issued_by_uid=sanction.issued_by_uid,
        tournament_uid=sanction.tournament_uid,
        level=sanction.level,
        category=sanction.category,
        subcategory=sanction.subcategory,
        round_number=sanction.round_number,
        description=sanction.description,
        issued_at=sanction.issued_at,
        expires_at=sanction.expires_at,
        lifted_at=sanction.lifted_at,
        lifted_by_uid=sanction.lifted_by_uid,
        deleted_at=now,
    )

    bd = await update_sanction(updated)
    logger.info(f"Sanction {uid} soft-deleted by {current_user.uid}")

    # Broadcast to SSE clients
    if broadcast_sanction_event:
        broadcast_sanction_event(bd)

    return Response(
        content=encoder.encode({"message": "Sanction deleted"}),
        media_type="application/json",
    )


@router.get("/user/{user_uid}")
async def get_user_sanctions(
    user_uid: str,
    include_deleted: bool = False,
) -> Response:
    """Get all sanctions for a user.

    By default excludes soft-deleted sanctions unless include_deleted=True.
    """
    sanctions = await get_sanctions_for_user(user_uid)

    if not include_deleted:
        sanctions = [s for s in sanctions if s.deleted_at is None]

    return Response(
        content=encoder.encode(sanctions),
        media_type="application/json",
    )
