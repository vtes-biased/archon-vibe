import json
import logging
from datetime import UTC, date, datetime, timedelta
from uuid import uuid7

import msgspec
from archon_engine import PyEngine
from fastapi import APIRouter, HTTPException, Request, Response
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
    tournament_transaction,
)
from ..middleware.auth import OptionalUser
from ..models import (
    SUBCATEGORIES_BY_CATEGORY,
    PlayerState,
    Sanction,
    SanctionCategory,
    SanctionLevel,
    SanctionSubcategory,
    TableState,
    Tournament,
    TournamentState,
)

router = APIRouter(prefix="/sanctions", tags=["sanctions"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()
_engine = PyEngine()

MAX_EXPIRY_MONTHS = 18


@router.get("/reference")
async def get_sanction_reference() -> Response:
    """Public sanction reference owned by the Rust engine; the Discord bot
    builds its sanction UI from this."""
    return Response(content=_engine.sanction_reference(), media_type="application/json")


async def _can_issue_sanction(
    issuer, level: SanctionLevel, tournament_uid: str | None
) -> bool:
    tournament = await get_tournament_by_uid(tournament_uid) if tournament_uid else None
    return permissions.can_issue_sanction(issuer, level, tournament)


async def _can_lift_sanction(user, sanction: Sanction) -> bool:
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
    tournament = (
        await get_tournament_by_uid(sanction.tournament_uid)
        if sanction.tournament_uid
        else None
    )
    return permissions.can_delete_sanction(user, sanction, tournament)


def _validate_expiry(
    level: SanctionLevel, expires_at: datetime | None, issued_at: datetime
) -> None:
    """PROBATION requires expires_at within MAX_EXPIRY_MONTHS; SUSPENSION's is
    optional but capped the same way."""
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


async def _has_active_dq(tournament_uid: str, user_uid: str) -> bool:
    """True if the player carries an active DQ on this tournament (get_sanctions_
    for_tournament already drops deleted rows, so only lifted needs excluding)."""
    return any(
        s.user_uid == user_uid
        and s.level == SanctionLevel.DISQUALIFICATION
        and s.lifted_at is None
        for s in await get_sanctions_for_tournament(tournament_uid)
    )


async def _dq_restore_state(tournament_uid: str, user_uid: str) -> PlayerState:
    """Call AFTER saving the DQ removal, so it no longer counts. A fat-fingered
    DQ must be fully reversible, not stranded in Finished (withdrawn)."""
    if await _has_active_dq(tournament_uid, user_uid):
        return PlayerState.DISQUALIFIED
    tournament = await get_tournament_by_uid(tournament_uid)
    if tournament is None or tournament.state == TournamentState.FINISHED:
        return PlayerState.FINISHED
    live_tables = [
        table
        for rnd in tournament.rounds
        for table in rnd
        if table.state not in (TableState.FINISHED, TableState.CANCELLED)
    ]
    if tournament.finals is not None and tournament.finals.state != TableState.FINISHED:
        live_tables.append(tournament.finals)
    for table in live_tables:
        if any(seat.player_uid == user_uid for seat in table.seating):
            return PlayerState.PLAYING
    return PlayerState.CHECKED_IN


async def _apply_sanction_to_tournament(
    tournament_uid: str,
    *,
    dq_user_uid: str | None = None,
    dq_state: PlayerState | None = None,
) -> None:
    """One row lock for the whole reflect — two unlocked saves would clobber a
    concurrent /action commit and double-broadcast. DQ state is set before the
    standings recompute (zeroes the player) and re-asserted after in case the
    engine drops it."""
    async with tournament_transaction(tournament_uid) as (tournament, tx_conn):
        if tournament is None:
            return
        changed = False
        if dq_user_uid is not None and dq_state is not None:
            for player in tournament.players:
                if player.user_uid == dq_user_uid:
                    player.state = dq_state
                    changed = True
                    break
        # Same divergence detection as the /action endpoint.
        pre_results = (
            (
                tournament.winner,
                encoder.encode(tournament.standings),
                encoder.encode(tournament.finals),
                encoder.encode(tournament.rounds),
            )
            if tournament.vekn_pushed_at and not tournament.vekn_results_stale
            else None
        )
        if tournament.rounds:
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
            tournament = msgspec.convert(json.loads(result_json), Tournament)
            if dq_user_uid is not None and dq_state is not None:
                for player in tournament.players:
                    if player.user_uid == dq_user_uid:
                        player.state = dq_state
                        break
            changed = True
        if not changed:
            return
        if pre_results is not None and pre_results != (
            tournament.winner,
            encoder.encode(tournament.standings),
            encoder.encode(tournament.finals),
            encoder.encode(tournament.rounds),
        ):
            tournament.vekn_results_stale = True
        tournament.modified = datetime.now(UTC)
        bd = await save_tournament(tournament, conn=tx_conn)
    broadcast_precomputed(bd)


class CreateSanctionRequest(BaseModel):
    user_uid: str
    level: str
    category: str
    subcategory: str | None = None
    round_number: int | None = None
    description: str
    expires_at: str | None = None  # YYYY-MM-DD date string
    tournament_uid: str | None = None


class UpdateSanctionRequest(BaseModel):
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
    http_request: Request,
    current_user: OptionalUser = None,
) -> Response:
    """Only IC and Ethics can issue SUSPENSION and PROBATION outside tournaments."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # The path allowlist cannot see a body, so the tournament match lands here.
    oauth_tournament = getattr(http_request.state, "oauth_tournament", None)
    if oauth_tournament and request.tournament_uid != oauth_tournament:
        raise HTTPException(
            status_code=403,
            detail="This token acts only on the tournament it was granted for",
        )

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

    subcategory = None
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

    round_number = request.round_number
    if level == SanctionLevel.STANDINGS_ADJUSTMENT and round_number is None:
        raise HTTPException(
            status_code=400,
            detail="round_number is required for standings_adjustment sanctions",
        )
    if round_number is not None and request.tournament_uid:
        tournament = await get_tournament_by_uid(request.tournament_uid)
        # len(rounds) is the finals sentinel (same as setTableScore), valid
        # only once a finals table exists.
        if tournament and (
            round_number > len(tournament.rounds)
            or (round_number == len(tournament.rounds) and tournament.finals is None)
        ):
            raise HTTPException(
                status_code=400,
                detail=f"round_number {round_number} exceeds tournament rounds ({len(tournament.rounds)})",
            )

    if not await _can_issue_sanction(current_user, level, request.tournament_uid):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to issue this type of sanction",
        )

    target_user = await get_user_by_uid(request.user_uid)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

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

    # One active DQ per player per tournament: a second is meaningless and, once one
    # is lifted, would strand the player zeroed. Re-DQ after a lift is still allowed.
    if (
        level == SanctionLevel.DISQUALIFICATION
        and request.tournament_uid
        and await _has_active_dq(request.tournament_uid, request.user_uid)
    ):
        raise HTTPException(
            status_code=409,
            detail="Player already has an active disqualification in this tournament",
        )

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

    # A sanction is not a TournamentEvent, so it needs its own recompute call.
    if level == SanctionLevel.DISQUALIFICATION and request.tournament_uid:
        await _apply_sanction_to_tournament(
            request.tournament_uid,
            dq_user_uid=request.user_uid,
            dq_state=PlayerState.DISQUALIFIED,
        )
    elif level == SanctionLevel.STANDINGS_ADJUSTMENT and request.tournament_uid:
        await _apply_sanction_to_tournament(request.tournament_uid)

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
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    sanction = await get_sanction_by_uid(uid)
    if not sanction:
        raise HTTPException(status_code=404, detail="Sanction not found")

    if request.lifted is True and sanction.lifted_at is None:
        if not await _can_lift_sanction(current_user, sanction):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to lift this sanction",
            )

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
        if not permissions.can_modify_sanction(current_user):
            raise HTTPException(
                status_code=403, detail="Only IC or Ethics can modify sanctions"
            )

    now = datetime.now(UTC)
    level = sanction.level
    category = sanction.category
    subcategory = sanction.subcategory
    round_number = sanction.round_number
    description = sanction.description
    expires_at = sanction.expires_at
    lifted_at = sanction.lifted_at
    lifted_by_uid = sanction.lifted_by_uid

    if request.level is not None:
        try:
            level = SanctionLevel(request.level)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid level: {request.level}",
            ) from e

    if request.category is not None:
        try:
            category = SanctionCategory(request.category)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category: {request.category}",
            ) from e

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

    # Mirrors create's sentinel check: else an SA silently no-ops in the engine.
    if request.round_number is not None:
        round_number = request.round_number
        if sanction.tournament_uid is not None:
            tournament = await get_tournament_by_uid(sanction.tournament_uid)
            if tournament and (
                round_number > len(tournament.rounds)
                or (
                    round_number == len(tournament.rounds) and tournament.finals is None
                )
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"round_number {round_number} exceeds tournament rounds ({len(tournament.rounds)})",
                )

    # A resulting SA needs a round_number, e.g. after a DQ→SA edit.
    if level == SanctionLevel.STANDINGS_ADJUSTMENT and round_number is None:
        raise HTTPException(
            status_code=400,
            detail="round_number is required for standings_adjustment sanctions",
        )

    if request.description is not None:
        description = request.description.strip()
        if not description:
            raise HTTPException(status_code=400, detail="Description cannot be empty")

    if request.expires_at is not None:
        try:
            d = date.fromisoformat(request.expires_at)
            expires_at = datetime(d.year, d.month, d.day, tzinfo=UTC)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid expires_at format (expected YYYY-MM-DD): {e}",
            ) from e

    # Runs even on a level-only change, e.g. SUSPENSION→PROBATION must not
    # persist PROBATION with expires_at=None.
    _validate_expiry(level, expires_at, sanction.issued_at)

    if request.lifted is True and sanction.lifted_at is None:
        lifted_at = now
        lifted_by_uid = current_user.uid

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

    # Entering/leaving an active DQ must flip state + recompute below, else a
    # downgraded/lifted DQ stays zeroed forever (the DQ signal is dual).
    was_active_dq = (
        sanction.level == SanctionLevel.DISQUALIFICATION and sanction.lifted_at is None
    )
    is_active_dq = (
        updated.level == SanctionLevel.DISQUALIFICATION and updated.lifted_at is None
    )
    # A level edit can't mint a second active DQ on the same player.
    if (
        is_active_dq
        and not was_active_dq
        and sanction.tournament_uid
        and await _has_active_dq(sanction.tournament_uid, sanction.user_uid)
    ):
        raise HTTPException(
            status_code=409,
            detail="Player already has an active disqualification in this tournament",
        )

    bd = await save_sanction(updated)
    logger.info(f"Sanction {uid} updated by {current_user.uid}")

    if sanction.tournament_uid and was_active_dq != is_active_dq:
        # Covers any new SA level on the row too, hence the elif below.
        await _apply_sanction_to_tournament(
            sanction.tournament_uid,
            dq_user_uid=sanction.user_uid,
            dq_state=(
                PlayerState.DISQUALIFIED
                if is_active_dq
                else await _dq_restore_state(sanction.tournament_uid, sanction.user_uid)
            ),
        )
    elif sanction.tournament_uid and (
        updated.level == SanctionLevel.STANDINGS_ADJUSTMENT
        or sanction.level == SanctionLevel.STANDINGS_ADJUSTMENT
    ):
        await _apply_sanction_to_tournament(sanction.tournament_uid)

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
    """Soft-delete a sanction."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    sanction = await get_sanction_by_uid(uid)
    if not sanction:
        raise HTTPException(status_code=404, detail="Sanction not found")

    if sanction.deleted_at is not None:
        raise HTTPException(status_code=400, detail="Sanction already deleted")

    if not await _can_delete_sanction(current_user, sanction):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to delete this sanction",
        )

    now = datetime.now(UTC)
    updated = msgspec.structs.replace(sanction, modified=now, deleted_at=now)

    bd = await save_sanction(updated)
    logger.info(f"Sanction {uid} soft-deleted by {current_user.uid}")

    # Mirrors the lift path: restores a playable state unless another active
    # DQ still keeps the player zeroed.
    if (
        sanction.level == SanctionLevel.DISQUALIFICATION
        and sanction.lifted_at is None
        and sanction.tournament_uid
    ):
        await _apply_sanction_to_tournament(
            sanction.tournament_uid,
            dq_user_uid=sanction.user_uid,
            dq_state=await _dq_restore_state(
                sanction.tournament_uid, sanction.user_uid
            ),
        )

    if (
        sanction.level == SanctionLevel.STANDINGS_ADJUSTMENT
        and sanction.lifted_at is None
        and sanction.tournament_uid
    ):
        await _apply_sanction_to_tournament(sanction.tournament_uid)

    broadcast_precomputed(bd)

    return Response(
        content=encoder.encode({"message": "Sanction deleted"}),
        media_type="application/json",
    )
