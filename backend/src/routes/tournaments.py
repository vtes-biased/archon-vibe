"""Tournament API endpoints."""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import msgspec
from archon_engine import PyEngine
from fastapi import APIRouter, Header, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from uuid6 import uuid7

from ..db import (
    BroadcastData,
    get_auth_method_by_identifier,
    get_decks_for_tournament,
    get_sanctions_for_tournament,
    get_sanctions_for_user,
    get_tournament_by_uid,
    get_user_by_uid,
    get_user_by_vekn_id,
    insert_sanction,
    insert_tournament,
    insert_user,
    save_object,
    save_object_from_model,
    soft_delete_tournament,
    tournament_transaction,
    update_tournament,
)
from ..models import (
    DeckListsMode,
    DeckObject,
    ObjectType,
    Role,
    Sanction,
    SanctionLevel,
    StandingsMode,
    TimeExtensionPolicy,
    TimerState,
    Tournament,
    TournamentFormat,
    TournamentMinimal,
    TournamentRank,
    TournamentState,
    User,
)
from .auth import verify_token

router = APIRouter(prefix="/api/tournaments", tags=["tournaments"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()
decoder = msgspec.json.Decoder(Tournament)

# Broadcast functions will be set by main.py
broadcast_tournament_event = None
broadcast_user_event = None
broadcast_sanction_event = None
broadcast_deck_event = None  # async fn(deck_uid: str) -> None

_engine = PyEngine()


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
    """Check if user is an organizer of this tournament (IC is implicit organizer)."""
    return user.uid in tournament.organizers_uids or Role.IC in user.roles


async def _build_decks_json(tournament_uid: str) -> str:
    """Build deck metadata JSON for the engine's decks parameter."""
    decks = await get_decks_for_tournament(tournament_uid)
    return msgspec.json.encode(
        [{"user_uid": d.user_uid, "round": d.round, "uid": d.uid} for d in decks]
    ).decode()


async def _process_deck_ops(
    deck_ops: list,
    tournament_uid: str,
    existing_decks: list[DeckObject] | None = None,
) -> list[BroadcastData]:
    """Process deck_ops from engine result. Returns BroadcastData for each affected deck."""
    if not deck_ops:
        return []
    if existing_decks is None:
        existing_decks = await get_decks_for_tournament(tournament_uid)

    affected: list[BroadcastData] = []
    for op in deck_ops:
        op_type = op.get("op")
        if op_type == "upsert":
            deck_data = op["deck"]
            player_uid = op["player_uid"]
            round_val = deck_data.get("round")
            # Find existing deck for this (tournament, player, round)
            existing = next(
                (
                    d
                    for d in existing_decks
                    if d.user_uid == player_uid and d.round == round_val
                ),
                None,
            )
            if existing:
                deck_obj = existing
                deck_obj.modified = datetime.now(UTC)
            else:
                deck_obj = DeckObject(
                    uid=str(uuid7()),
                    modified=datetime.now(UTC),
                    tournament_uid=tournament_uid,
                    user_uid=player_uid,
                )
            deck_obj.round = round_val
            deck_obj.name = deck_data.get("name", "")
            deck_obj.author = deck_data.get("author", "")
            deck_obj.comments = deck_data.get("comments", "")
            deck_obj.cards = deck_data.get("cards", {})
            deck_obj.attribution = deck_data.get("attribution")
            deck_obj.public = deck_data.get("public", False)
            bd = await save_object_from_model(ObjectType.DECK, deck_obj)
            affected.append(bd)

        elif op_type == "delete":
            player_uid = op["player_uid"]
            for d in existing_decks:
                if d.user_uid == player_uid:
                    d.deleted_at = datetime.now(UTC)
                    d.modified = datetime.now(UTC)
                    bd = await save_object_from_model(ObjectType.DECK, d)
                    affected.append(bd)

        elif op_type == "set_public":
            deck_uid = op.get("deck_uid")
            public_val = op.get("public", False)
            target = next((d for d in existing_decks if d.uid == deck_uid), None)
            if target:
                target.public = public_val
                target.modified = datetime.now(UTC)
                bd = await save_object_from_model(ObjectType.DECK, target)
                affected.append(bd)

    return affected


async def _maybe_push_vekn(tournament: Tournament) -> None:
    """Push tournament results to VEKN if VEKN_PUSH is enabled."""
    if os.getenv("VEKN_PUSH", "").lower() != "true":
        return
    try:
        from ..vekn_api import VEKNAPIClient
        from ..vekn_push import push_tournament_results

        client = VEKNAPIClient()
        try:
            await push_tournament_results(client, tournament)
        finally:
            await client.close()
    except Exception:
        logger.exception("Failed to push VEKN results")


async def _maybe_push_vekn_event(tournament: Tournament) -> None:
    """Create VEKN calendar event if VEKN_PUSH is enabled."""
    if os.getenv("VEKN_PUSH", "").lower() != "true":
        return
    try:
        from ..vekn_api import VEKNAPIClient
        from ..vekn_push import push_tournament_event

        client = VEKNAPIClient()
        try:
            await push_tournament_event(client, tournament)
        finally:
            await client.close()
    except Exception:
        logger.exception("Failed to push VEKN event")


async def _maybe_submit_twda(tournament: Tournament) -> None:
    """Submit winner's deck to TWDA if conditions are met.

    Conditions: sanctioned tournament, finished, winner has deck, has VEKN event ID.
    """
    if tournament.state != TournamentState.FINISHED:
        return
    if not tournament.winner:
        return
    if tournament.rank == TournamentRank.BASIC:
        return  # unsanctioned
    vekn_event_id = tournament.external_ids.get("vekn")
    if not vekn_event_id:
        return

    # Find winner's deck from DeckObject store
    decks = await get_decks_for_tournament(tournament.uid)
    winner_deck = next((d for d in decks if d.user_uid == tournament.winner), None)
    if not winner_deck:
        return

    try:
        import json as json_mod

        from ..twda import submit_twda_pr

        engine = _engine
        deck_json = json_mod.dumps(
            {
                "name": winner_deck.name,
                "author": winner_deck.author,
                "comments": winner_deck.comments,
                "cards": winner_deck.cards,
            }
        )

        player_user = await get_user_by_uid(tournament.winner)
        player_name = player_user.name if player_user else "Unknown"
        player_count = len(tournament.players)
        tournament_date = tournament.start or tournament.modified.isoformat()
        rounds_count = len(tournament.rounds)
        has_finals = tournament.finals is not None
        tournament_format = f"{rounds_count}R" + ("+F" if has_finals else "")

        deck_text = engine.export_twda(
            deck_json,
            _load_cards_json(),
            tournament.name,
            str(tournament_date),
            tournament.country or "",
            tournament_format,
            "",  # tournament_url
            player_count,
            player_name,
        )

        await submit_twda_pr(vekn_event_id, deck_text, tournament.name)
    except Exception:
        logger.exception("Failed to submit TWDA PR")


def _build_actor_context(user, tournament: Tournament) -> dict:
    """Build actor context dict for the Rust engine."""
    return {
        "uid": user.uid,
        "roles": [r.value if hasattr(r, "value") else str(r) for r in user.roles],
        "is_organizer": _is_organizer(user, tournament),
    }


def _can_manage_tournaments(user) -> bool:
    """Check if user can create/manage tournaments."""
    return any(r in user.roles for r in (Role.IC, Role.NC, Role.PRINCE))


async def _check_player_barred(
    player_uid: str, tournament_uid: str, tournament: Tournament
) -> None:
    """Check if a player is barred from checking in (cross-tournament sanctions).

    Raises HTTPException(400) if:
    - Player has an active suspension
    - Player is DQ'd in a sibling league tournament (league-wide DQ)
    """
    from datetime import UTC, datetime

    # Check active suspensions
    user_sanctions = await get_sanctions_for_user(player_uid)
    now = datetime.now(UTC)
    for s in user_sanctions:
        if s.deleted_at or s.lifted_at:
            continue
        if s.level == SanctionLevel.SUSPENSION:
            if s.expires_at is None or s.expires_at > now:
                raise HTTPException(
                    status_code=400, detail="Player is suspended and cannot check in"
                )

    # Check league-wide DQ (only if tournament is in a league)
    if tournament.league_uid:
        for s in user_sanctions:
            if s.deleted_at or s.lifted_at:
                continue
            if s.level == SanctionLevel.DISQUALIFICATION and s.tournament_uid:
                # Check if the DQ sanction's tournament is in the same league
                dq_tournament = await get_tournament_by_uid(s.tournament_uid)
                if dq_tournament and dq_tournament.league_uid == tournament.league_uid:
                    raise HTTPException(
                        status_code=400,
                        detail="Player is disqualified from a league tournament and cannot check in",
                    )


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


class OrganizerAction(BaseModel):
    user_uid: str


@router.post("/{uid}/organizers")
async def add_organizer(
    uid: str,
    body: OrganizerAction,
    authorization: str | None = Header(default=None),
) -> Response:
    """Add an organizer to a tournament."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not _is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can manage organizers"
        )

    if body.user_uid not in tournament.organizers_uids:
        tournament.organizers_uids.append(body.user_uid)
        tournament.modified = datetime.now(UTC)
        bd = await update_tournament(tournament)
        if broadcast_tournament_event:
            broadcast_tournament_event(bd)

    return Response(
        content=encoder.encode(tournament),
        media_type="application/json",
    )


@router.delete("/{uid}/organizers/{organizer_uid}")
async def remove_organizer(
    uid: str,
    organizer_uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Remove an organizer from a tournament."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not _is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can manage organizers"
        )

    if organizer_uid in tournament.organizers_uids:
        if len(tournament.organizers_uids) <= 1:
            raise HTTPException(
                status_code=400, detail="Cannot remove the last organizer"
            )
        tournament.organizers_uids.remove(organizer_uid)
        tournament.modified = datetime.now(UTC)
        bd = await update_tournament(tournament)
        if broadcast_tournament_event:
            broadcast_tournament_event(bd)

    return Response(
        content=encoder.encode(tournament),
        media_type="application/json",
    )


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
    league_uid: str | None = None


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

    # VEKN_PUSH: validate max_rounds is 2-4
    vekn_push = os.getenv("VEKN_PUSH", "").lower() == "true"
    if vekn_push:
        if request.max_rounds < 2 or request.max_rounds > 4:
            raise HTTPException(
                status_code=400,
                detail="max_rounds must be 2, 3, or 4 when VEKN push is enabled",
            )

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
        league_uid=request.league_uid or None,
        organizers_uids=[current_user.uid],
    )

    bd = await insert_tournament(tournament)
    logger.info(f"Tournament {tournament.uid} created by {current_user.uid}")

    if broadcast_tournament_event:
        broadcast_tournament_event(bd)

    # VEKN push: create calendar event
    await _maybe_push_vekn_event(tournament)

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
    if (
        current_user
        and Role.NC in current_user.roles
        and current_user.country
        and tournament.country == current_user.country
    ):
        return Response(
            content=encoder.encode(tournament),
            media_type="application/json",
        )

    # Registered players see full tournament data (decks are separate objects)
    if current_user:
        player_uids = {p.user_uid for p in tournament.players if p.user_uid}
        if current_user.uid in player_uids:
            return Response(
                content=encoder.encode(tournament),
                media_type="application/json",
            )

    # Members (users with vekn_id) see full data for finished tournaments
    if (
        current_user
        and current_user.vekn_id
        and tournament.state == TournamentState.FINISHED
    ):
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

    result = await soft_delete_tournament(uid)
    logger.info(f"Tournament {uid} soft-deleted by {current_user.uid}")

    if result and broadcast_tournament_event:
        broadcast_tournament_event(result[1])

    return Response(
        content=encoder.encode({"message": "Tournament deleted"}),
        media_type="application/json",
    )


# --- Archon Import Endpoints ---


@router.get("/archon-template")
async def download_archon_template() -> FileResponse:
    """Serve blank Archon v1.5l spreadsheet template. Public access."""
    path = Path(__file__).parent.parent.parent / "data" / "thearchon1.5l.xlsx"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Template file not found")
    return FileResponse(
        path,
        filename="thearchon1.5l.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/{uid}/archon-import")
async def archon_import(
    uid: str,
    file: UploadFile,
    authorization: str | None = Header(default=None),
) -> Response:
    """Import a filled-in Archon v1.5l spreadsheet into an existing tournament."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Auth: organizer, IC, or NC/Prince of same country
    if not (
        _is_organizer(current_user, tournament)
        or Role.NC in current_user.roles
        and current_user.country
        and tournament.country == current_user.country
    ):
        raise HTTPException(
            status_code=403,
            detail="Only organizers, IC, or NC/Prince of the same country can import",
        )

    # File validation
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be an .xlsx spreadsheet")

    file_bytes = await file.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    from ..archon_import import (
        apply_archon_import,
        parse_archon_file,
        validate_archon_import,
    )

    # Parse
    try:
        data = parse_archon_file(file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to parse spreadsheet: {e}"
        ) from e

    # Validate
    engine = _engine
    errors = validate_archon_import(data, engine)
    if errors:
        return Response(
            content=msgspec.json.encode(
                {
                    "success": False,
                    "errors": errors,
                    "warnings": [],
                    "players_matched": 0,
                    "rounds_imported": 0,
                    "has_finals": False,
                }
            ).decode(),
            media_type="application/json",
            status_code=400,
        )

    # Apply
    result = await apply_archon_import(
        tournament_uid=uid,
        data=data,
        actor_uid=current_user.uid,
        engine=engine,
        broadcast_tournament_event=broadcast_tournament_event,
        broadcast_user_event=broadcast_user_event,
    )

    status = 200 if result.success else 400
    return Response(
        content=msgspec.json.encode(
            {
                "success": result.success,
                "errors": result.errors,
                "warnings": result.warnings,
                "players_matched": result.players_matched,
                "rounds_imported": result.rounds_imported,
                "has_finals": result.has_finals,
            }
        ).decode(),
        media_type="application/json",
        status_code=status,
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
    status: str | None = None  # For SetPaymentStatus
    seating: list[list[str]] | None = None  # For AlterSeating
    config: dict | None = None  # For UpdateConfig: partial config fields
    # Deck
    deck: dict | None = None
    multideck: bool | None = None
    # Raffle
    label: str | None = None
    pool: str | None = None
    exclude_drawn: bool | None = None
    count: int | None = None
    seed: int | None = None


@router.post("/{uid}/action")
async def tournament_action(
    uid: str,
    request: TournamentActionRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Process a tournament event via the Rust engine.

    All tournament state mutations go through this endpoint, which delegates
    to the Rust engine for consistent behavior in online/offline modes.

    Uses SELECT ... FOR UPDATE to serialize concurrent writes per tournament,
    preventing lost updates when multiple actions arrive simultaneously.
    """
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Build event data outside the transaction (no DB needed)
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
    if request.status:
        event_data["status"] = request.status
    if request.seating:
        event_data["seating"] = request.seating
    if request.config is not None:
        event_data["config"] = request.config
    if request.deck is not None:
        event_data["deck"] = request.deck
    if request.multideck is not None:
        event_data["multideck"] = request.multideck
    if request.label:
        event_data["label"] = request.label
    if request.pool:
        event_data["pool"] = request.pool
    if request.exclude_drawn is not None:
        event_data["exclude_drawn"] = request.exclude_drawn
    if request.count is not None:
        event_data["count"] = request.count
    if request.seed is not None:
        event_data["seed"] = request.seed

    # SELECT FOR UPDATE: serialize concurrent writes to this tournament
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")

        # VEKN_PUSH: max_rounds immutable once pushed to VEKN
        if (
            request.type == "UpdateConfig"
            and request.config
            and "max_rounds" in request.config
        ):
            if tournament.external_ids.get("vekn"):
                if request.config["max_rounds"] != tournament.max_rounds:
                    raise HTTPException(
                        status_code=409,
                        detail="max_rounds cannot be changed after tournament is pushed to VEKN",
                    )
            vekn_push = os.getenv("VEKN_PUSH", "").lower() == "true"
            if vekn_push and request.config["max_rounds"] is not None:
                mr = request.config["max_rounds"]
                if mr != 0 and (mr < 2 or mr > 4):
                    raise HTTPException(
                        status_code=400,
                        detail="max_rounds must be 2, 3, or 4 when VEKN push is enabled",
                    )

        # Reject actions on offline-locked tournaments
        if tournament.offline_mode:
            raise HTTPException(
                status_code=423,
                detail="Tournament is in offline mode on another device",
            )

        # Build actor context for Rust engine
        actor_data = _build_actor_context(current_user, tournament)

        # Fetch sanctions for this tournament
        tournament_sanctions = await get_sanctions_for_tournament(uid)
        sanctions_data = [
            {
                "user_uid": s.user_uid,
                "level": s.level.value,
                "round_number": s.round_number,
                "lifted_at": s.lifted_at.isoformat() if s.lifted_at else None,
                "deleted_at": s.deleted_at.isoformat() if s.deleted_at else None,
            }
            for s in tournament_sanctions
        ]

        # Serialize tournament to JSON for engine
        tournament_json = encoder.encode(tournament).decode("utf-8")
        event_json = msgspec.json.encode(event_data).decode("utf-8")
        actor_json = msgspec.json.encode(actor_data).decode("utf-8")
        sanctions_json = msgspec.json.encode(sanctions_data).decode("utf-8")
        decks_json = await _build_decks_json(uid)

        # Backend pre-checks for cross-tournament sanctions (CheckIn)
        if request.type == "CheckIn" and request.player_uid:
            await _check_player_barred(request.player_uid, uid, tournament)

        # Call Rust engine
        engine = _engine
        try:
            result_json = engine.process_tournament_event(
                tournament_json, event_json, actor_json, sanctions_json, decks_json
            )
        except ValueError as e:
            # Rust engine returns validation errors as ValueError
            raise HTTPException(status_code=400, detail=str(e)) from e

        # Parse new result format: {"tournament": {...}, "deck_ops": [...]}
        import json as json_mod

        result = json_mod.loads(result_json)
        updated = decoder.decode(msgspec.json.encode(result["tournament"]))
        updated.modified = datetime.now(UTC)
        deck_ops = result.get("deck_ops", [])

        # Timer lifecycle hooks (online-only, not handled by Rust engine)
        if request.type in ("StartRound", "StartFinals"):
            updated.timer = TimerState()  # Fresh paused timer
            updated.table_extra_time = {}
            updated.table_paused_at = {}
        elif request.type in ("FinishRound", "CancelRound", "FinishTournament"):
            if not updated.timer.paused and updated.timer.started_at:
                # Accumulate elapsed time before pausing
                elapsed = (datetime.now(UTC) - updated.timer.started_at).total_seconds()
                updated.timer = TimerState(
                    elapsed_before_pause=updated.timer.elapsed_before_pause + elapsed,
                    paused=True,
                )
            updated.table_extra_time = {}
            updated.table_paused_at = {}

        # Save within the same transaction (row is still locked)
        tournament_bd = await save_object(
            ObjectType.TOURNAMENT,
            updated.uid,
            msgspec.to_builtins(updated),
            conn=tx_conn,
        )
        pre_state = tournament.state

    # --- Transaction committed, row lock released ---
    logger.info(f"Tournament {uid} action {request.type} by {current_user.uid}")

    # Process deck side-effects (outside transaction)
    deck_bds = await _process_deck_ops(deck_ops, uid)
    if broadcast_deck_event:
        for bd in deck_bds:
            broadcast_deck_event(bd)

    if broadcast_tournament_event:
        broadcast_tournament_event(tournament_bd)

    # Recompute ratings when tournament enters/leaves Finished state,
    # or when data changes on a finished tournament (e.g. SetScore, UpdateConfig)
    was_finished = pre_state == TournamentState.FINISHED
    is_finished = updated.state == TournamentState.FINISHED
    if was_finished != is_finished or is_finished:
        try:
            from ..ratings import (
                rating_category_for_tournament,
                recompute_ratings_for_players,
            )

            player_uids = {p.user_uid for p in updated.players if p.user_uid}
            category = rating_category_for_tournament(updated)
            results = await recompute_ratings_for_players(player_uids, category)
            if broadcast_user_event:
                for _user, bd in results:
                    broadcast_user_event(bd)
            # If category changed (format/online toggle), also recompute old category
            old_category = rating_category_for_tournament(tournament)
            if old_category != category:
                old_results = await recompute_ratings_for_players(
                    player_uids, old_category
                )
                if broadcast_user_event:
                    for _user, bd in old_results:
                        broadcast_user_event(bd)
        except Exception as e:
            logger.error(f"Error recomputing ratings for {uid}: {e}", exc_info=True)

    # TWDA auto-PR + VEKN push: trigger when tournament finishes
    if is_finished and not was_finished:
        await _maybe_submit_twda(updated)
        await _maybe_push_vekn(updated)

    return Response(
        content=encoder.encode(updated),
        media_type="application/json",
    )


# ============================================================================
# QR check-in (server-only, validates checkin_code before delegating)
# ============================================================================


class QrCheckinRequest(BaseModel):
    code: str


@router.post("/{uid}/qr-checkin")
async def qr_checkin(
    uid: str,
    request: QrCheckinRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Self check-in via QR code scanned at the venue."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if request.code != tournament.checkin_code:
        raise HTTPException(status_code=403, detail="Invalid check-in code")
    return await tournament_action(
        uid,
        TournamentActionRequest(type="CheckIn", player_uid=current_user.uid),
        authorization,
    )


# ============================================================================
# Deck endpoints
# ============================================================================

_cards_json: str | None = None


def _load_cards_json() -> str:
    """Load cards.json for the Rust engine (cached in memory)."""
    global _cards_json
    if _cards_json is None:
        from pathlib import Path

        cards_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "engine"
            / "data"
            / "cards.json"
        )
        if not cards_path.exists():
            raise HTTPException(
                status_code=503, detail="Cards data not available. Run: just cards"
            )
        _cards_json = cards_path.read_text(encoding="utf-8")
    return _cards_json


@router.get("/fetch-deck")
async def fetch_deck_proxy(
    url: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Proxy to fetch deck data from external URLs (VDB, VTESDecks, Amaranth).

    Read-only — no mutation. Works around CORS restrictions on external APIs.
    Returns parsed deck: {name, author, comments, cards}.
    """
    import asyncio

    await _get_current_user(authorization)  # auth check

    from ..providers import DeckFetchError, fetch_deck_from_url

    try:
        result = await asyncio.to_thread(fetch_deck_from_url, url)
    except DeckFetchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Failed to fetch deck from URL")
        raise HTTPException(status_code=400, detail=f"Failed to fetch deck: {e}") from e

    return Response(
        content=msgspec.json.encode(result),
        media_type="application/json",
    )


@router.get("/{uid}/decks/{player_uid}/twda")
async def export_deck_twda(
    uid: str,
    player_uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Export a player's deck in TWDA text format."""
    await _get_current_user(authorization)  # auth check
    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Find deck from DeckObject store
    all_decks = await get_decks_for_tournament(uid)
    deck = next((d for d in all_decks if d.user_uid == player_uid), None)
    if not deck:
        raise HTTPException(status_code=404, detail="No deck found for player")

    engine = _engine
    import json as json_mod

    deck_json = json_mod.dumps(
        {
            "name": deck.name,
            "author": deck.author,
            "comments": deck.comments,
            "cards": deck.cards,
        }
    )

    # Get player name
    player_user = await get_user_by_uid(player_uid)
    player_name = player_user.name if player_user else "Unknown"
    player_count = len(tournament.players)
    tournament_date = tournament.start or tournament.modified.isoformat()

    # Build tournament format string (e.g. "2R+F")
    rounds_count = len(tournament.rounds)
    has_finals = tournament.finals is not None
    tournament_format = f"{rounds_count}R" + ("+F" if has_finals else "")

    # Build tournament URL
    tournament_url = ""  # Can be set to app URL when deployed

    text = engine.export_twda(
        deck_json,
        _load_cards_json(),
        tournament.name,
        str(tournament_date),
        tournament.country or "",
        tournament_format,
        tournament_url,
        player_count,
        player_name,
    )
    return Response(content=text, media_type="text/plain")


@router.get("/{uid}/report")
async def tournament_report(
    uid: str,
    format: str = "text",
    authorization: str | None = Header(default=None),
) -> Response:
    """Download a tournament report with standings, results, and winner's deck.

    Query params:
    - format: "text" (default) or "json"
    """
    user = await _get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if tournament.state != TournamentState.FINISHED:
        raise HTTPException(status_code=400, detail="Tournament is not finished")

    # Check if organizer
    if not _is_organizer(user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can download reports"
        )

    if format == "json":
        # JSON report
        import json as json_mod

        report = {
            "tournament": {
                "name": tournament.name,
                "date": str(tournament.start or tournament.modified.isoformat()),
                "country": tournament.country,
                "format": tournament.format.value
                if hasattr(tournament.format, "value")
                else str(tournament.format),
                "player_count": len(tournament.players),
                "winner": tournament.winner,
            },
            "standings": [
                {
                    "user_uid": s.user_uid,
                    "gw": s.gw,
                    "vp": s.vp,
                    "tp": s.tp,
                    "finalist": s.finalist,
                }
                for s in tournament.standings
            ],
        }
        return Response(
            content=json_mod.dumps(report, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{uid}-report.json"'
            },
        )

    # Text report
    lines = []
    lines.append(f"Tournament Report: {tournament.name}")
    lines.append(f"Date: {tournament.start or tournament.modified.isoformat()}")
    lines.append(f"Location: {tournament.country or 'Unknown'}")
    lines.append(f"Players: {len(tournament.players)}")
    lines.append("")

    # Standings
    lines.append("=== Standings ===")
    for i, s in enumerate(tournament.standings, 1):
        player_user = await get_user_by_uid(s.user_uid)
        name = player_user.name if player_user else s.user_uid
        finalist_mark = " (F)" if s.finalist else ""
        winner_mark = " *WINNER*" if s.user_uid == tournament.winner else ""
        lines.append(
            f"{i:>3}. {name:30} GW={s.gw:.1f} VP={s.vp:.1f} TP={s.tp}{finalist_mark}{winner_mark}"
        )

    # Winner's deck (from DeckObject store)
    winner_deck = None
    if tournament.winner:
        all_decks = await get_decks_for_tournament(uid)
        winner_deck = next(
            (d for d in all_decks if d.user_uid == tournament.winner), None
        )

    if winner_deck:
        lines.append("")
        lines.append("=== Winner's Decklist ===")
        try:
            engine = _engine
            import json as json_mod

            deck_json = json_mod.dumps(
                {
                    "name": winner_deck.name,
                    "author": winner_deck.author,
                    "comments": winner_deck.comments,
                    "cards": winner_deck.cards,
                }
            )

            player_user = await get_user_by_uid(tournament.winner)
            player_name = player_user.name if player_user else "Unknown"
            tournament_date = tournament.start or tournament.modified.isoformat()
            rounds_count = len(tournament.rounds)
            has_finals = tournament.finals is not None
            tournament_format = f"{rounds_count}R" + ("+F" if has_finals else "")

            twda_text = engine.export_twda(
                deck_json,
                _load_cards_json(),
                tournament.name,
                str(tournament_date),
                tournament.country or "",
                tournament_format,
                "",
                len(tournament.players),
                player_name,
            )
            lines.append(twda_text)
        except Exception:
            lines.append("(Failed to generate decklist)")
    else:
        lines.append("")
        lines.append("Winner's decklist: not available")

    text = "\n".join(lines)
    return Response(
        content=text,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{uid}-report.txt"'},
    )


# ============================================================================
# Timer endpoints (online-only, not processed by Rust engine)
# ============================================================================


async def _check_organizer(authorization: str | None):
    """Auth check for timer endpoints. Returns user."""
    user = await _get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def _validate_timer_tournament(user, tournament: Tournament | None):
    """Validate tournament state for timer operations (inside transaction)."""
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not _is_organizer(user, tournament):
        raise HTTPException(status_code=403, detail="Organizer access required")
    if tournament.offline_mode:
        raise HTTPException(status_code=423, detail="Tournament is in offline mode")
    if tournament.state != TournamentState.PLAYING:
        raise HTTPException(status_code=400, detail="Tournament is not playing")


async def _save_timer_tx(tournament: Tournament, tx_conn) -> BroadcastData:
    """Save within transaction. Returns BroadcastData for broadcasting after commit."""
    tournament.modified = datetime.now(UTC)
    return await save_object(
        ObjectType.TOURNAMENT,
        tournament.uid,
        msgspec.to_builtins(tournament),
        conn=tx_conn,
    )


@router.post("/{uid}/timer/start")
async def timer_start(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Start or resume the global timer."""
    user = await _check_organizer(authorization)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        if not tournament.timer.paused:
            raise HTTPException(status_code=400, detail="Timer is already running")
        tournament.timer = TimerState(
            started_at=datetime.now(UTC),
            elapsed_before_pause=tournament.timer.elapsed_before_pause,
            paused=False,
        )
        bd = await _save_timer_tx(tournament, tx_conn)
    if broadcast_tournament_event:
        broadcast_tournament_event(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


@router.post("/{uid}/timer/pause")
async def timer_pause(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Pause the global timer."""
    user = await _check_organizer(authorization)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        if tournament.timer.paused:
            raise HTTPException(status_code=400, detail="Timer is already paused")
        elapsed = 0.0
        if tournament.timer.started_at:
            elapsed = (datetime.now(UTC) - tournament.timer.started_at).total_seconds()
        tournament.timer = TimerState(
            elapsed_before_pause=tournament.timer.elapsed_before_pause + elapsed,
            paused=True,
        )
        bd = await _save_timer_tx(tournament, tx_conn)
    if broadcast_tournament_event:
        broadcast_tournament_event(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


@router.post("/{uid}/timer/reset")
async def timer_reset(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """Reset the global timer to fresh paused state."""
    user = await _check_organizer(authorization)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        tournament.timer = TimerState()
        tournament.table_extra_time = {}
        tournament.table_paused_at = {}
        bd = await _save_timer_tx(tournament, tx_conn)
    if broadcast_tournament_event:
        broadcast_tournament_event(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


class AddTimeRequest(BaseModel):
    table: str  # table index as string key
    seconds: int


@router.post("/{uid}/timer/add-time")
async def timer_add_time(
    uid: str,
    request: AddTimeRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Add extra time to a specific table."""
    user = await _check_organizer(authorization)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        if tournament.time_extension_policy not in (
            TimeExtensionPolicy.ADDITIONS,
            TimeExtensionPolicy.BOTH,
        ):
            raise HTTPException(
                status_code=400, detail="Time additions not allowed by policy"
            )
        if request.seconds <= 0:
            raise HTTPException(status_code=400, detail="Seconds must be positive")
        current = tournament.table_extra_time.get(request.table, 0)
        if current + request.seconds > 600:
            raise HTTPException(
                status_code=400, detail="Max 600s (10 min) extra time per table"
            )
        tournament.table_extra_time[request.table] = current + request.seconds
        bd = await _save_timer_tx(tournament, tx_conn)
    if broadcast_tournament_event:
        broadcast_tournament_event(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


class ClockStopRequest(BaseModel):
    table: str


@router.post("/{uid}/timer/clock-stop")
async def timer_clock_stop(
    uid: str,
    request: ClockStopRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Pause a table's clock (clock-stop)."""
    user = await _check_organizer(authorization)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        if tournament.time_extension_policy not in (
            TimeExtensionPolicy.CLOCK_STOP,
            TimeExtensionPolicy.BOTH,
        ):
            raise HTTPException(
                status_code=400, detail="Clock stops not allowed by policy"
            )
        if request.table in tournament.table_paused_at:
            raise HTTPException(
                status_code=400, detail="Table clock is already stopped"
            )
        tournament.table_paused_at[request.table] = datetime.now(UTC).isoformat()
        bd = await _save_timer_tx(tournament, tx_conn)
    if broadcast_tournament_event:
        broadcast_tournament_event(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


@router.post("/{uid}/timer/clock-resume")
async def timer_clock_resume(
    uid: str,
    request: ClockStopRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Resume a table's clock (converts pause duration to extra_time)."""
    user = await _check_organizer(authorization)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        if tournament.time_extension_policy not in (
            TimeExtensionPolicy.CLOCK_STOP,
            TimeExtensionPolicy.BOTH,
        ):
            raise HTTPException(
                status_code=400, detail="Clock stops not allowed by policy"
            )
        paused_at_str = tournament.table_paused_at.get(request.table)
        if not paused_at_str:
            raise HTTPException(status_code=400, detail="Table clock is not stopped")
        paused_at = datetime.fromisoformat(paused_at_str)
        pause_duration = int((datetime.now(UTC) - paused_at).total_seconds())
        current_extra = tournament.table_extra_time.get(request.table, 0)
        tournament.table_extra_time[request.table] = current_extra + pause_duration
        del tournament.table_paused_at[request.table]
        bd = await _save_timer_tx(tournament, tx_conn)
    if broadcast_tournament_event:
        broadcast_tournament_event(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


# ============================================================================
# Judge call endpoint (online-only)
# ============================================================================

# Broadcast function set by main.py
broadcast_judge_call = None


class JudgeCallRequest(BaseModel):
    table: int


@router.post("/{uid}/call-judge", status_code=204)
async def call_judge(
    uid: str,
    request: JudgeCallRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Player calls for judge assistance at their table."""
    user = await _get_current_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tournament.state != TournamentState.PLAYING:
        raise HTTPException(status_code=400, detail="Tournament is not playing")
    if tournament.offline_mode:
        raise HTTPException(status_code=423, detail="Tournament is in offline mode")
    # Verify player is seated at the specified table in current round
    if not tournament.rounds:
        raise HTTPException(status_code=400, detail="No active round")
    current_round = tournament.rounds[-1]
    if request.table < 0 or request.table >= len(current_round):
        raise HTTPException(status_code=400, detail="Invalid table index")
    table = current_round[request.table]
    if not any(s.player_uid == user.uid for s in table.seating):
        raise HTTPException(status_code=403, detail="You are not seated at this table")
    # Build table label
    table_label = resolveTableLabelPy(tournament.table_rooms, request.table)
    # Broadcast to organizers
    if broadcast_judge_call:
        await broadcast_judge_call(
            tournament_uid=tournament.uid,
            table=request.table,
            table_label=table_label,
            player_name=user.name,
            organizer_uids=tournament.organizers_uids,
        )
    return Response(status_code=204)


def resolveTableLabelPy(rooms: list, table_idx: int) -> str:
    """Resolve table label from rooms config (Python equivalent of frontend util)."""
    if not rooms:
        return f"Table {table_idx + 1}"
    offset = 0
    for room in rooms:
        if table_idx < offset + room.count:
            local = table_idx - offset + 1
            return f"{room.name} T{local}"
        offset += room.count
    return f"Table {table_idx + 1}"


# ============================================================================
# Offline tournament mode endpoints
# ============================================================================


class GoOfflineRequest(BaseModel):
    device_id: str


@router.post("/{uid}/go-offline")
async def go_offline(
    uid: str,
    request: GoOfflineRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Lock a tournament for offline use on a specific device."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not _is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can take a tournament offline"
        )

    if tournament.offline_mode:
        raise HTTPException(
            status_code=409, detail="Tournament is already in offline mode"
        )

    tournament.offline_mode = True
    tournament.offline_device_id = request.device_id
    tournament.offline_user_uid = current_user.uid
    tournament.offline_since = datetime.now(UTC)
    tournament.modified = datetime.now(UTC)

    bd = await update_tournament(tournament)
    logger.info(
        f"Tournament {uid} went offline (device={request.device_id}, user={current_user.uid})"
    )

    if broadcast_tournament_event:
        broadcast_tournament_event(bd)

    return Response(content=encoder.encode(tournament), media_type="application/json")


class OfflinePlayerData(BaseModel):
    temp_uid: str
    name: str
    vekn_id: str | None = None
    email: str | None = None


class GoOnlineRequest(BaseModel):
    device_id: str
    tournament: dict  # Full tournament data from the offline device
    offline_players: list[OfflinePlayerData] = []
    offline_sanctions: list[dict] = []
    offline_decks: list[dict] = []
    force: bool = False


async def _resolve_or_create_offline_player(
    player_data: OfflinePlayerData, tournament_country: str | None
) -> tuple[str, User]:
    """Resolve an offline player to a real user. Returns (temp_uid, real_user)."""
    # 1. Match by vekn_id
    if player_data.vekn_id:
        user = await get_user_by_vekn_id(player_data.vekn_id)
        if user:
            return player_data.temp_uid, user

    # 2. Match by email
    if player_data.email:
        auth_method = await get_auth_method_by_identifier("email", player_data.email)
        if auth_method:
            user = await get_user_by_uid(auth_method.user_uid)
            if user:
                return player_data.temp_uid, user

    # 3. Create new user
    now = datetime.now(UTC)
    new_user = User(
        uid=str(uuid7()),
        modified=now,
        name=player_data.name,
        country=tournament_country,
    )
    bd = await insert_user(new_user)
    logger.info(f"Created user {new_user.uid} for offline player '{player_data.name}'")

    if broadcast_user_event:
        broadcast_user_event(bd)

    return player_data.temp_uid, new_user


def _remap_uids_in_tournament(tournament_data: dict, uid_map: dict[str, str]) -> dict:
    """Replace all temp_uid references with real UIDs throughout tournament data."""
    import json as json_mod

    raw = json_mod.dumps(tournament_data)
    for temp_uid, real_uid in uid_map.items():
        raw = raw.replace(temp_uid, real_uid)
    return json_mod.loads(raw)


@router.post("/{uid}/go-online")
async def go_online(
    uid: str,
    request: GoOnlineRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Bring a tournament back online with full reconciliation."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    # Tournament might not exist on server (created offline)
    if tournament and not _is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can bring a tournament online"
        )

    # Verify device lock
    if tournament and tournament.offline_mode:
        if tournament.offline_device_id != request.device_id and not request.force:
            raise HTTPException(
                status_code=409,
                detail="Tournament owned by another device. Use force to override.",
            )

    # Validate tournament UID matches URL
    if request.tournament.get("uid") and request.tournament["uid"] != uid:
        raise HTTPException(status_code=400, detail="Tournament UID mismatch")
    request.tournament["uid"] = uid  # Force correct UID

    # Preserve original organizers (prevent client from removing them)
    if tournament:
        original_organizers = tournament.organizers_uids or []
        client_organizers = request.tournament.get("organizers_uids", [])
        merged = list(dict.fromkeys(original_organizers + client_organizers))
        request.tournament["organizers_uids"] = merged

    # 1. Resolve offline players → real user accounts
    uid_map: dict[str, str] = {}
    for player_data in request.offline_players:
        temp_uid, real_user = await _resolve_or_create_offline_player(
            player_data, request.tournament.get("country")
        )
        uid_map[temp_uid] = real_user.uid

    # 2. Remap UIDs throughout tournament data
    tournament_data = request.tournament
    if uid_map:
        tournament_data = _remap_uids_in_tournament(tournament_data, uid_map)

    # 3. Clear offline fields
    tournament_data["offline_mode"] = False
    tournament_data["offline_device_id"] = ""
    tournament_data["offline_user_uid"] = ""
    tournament_data["offline_since"] = None
    tournament_data["modified"] = datetime.now(UTC).isoformat()

    # 4. Save tournament
    updated = decoder.decode(msgspec.json.encode(tournament_data))
    updated.modified = datetime.now(UTC)

    if tournament:
        tournament_bd = await update_tournament(updated)
    else:
        tournament_bd = await insert_tournament(updated)

    logger.info(
        f"Tournament {uid} went back online (user={current_user.uid}, remapped={len(uid_map)} players)"
    )

    # 5. Save offline sanctions with remapped UIDs
    for sanction_data in request.offline_sanctions:
        if uid_map:
            import json as json_mod

            raw = json_mod.dumps(sanction_data)
            for temp_uid, real_uid in uid_map.items():
                raw = raw.replace(temp_uid, real_uid)
            sanction_data = json_mod.loads(raw)

        sanction = msgspec.convert(sanction_data, Sanction)
        bd = await insert_sanction(sanction)
        if broadcast_sanction_event:
            broadcast_sanction_event(bd)

    # 6. Save offline decks with remapped UIDs
    for deck_data in request.offline_decks:
        if uid_map:
            import json as json_mod

            raw = json_mod.dumps(deck_data)
            for temp_uid, real_uid in uid_map.items():
                raw = raw.replace(temp_uid, real_uid)
            deck_data = json_mod.loads(raw)

        # Ensure tournament_uid is correct
        deck_data["tournament_uid"] = uid
        deck_obj = msgspec.convert(deck_data, DeckObject)
        bd = await save_object_from_model(ObjectType.DECK, deck_obj)
        if broadcast_deck_event:
            broadcast_deck_event(bd)

    # 7. Broadcast updated tournament
    if broadcast_tournament_event:
        broadcast_tournament_event(tournament_bd)

    return Response(content=encoder.encode(updated), media_type="application/json")


class ForceTakeoverRequest(BaseModel):
    device_id: str


@router.post("/{uid}/force-takeover")
async def force_takeover(
    uid: str,
    request: ForceTakeoverRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Transfer offline lock to a new device (any organizer of this tournament)."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not _is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can force-takeover"
        )

    if not tournament.offline_mode:
        raise HTTPException(status_code=400, detail="Tournament is not in offline mode")

    old_device = tournament.offline_device_id
    tournament.offline_device_id = request.device_id
    tournament.offline_user_uid = current_user.uid
    tournament.modified = datetime.now(UTC)

    bd = await update_tournament(tournament)
    logger.info(
        f"Tournament {uid} force-takeover: {old_device} → {request.device_id} by {current_user.uid}"
    )

    if broadcast_tournament_event:
        broadcast_tournament_event(bd)

    return Response(content=encoder.encode(tournament), media_type="application/json")


class SyncOfflineRequest(BaseModel):
    device_id: str
    tournament: dict


@router.post("/{uid}/sync-offline")
async def sync_offline(
    uid: str,
    request: SyncOfflineRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    """Background data backup for offline tournament. Saves snapshot without unlocking."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not tournament.offline_mode:
        raise HTTPException(status_code=400, detail="Tournament is not in offline mode")

    if tournament.offline_device_id != request.device_id:
        raise HTTPException(
            status_code=409, detail="Device does not hold the offline lock"
        )

    # Save tournament snapshot (keep offline_mode=True)
    tournament_data = request.tournament
    tournament_data["offline_mode"] = True
    tournament_data["offline_device_id"] = tournament.offline_device_id
    tournament_data["offline_user_uid"] = tournament.offline_user_uid
    if tournament.offline_since:
        tournament_data["offline_since"] = tournament.offline_since.isoformat()
    tournament_data["modified"] = datetime.now(UTC).isoformat()

    updated = decoder.decode(msgspec.json.encode(tournament_data))
    updated.modified = datetime.now(UTC)
    await update_tournament(updated)

    now = datetime.now(UTC)
    logger.info(f"Tournament {uid} offline sync from device {request.device_id}")

    return Response(
        content=encoder.encode({"synced_at": now.isoformat()}),
        media_type="application/json",
    )


@router.post("/{uid}/force-unlock")
async def force_unlock(
    uid: str,
    authorization: str | None = Header(default=None),
) -> Response:
    """IC-only emergency unlock. Clears offline mode entirely."""
    current_user = await _get_current_user(authorization)
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if Role.IC not in current_user.roles:
        raise HTTPException(
            status_code=403, detail="Only IC can force-unlock tournaments"
        )

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not tournament.offline_mode:
        raise HTTPException(status_code=400, detail="Tournament is not in offline mode")

    tournament.offline_mode = False
    tournament.offline_device_id = ""
    tournament.offline_user_uid = ""
    tournament.offline_since = None
    tournament.modified = datetime.now(UTC)

    bd = await update_tournament(tournament)
    logger.info(f"Tournament {uid} force-unlocked by IC {current_user.uid}")

    if broadcast_tournament_event:
        broadcast_tournament_event(bd)

    return Response(content=encoder.encode(tournament), media_type="application/json")
