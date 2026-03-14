"""Third-party API endpoints (v1).

All endpoints require authentication (access or OAuth token).
Access level derived from user's role:
- IC -> full column
- NC/Prince + same country -> full column
- Has vekn_id -> member column
- Default -> public column
"""

import logging

from fastapi import APIRouter, HTTPException, Response

from ..db import get_connection
from ..middleware.auth import CurrentUser
from ..models import ObjectType, Role

router = APIRouter(prefix="/api/v1", tags=["api_v1"])
logger = logging.getLogger(__name__)


def _access_level(user) -> str:
    """Determine access level column for user."""
    if Role.IC in user.roles:
        return "full"
    if user.vekn_id:
        return "member"
    return "public"


def _access_level_for_country(user, obj_country: str | None) -> str:
    """Determine access level, upgrading to full for NC/Prince of same country."""
    base = _access_level(user)
    if base == "member" and obj_country and user.country == obj_country:
        if Role.NC in user.roles or Role.PRINCE in user.roles:
            return "full"
    return base


@router.get("/users/")
async def list_users(user: CurrentUser) -> Response:
    """List all users."""
    level = _access_level(user)
    async with get_connection() as conn:
        cursor = await conn.execute(
            f'SELECT "{level}"::text FROM objects WHERE type = %s AND "{level}" IS NOT NULL AND deleted_at IS NULL ORDER BY modified_at DESC',
            (ObjectType.USER,),
        )
        rows = await cursor.fetchall()
    joined = ",".join(r[0] for r in rows if r[0])
    return Response(content=f"[{joined}]", media_type="application/json")


@router.get("/users/{uid}")
async def get_user(uid: str, user: CurrentUser) -> Response:
    """Get a single user."""
    level = _access_level(user)
    async with get_connection() as conn:
        cursor = await conn.execute(
            f'SELECT "{level}"::text FROM objects WHERE uid = %s AND type = %s',
            (uid, ObjectType.USER),
        )
        row = await cursor.fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="User not found")
    return Response(content=row[0], media_type="application/json")


@router.get("/tournaments/{uid}")
async def get_tournament(uid: str, user: CurrentUser) -> Response:
    """Get a single tournament."""
    # Need to peek at country for NC/Prince upgrade
    async with get_connection() as conn:
        cursor = await conn.execute(
            'SELECT "full"->>\'country\' FROM objects WHERE uid = %s AND type = %s',
            (uid, ObjectType.TOURNAMENT),
        )
        meta = await cursor.fetchone()
    if not meta:
        raise HTTPException(status_code=404, detail="Tournament not found")

    level = _access_level_for_country(user, meta[0])
    async with get_connection() as conn:
        cursor = await conn.execute(
            f'SELECT "{level}"::text FROM objects WHERE uid = %s AND type = %s',
            (uid, ObjectType.TOURNAMENT),
        )
        row = await cursor.fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return Response(content=row[0], media_type="application/json")


@router.get("/leagues/{uid}")
async def get_league(uid: str, user: CurrentUser) -> Response:
    """Get a single league."""
    level = _access_level(user)
    async with get_connection() as conn:
        cursor = await conn.execute(
            f'SELECT "{level}"::text FROM objects WHERE uid = %s AND type = %s',
            (uid, ObjectType.LEAGUE),
        )
        row = await cursor.fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="League not found")
    return Response(content=row[0], media_type="application/json")


@router.get("/sanctions/user/{user_uid}")
async def get_user_sanctions(user_uid: str, user: CurrentUser) -> Response:
    """Get sanctions for a user."""
    level = _access_level(user)
    async with get_connection() as conn:
        cursor = await conn.execute(
            f"""SELECT "{level}"::text FROM objects WHERE type = %s AND "full"->>'user_uid' = %s AND "{level}" IS NOT NULL AND deleted_at IS NULL""",
            (ObjectType.SANCTION, user_uid),
        )
        rows = await cursor.fetchall()
    joined = ",".join(r[0] for r in rows if r[0])
    return Response(content=f"[{joined}]", media_type="application/json")
