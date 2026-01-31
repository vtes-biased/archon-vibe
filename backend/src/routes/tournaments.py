"""Tournament API endpoints."""

import logging
from datetime import UTC, datetime

import msgspec
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
from uuid6 import uuid7

from ..db import (
    delete_tournament_db,
    get_tournament_by_uid,
    get_user_by_uid,
    insert_tournament,
    update_tournament,
)
from ..models import (
    DeckListsMode,
    Role,
    StandingsMode,
    Tournament,
    TournamentFormat,
    TournamentMinimal,
    TournamentRank,
    TournamentState,
)
from .auth import verify_token

router = APIRouter(prefix="/api/tournaments", tags=["tournaments"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()
decoder = msgspec.json.Decoder(Tournament)

# Broadcast functions will be set by main.py
broadcast_tournament_event = None
broadcast_tournament_delete = None
broadcast_rating_event = None

# Rust engine - lazy loaded
_engine = None


def get_engine():
    """Get the Rust engine instance (lazy loaded)."""
    global _engine
    if _engine is None:
        try:
            from archon_engine import PyEngine

            _engine = PyEngine()
            logger.info("Rust tournament engine loaded")
        except ImportError:
            logger.warning("archon_engine not available, tournament actions disabled")
            raise HTTPException(
                status_code=503, detail="Tournament engine not available"
            )
    return _engine


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


def _is_organizer(user, tournament: Tournament) -> bool:
    """Check if user is an organizer of this tournament."""
    return user.uid in tournament.organizers_uids


def _can_manage_tournaments(user) -> bool:
    """Check if user can create/manage tournaments."""
    return any(r in user.roles for r in (Role.IC, Role.NC, Role.PRINCE))


def _tournament_to_minimal(t: Tournament) -> TournamentMinimal:
    """Strip tournament to minimal public data for SSE streaming."""
    return TournamentMinimal(
        uid=t.uid,
        modified=t.modified,
        name=t.name,
        format=t.format,
        rank=t.rank,
        online=t.online,
        start=t.start,
        finish=t.finish,
        timezone=t.timezone,
        country=t.country,
        league_uid=t.league_uid,
        state=t.state,
    )


def _strip_for_player(t: Tournament, user_uid: str) -> dict:
    """Strip tournament data for a registered player (hide other players' details)."""
    data = msgspec.to_builtins(t)
    # Players can see config but not other players' decks
    player_decks = data.get("decks", {}).get(user_uid, [])
    data["decks"] = {user_uid: player_decks} if player_decks else {}
    return data


class CreateTournamentRequest(BaseModel):
    name: str
    format: str = "Standard"
    rank: str = ""
    online: bool = False
    start: str | None = None
    finish: str | None = None
    timezone: str = "UTC"
    country: str | None = None
    venue: str = ""
    venue_url: str = ""
    address: str = ""
    map_url: str = ""
    proxies: bool = False
    multideck: bool = False
    decklist_required: bool = False
    description: str = ""
    standings_mode: str = "Private"
    decklists_mode: str = "Winner"
    max_rounds: int = 0


class UpdateTournamentRequest(BaseModel):
    name: str | None = None
    format: str | None = None
    rank: str | None = None
    online: bool | None = None
    start: str | None = None
    finish: str | None = None
    timezone: str | None = None
    country: str | None = None
    venue: str | None = None
    venue_url: str | None = None
    address: str | None = None
    map_url: str | None = None
    proxies: bool | None = None
    multideck: bool | None = None
    decklist_required: bool | None = None
    description: str | None = None
    standings_mode: str | None = None
    decklists_mode: str | None = None
    max_rounds: int | None = None


def _parse_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


@router.post("/", status_code=201)
async def create_tournament(
    request: CreateTournamentRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Create a new tournament."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not _can_manage_tournaments(current_user):
        raise HTTPException(
            status_code=403, detail="Only IC, NC, or Prince can create tournaments"
        )

    try:
        fmt = TournamentFormat(request.format)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid format: {request.format}"
        ) from e

    try:
        rank = TournamentRank(request.rank)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid rank: {request.rank}"
        ) from e

    try:
        standings = StandingsMode(request.standings_mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid standings_mode") from e

    try:
        decklists = DeckListsMode(request.decklists_mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid decklists_mode") from e

    now = datetime.now(UTC)
    tournament = Tournament(
        uid=str(uuid7()),
        modified=now,
        name=request.name,
        format=fmt,
        rank=rank,
        online=request.online,
        start=_parse_datetime(request.start),
        finish=_parse_datetime(request.finish),
        timezone=request.timezone,
        country=request.country,
        venue=request.venue,
        venue_url=request.venue_url,
        address=request.address,
        map_url=request.map_url,
        proxies=request.proxies,
        multideck=request.multideck,
        decklist_required=request.decklist_required,
        description=request.description,
        standings_mode=standings,
        decklists_mode=decklists,
        max_rounds=request.max_rounds,
        organizers_uids=[current_user.uid],
    )

    await insert_tournament(tournament)
    logger.info(f"Tournament {tournament.uid} created by {current_user.uid}")

    if broadcast_tournament_event:
        await broadcast_tournament_event(tournament)

    return Response(
        content=encoder.encode(tournament),
        media_type="application/json",
        status_code=201,
    )


@router.get("/{uid}")
async def get_tournament(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Get a tournament by UID.

    Organizers get full data. Registered players get filtered data.
    Unauthenticated users get minimal data.
    """
    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    current_user = await _get_current_user(authorization)

    # Organizers get full tournament
    if current_user and _is_organizer(current_user, tournament):
        return Response(
            content=encoder.encode(tournament),
            media_type="application/json",
        )

    # ICs get full access to all tournaments
    if current_user and Role.IC in current_user.roles:
        return Response(
            content=encoder.encode(tournament),
            media_type="application/json",
        )

    # NCs get full access to tournaments in their country
    if current_user and Role.NC in current_user.roles and current_user.country and tournament.country == current_user.country:
        return Response(
            content=encoder.encode(tournament),
            media_type="application/json",
        )

    # Registered players get filtered view (hide other players' decks)
    if current_user:
        player_uids = {p.user_uid for p in tournament.players if p.user_uid}
        if current_user.uid in player_uids:
            data = _strip_for_player(tournament, current_user.uid)
            return Response(
                content=encoder.encode(data),
                media_type="application/json",
            )

    # Members (users with vekn_id) see full data for finished tournaments
    if current_user and current_user.vekn_id and tournament.state == TournamentState.FINISHED:
        return Response(
            content=encoder.encode(tournament),
            media_type="application/json",
        )

    # Public / non-member users: minimal data
    minimal = _tournament_to_minimal(tournament)
    return Response(
        content=encoder.encode(minimal),
        media_type="application/json",
    )


@router.put("/{uid}")
async def update_tournament_endpoint(
    uid: str,
    request: UpdateTournamentRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Update tournament config (organizers only)."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not _is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can update this tournament"
        )

    # Validate max_rounds: must be 0 (unlimited) or >= completed rounds
    if request.max_rounds is not None and request.max_rounds != 0:
        completed_rounds = len(tournament.rounds)
        if tournament.state == TournamentState.PLAYING:
            # Current round is in progress, don't count it
            completed_rounds = max(0, completed_rounds - 1)
        if request.max_rounds < completed_rounds:
            raise HTTPException(
                status_code=400,
                detail=f"max_rounds ({request.max_rounds}) cannot be less than completed rounds ({completed_rounds})",
            )

    # Apply updates via dict merge
    data = msgspec.to_builtins(tournament)
    updates = request.model_dump(exclude_none=True)

    # Validate enums if provided
    if "format" in updates:
        try:
            updates["format"] = TournamentFormat(updates["format"]).value
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid format") from e
    if "rank" in updates:
        try:
            updates["rank"] = TournamentRank(updates["rank"]).value
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid rank") from e
    if "standings_mode" in updates:
        try:
            updates["standings_mode"] = StandingsMode(updates["standings_mode"]).value
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid standings_mode") from e
    if "decklists_mode" in updates:
        try:
            updates["decklists_mode"] = DeckListsMode(updates["decklists_mode"]).value
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid decklists_mode") from e

    # Parse datetime strings
    if "start" in updates and updates["start"]:
        updates["start"] = _parse_datetime(updates["start"])
    if "finish" in updates and updates["finish"]:
        updates["finish"] = _parse_datetime(updates["finish"])

    data.update(updates)
    data["modified"] = datetime.now(UTC)

    updated = msgspec.convert(data, Tournament)
    await update_tournament(updated)

    if broadcast_tournament_event:
        await broadcast_tournament_event(updated)

    return Response(
        content=encoder.encode(updated),
        media_type="application/json",
    )


@router.delete("/{uid}")
async def delete_tournament_endpoint(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Delete a tournament (organizers only, PLANNED state only)."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not _is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can delete this tournament"
        )

    if tournament.state != TournamentState.PLANNED:
        raise HTTPException(
            status_code=400,
            detail="Can only delete tournaments in Planned state",
        )

    await delete_tournament_db(uid)
    logger.info(f"Tournament {uid} deleted by {current_user.uid}")

    if broadcast_tournament_delete:
        await broadcast_tournament_delete(uid)

    return Response(
        content=encoder.encode({"message": "Tournament deleted"}),
        media_type="application/json",
    )


# --- Tournament Action Endpoint (Rust Engine) ---


class TournamentActionRequest(BaseModel):
    """Request body for tournament actions processed by Rust engine."""

    type: str  # Event type: OpenRegistration, Register, CheckIn, StartRound, etc.
    user_uid: str | None = None  # For Register, AddPlayer, RemovePlayer
    player_uid: str | None = None  # For CheckIn
    round: int | None = None  # For SetScore, SwapSeats
    table: int | None = None  # For SetScore
    table1: int | None = None  # For SwapSeats
    seat1: int | None = None  # For SwapSeats
    table2: int | None = None  # For SwapSeats
    seat2: int | None = None  # For SwapSeats
    seat: int | None = None  # For SeatPlayer
    scores: list[dict] | None = None  # For SetScore: [{player_uid, vp}]
    comment: str | None = None  # For Override
    toss: int | None = None  # For SetToss


@router.post("/{uid}/action")
async def tournament_action(
    uid: str,
    request: TournamentActionRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Process a tournament event via the Rust engine.

    All tournament state mutations go through this endpoint, which delegates
    to the Rust engine for consistent behavior in online/offline modes.
    """
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Build event JSON for Rust engine
    event_data = {"type": request.type}
    if request.user_uid:
        event_data["user_uid"] = request.user_uid
    if request.player_uid:
        event_data["player_uid"] = request.player_uid
    if request.round is not None:
        event_data["round"] = request.round
    if request.table is not None:
        event_data["table"] = request.table
    if request.table1 is not None:
        event_data["table1"] = request.table1
    if request.seat1 is not None:
        event_data["seat1"] = request.seat1
    if request.table2 is not None:
        event_data["table2"] = request.table2
    if request.seat2 is not None:
        event_data["seat2"] = request.seat2
    if request.seat is not None:
        event_data["seat"] = request.seat
    if request.scores:
        event_data["scores"] = request.scores
    if request.comment:
        event_data["comment"] = request.comment
    if request.toss is not None:
        event_data["toss"] = request.toss

    # Build actor context for Rust engine
    actor_data = {
        "uid": current_user.uid,
        "roles": [r.value if hasattr(r, "value") else str(r) for r in current_user.roles],
        "is_organizer": _is_organizer(current_user, tournament),
    }

    # Serialize tournament to JSON for engine
    tournament_json = encoder.encode(tournament).decode("utf-8")
    event_json = msgspec.json.encode(event_data).decode("utf-8")
    actor_json = msgspec.json.encode(actor_data).decode("utf-8")

    # Call Rust engine
    engine = get_engine()
    try:
        result_json = engine.process_tournament_event(
            tournament_json, event_json, actor_json
        )
    except ValueError as e:
        # Rust engine returns validation errors as ValueError
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Parse result and update timestamp
    updated = decoder.decode(result_json.encode("utf-8"))
    updated.modified = datetime.now(UTC)

    # Save to database
    await update_tournament(updated)
    logger.info(f"Tournament {uid} action {request.type} by {current_user.uid}")

    if broadcast_tournament_event:
        await broadcast_tournament_event(updated)

    # Recompute ratings when tournament enters or leaves Finished state
    was_finished = tournament.state == TournamentState.FINISHED
    is_finished = updated.state == TournamentState.FINISHED
    if was_finished != is_finished:
        try:
            from ..ratings import recompute_ratings_for_players

            player_uids = {p.user_uid for p in tournament.players if p.user_uid}
            # Get category from the pre-change tournament (format/online don't change)
            from ..ratings import _rating_category_for_tournament

            category = _rating_category_for_tournament(tournament)
            ratings = await recompute_ratings_for_players(player_uids, category)
            if broadcast_rating_event:
                for rating in ratings:
                    await broadcast_rating_event(rating)
        except Exception as e:
            logger.error(f"Error recomputing ratings for {uid}: {e}", exc_info=True)

    return Response(
        content=encoder.encode(updated),
        media_type="application/json",
    )


# --- Legacy action endpoints (kept for backward compatibility, delegate to /action) ---


@router.post("/{uid}/open-registration")
async def open_registration(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Open registration (PLANNED → REGISTRATION)."""
    return await tournament_action(
        uid, TournamentActionRequest(type="OpenRegistration"), authorization
    )


@router.post("/{uid}/register")
async def register_player(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Player self-registration."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return await tournament_action(
        uid,
        TournamentActionRequest(type="Register", user_uid=current_user.uid),
        authorization,
    )


@router.post("/{uid}/unregister")
async def unregister_player(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Player self-unregistration."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return await tournament_action(
        uid,
        TournamentActionRequest(type="Unregister", user_uid=current_user.uid),
        authorization,
    )


class AddPlayerRequest(BaseModel):
    user_uid: str


@router.post("/{uid}/add-player")
async def add_player(
    uid: str,
    request: AddPlayerRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Organizer adds a player."""
    return await tournament_action(
        uid,
        TournamentActionRequest(type="AddPlayer", user_uid=request.user_uid),
        authorization,
    )


@router.post("/{uid}/remove-player")
async def remove_player(
    uid: str,
    request: AddPlayerRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Organizer removes a player."""
    return await tournament_action(
        uid,
        TournamentActionRequest(type="RemovePlayer", user_uid=request.user_uid),
        authorization,
    )


@router.post("/{uid}/close-registration")
async def close_registration(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Close registration and start check-in (REGISTRATION → WAITING)."""
    return await tournament_action(
        uid, TournamentActionRequest(type="CloseRegistration"), authorization
    )


class CheckinRequest(BaseModel):
    player_uid: str


@router.post("/{uid}/checkin")
async def checkin_player(
    uid: str,
    request: CheckinRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Check in a player (organizer)."""
    return await tournament_action(
        uid,
        TournamentActionRequest(type="CheckIn", player_uid=request.player_uid),
        authorization,
    )


@router.post("/{uid}/checkin-all")
async def checkin_all(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Check in all registered players."""
    return await tournament_action(
        uid, TournamentActionRequest(type="CheckInAll"), authorization
    )


@router.post("/{uid}/rounds/start")
async def start_round(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Start the next round (WAITING → PLAYING)."""
    return await tournament_action(
        uid, TournamentActionRequest(type="StartRound"), authorization
    )


class SetScoreRequest(BaseModel):
    scores: list[dict]  # [{player_uid, vp}]


@router.put("/{uid}/rounds/{round_num}/tables/{table_num}/score")
async def set_table_score(
    uid: str,
    round_num: int,
    table_num: int,
    request: SetScoreRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Set scores for a table."""
    return await tournament_action(
        uid,
        TournamentActionRequest(
            type="SetScore",
            round=round_num,
            table=table_num,
            scores=request.scores,
        ),
        authorization,
    )


@router.post("/{uid}/rounds/finish")
async def finish_round(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Finish current round (PLAYING → WAITING)."""
    return await tournament_action(
        uid, TournamentActionRequest(type="FinishRound"), authorization
    )


@router.post("/{uid}/rounds/cancel")
async def cancel_round(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Cancel the current round and return to check-in (PLAYING → WAITING)."""
    return await tournament_action(
        uid, TournamentActionRequest(type="CancelRound"), authorization
    )


class SwapSeatsRequest(BaseModel):
    round: int
    table1: int
    seat1: int
    table2: int
    seat2: int


@router.post("/{uid}/rounds/swap-seats")
async def swap_seats(
    uid: str,
    request: SwapSeatsRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Swap two players' seats in the current round."""
    return await tournament_action(
        uid,
        TournamentActionRequest(
            type="SwapSeats",
            round=request.round,
            table1=request.table1,
            seat1=request.seat1,
            table2=request.table2,
            seat2=request.seat2,
        ),
        authorization,
    )


class SeatPlayerRequest(BaseModel):
    player_uid: str
    table: int
    seat: int


@router.post("/{uid}/seat-player")
async def seat_player(
    uid: str,
    request: SeatPlayerRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Seat a registered player at a specific table and seat position."""
    return await tournament_action(
        uid,
        TournamentActionRequest(
            type="SeatPlayer",
            player_uid=request.player_uid,
            table=request.table,
            seat=request.seat,
        ),
        authorization,
    )


class UnseatPlayerRequest(BaseModel):
    player_uid: str


@router.post("/{uid}/unseat-player")
async def unseat_player(
    uid: str,
    request: UnseatPlayerRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Remove a player from their seat in the current round."""
    return await tournament_action(
        uid,
        TournamentActionRequest(type="UnseatPlayer", player_uid=request.player_uid),
        authorization,
    )


class RemoveTableRequest(BaseModel):
    table: int


@router.post("/{uid}/rounds/remove-table")
async def remove_table(
    uid: str,
    request: RemoveTableRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Remove an empty table from the current round."""
    return await tournament_action(
        uid,
        TournamentActionRequest(type="RemoveTable", table=request.table),
        authorization,
    )


@router.post("/{uid}/rounds/add-table")
async def add_table(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Add an empty table to the current round."""
    return await tournament_action(
        uid, TournamentActionRequest(type="AddTable"), authorization
    )


class DropOutRequest(BaseModel):
    player_uid: str


@router.post("/{uid}/dropout")
async def dropout_player(
    uid: str,
    request: DropOutRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Drop a player out of the tournament."""
    return await tournament_action(
        uid,
        TournamentActionRequest(type="DropOut", player_uid=request.player_uid),
        authorization,
    )


@router.post("/{uid}/reset-checkin")
async def reset_checkin(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Reset all checked-in players back to registered."""
    return await tournament_action(
        uid, TournamentActionRequest(type="ResetCheckIn"), authorization
    )


@router.post("/{uid}/finish")
async def finish_tournament(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Finish the tournament (→ FINISHED)."""
    return await tournament_action(
        uid, TournamentActionRequest(type="FinishTournament"), authorization
    )


@router.post("/{uid}/cancel-registration")
async def cancel_registration(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Cancel registration (REGISTRATION → PLANNED)."""
    return await tournament_action(
        uid, TournamentActionRequest(type="CancelRegistration"), authorization
    )


@router.post("/{uid}/reopen-registration")
async def reopen_registration(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Reopen registration (WAITING → REGISTRATION)."""
    return await tournament_action(
        uid, TournamentActionRequest(type="ReopenRegistration"), authorization
    )


@router.post("/{uid}/reopen")
async def reopen_tournament(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Reopen tournament (FINISHED → WAITING)."""
    return await tournament_action(
        uid, TournamentActionRequest(type="ReopenTournament"), authorization
    )
