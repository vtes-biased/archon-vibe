"""Tournament API endpoints."""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from importlib.resources import files
from uuid import uuid7

import msgspec
from archon_engine import PyEngine
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import permissions
from ..broadcast import (
    broadcast_judge_call,
    broadcast_personal,
    broadcast_precomputed,
)
from ..card_data import cards_json_text
from ..db import (
    BroadcastData,
    allocate_next_vekn_id,
    compute_access_version,
    delete_banner,
    get_all_leagues,
    get_auth_method_by_identifier,
    get_banner,
    get_decks_for_tournament,
    get_league_by_uid,
    get_sanctions_for_tournament,
    get_sanctions_for_user,
    get_sanctions_for_users,
    get_tournament_by_uid,
    get_user_by_uid,
    get_user_by_vekn_id,
    save_object,
    save_object_from_model,
    save_sanction,
    save_tournament,
    save_user,
    soft_delete_tournament,
    tournament_transaction,
    upsert_banner,
)
from ..engine_errors import EngineRejection
from ..middleware.auth import OptionalUser
from ..models import (
    DeckListsMode,
    DeckObject,
    ObjectType,
    Role,
    Sanction,
    SanctionLevel,
    StandingsMode,
    TimerState,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)
from .auth import send_invite_email

router = APIRouter(prefix="/api/tournaments", tags=["tournaments"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()

# Post-finish actions that CANNOT change ranking points, so they must not trigger
# the (expensive: full window recompute + a broadcast per player) rating pass on
# an already-finished tournament. Conservative denylist — everything else still
# recomputes, because a stale rating is worse than a redundant pass. These are the
# edits that realistically happen after a tournament finishes: the winner's TWDA
# writeup, closing-ceremony raffles, payment reconciliation, late check-in fixes.
# Wire types are the RAW request.type, unnormalized — so list every deck-upsert
# alias the engine accepts (parsing.rs: UpsertDeck|UploadDeck|UpdateDeck); the
# frontend actually sends UpsertDeck, so omitting it defeated the headline case.
_RATING_IRRELEVANT_ACTIONS = frozenset(
    {
        "UpsertDeck",
        "UploadDeck",
        "UpdateDeck",
        "DeleteDeck",
        "SetPaymentStatus",
        "MarkAllPaid",
        # Proxy toggle: rating is recomputed only from FINISHED tournaments, and the
        # engine blocks the toggle once finished — so it never changes a live rating.
        "SetNonCompeting",
        "RaffleDraw",
        "RaffleUndo",
        "RaffleClear",
        "CheckIn",
        "CheckOut",
        "CheckInAll",
        "ResetCheckIn",
    }
)

_engine = PyEngine()


async def _build_decks_json(tournament_uid: str, conn=None) -> str:
    """Build deck metadata JSON for the engine's decks parameter."""
    decks = await get_decks_for_tournament(tournament_uid, conn=conn)
    return msgspec.json.encode(
        [{"user_uid": d.user_uid, "round": d.round, "uid": d.uid} for d in decks]
    ).decode()


async def _process_deck_ops(
    deck_ops: list,
    tournament_uid: str,
    existing_decks: list[DeckObject] | None = None,
    org_uids: list[str] | None = None,
) -> list[BroadcastData]:
    """Process deck_ops from engine result. Returns BroadcastData for each affected deck."""
    if not deck_ops:
        return []
    if existing_decks is None:
        existing_decks = await get_decks_for_tournament(tournament_uid)

    _org_uids = org_uids or []
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
            bd.org_uids = _org_uids
            affected.append(bd)

        elif op_type == "delete":
            player_uid = op["player_uid"]
            deck_index = op.get("deck_index")
            is_multideck = op.get("multideck", False)
            for d in existing_decks:
                if d.user_uid == player_uid:
                    if is_multideck and deck_index is not None:
                        if d.round != deck_index:
                            continue
                    d.deleted_at = datetime.now(UTC)
                    d.modified = datetime.now(UTC)
                    bd = await save_object_from_model(ObjectType.DECK, d)
                    bd.org_uids = _org_uids
                    affected.append(bd)

        elif op_type == "set_public":
            deck_uid = op.get("deck_uid")
            public_val = op.get("public", False)
            target = next((d for d in existing_decks if d.uid == deck_uid), None)
            if target:
                target.public = public_val
                target.modified = datetime.now(UTC)
                bd = await save_object_from_model(ObjectType.DECK, target)
                bd.org_uids = _org_uids
                affected.append(bd)

    return affected


async def _maybe_push_vekn(tournament: Tournament) -> None:
    """Push tournament results to VEKN if VEKN_PUSH is enabled."""
    try:
        from ..vekn_push import push_tournament_results, vekn_push_client

        async with vekn_push_client() as client:
            if client is not None:
                await push_tournament_results(client, tournament)
    except Exception:
        logger.exception("Failed to push VEKN results")


async def _maybe_push_vekn_event(tournament: Tournament) -> None:
    """Create VEKN calendar event if VEKN_PUSH is enabled."""
    try:
        from ..vekn_push import push_tournament_event, vekn_push_client

        async with vekn_push_client() as client:
            if client is not None:
                await push_tournament_event(client, tournament)
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
        from ..twda import submit_twda_pr

        engine = _engine

        player_user = await get_user_by_uid(tournament.winner)
        player_name = player_user.name if player_user else "Unknown"

        # Resolve the TWDA "Created by:" designer credit from the deck's
        # attribution (the "designed by" reference), not the raw author text.
        #   None              -> anonymous (null) or unset/self: omit the credit
        #                        (never leak a stored author the designer hid)
        #   "twda"            -> historical import; author already holds the name
        #   player's own id   -> self: omit (redundant with the header player line)
        #   other vekn / name -> credit that member; resolve a vekn -> display name
        attribution = winner_deck.attribution
        self_ids = {i for i in (getattr(player_user, "vekn_id", ""), player_name) if i}
        if attribution == "twda":
            designer_credit = winner_deck.author
        elif not attribution or attribution in self_ids:
            designer_credit = ""
        else:
            designer = await get_user_by_vekn_id(attribution)
            designer_credit = (designer.name if designer else "") or winner_deck.author

        deck_json = json.dumps(
            {
                "name": winner_deck.name,
                "author": designer_credit,
                "comments": winner_deck.comments,
                "cards": winner_deck.cards,
            }
        )
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


def _build_actor_context(
    user, tournament: Tournament, can_organize_league_uids: list[str] | None = None
) -> dict:
    """Build actor context dict for the Rust engine."""
    return {
        "uid": user.uid,
        "roles": [r.value if hasattr(r, "value") else str(r) for r in user.roles],
        "is_organizer": permissions.is_organizer(user, tournament),
        "can_organize_league_uids": can_organize_league_uids or [],
    }


async def _get_user_organizable_league_uids(user, conn=None) -> list[str]:
    """Get league UIDs the user can organize (own leagues + NC same-country)."""
    if Role.IC in user.roles:
        return []  # IC bypasses league check in engine
    leagues = await get_all_leagues(conn=conn)
    return [
        lg.uid
        for lg in leagues
        if user.uid in lg.organizers_uids
        or (Role.NC in user.roles and lg.country == user.country)
    ]


async def _check_player_barred(
    player_uid: str, tournament_uid: str, tournament: Tournament, conn=None
) -> None:
    """Check if a player is barred from participating (cross-tournament sanctions).

    Raises EngineRejection (-> 400 with engine error code) if:
    - Player has an active suspension
    - Player is DQ'd in a sibling league tournament (league-wide DQ)
    """
    from datetime import UTC, datetime

    # Check active suspensions
    user_sanctions = await get_sanctions_for_user(player_uid, conn=conn)
    now = datetime.now(UTC)
    for s in user_sanctions:
        if s.deleted_at or s.lifted_at:
            continue
        if s.level == SanctionLevel.SUSPENSION:
            if s.expires_at is None or s.expires_at > now:
                raise EngineRejection(
                    "Player is suspended and cannot participate",
                    code="tournament.player_suspended",
                )

    # Check league-wide DQ (only if tournament is in a league)
    if tournament.league_uid:
        for s in user_sanctions:
            if s.deleted_at or s.lifted_at:
                continue
            if s.level == SanctionLevel.DISQUALIFICATION and s.tournament_uid:
                # Check if the DQ sanction's tournament is in the same league
                dq_tournament = await get_tournament_by_uid(s.tournament_uid, conn=conn)
                if dq_tournament and dq_tournament.league_uid == tournament.league_uid:
                    raise EngineRejection(
                        "Player is disqualified from a league tournament and cannot participate",
                        code="tournament.player_disqualified",
                    )


class OrganizerAction(BaseModel):
    user_uid: str


async def _invalidate_organizer_view(
    tournament: Tournament, user_uid: str, modified_at: str | None
) -> None:
    """Targeted SSE invalidation for the user whose organizer status just changed.

    Pushes the tournament + each of its decks to that one user at their NEWLY-entitled
    projection — full on add (the organizer upgrade), member-or-tombstone on remove (a
    private deck whose member projection is null is tombstoned, evicting the leaked full
    copy from their IDB) — each frame carrying the recomputed access-version so the client
    refreshes its fingerprint without a full resync. broadcast_precomputed already
    propagated the org-set change to everyone else; this is the per-user overlay delta.
    """
    user = await get_user_by_uid(user_uid)
    if not user:
        return
    av = await compute_access_version(user)
    org_uids = tournament.organizers_uids
    broadcast_personal(
        user_uid,
        obj_type=ObjectType.TOURNAMENT,
        uid=tournament.uid,
        full_dict=msgspec.to_builtins(tournament),
        country=tournament.country,
        org_uids=org_uids,
        modified_at=modified_at,
        access_version=av,
    )
    for deck in await get_decks_for_tournament(tournament.uid):
        broadcast_personal(
            user_uid,
            obj_type=ObjectType.DECK,
            uid=deck.uid,
            full_dict=msgspec.to_builtins(deck),
            org_uids=org_uids,
            obj_user_uid=deck.user_uid,
            modified_at=modified_at,
            access_version=av,
        )


@router.post("/{uid}/organizers")
async def add_organizer(
    uid: str,
    body: OrganizerAction,
    current_user: OptionalUser = None,
) -> Response:
    """Add an organizer to a tournament."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not permissions.is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can manage organizers"
        )

    if body.user_uid not in tournament.organizers_uids:
        tournament.organizers_uids.append(body.user_uid)
        tournament.modified = datetime.now(UTC)
        bd = await save_tournament(tournament)
        broadcast_precomputed(bd)
        # Grant access: push the tournament + its (private) decks at full to the new
        # organizer — broadcast_precomputed delivers the tournament but never the decks.
        await _invalidate_organizer_view(tournament, body.user_uid, bd.modified_at)

    return Response(
        content=encoder.encode(tournament),
        media_type="application/json",
    )


@router.delete("/{uid}/organizers/{organizer_uid}")
async def remove_organizer(
    uid: str,
    organizer_uid: str,
    current_user: OptionalUser = None,
) -> Response:
    """Remove an organizer from a tournament."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not permissions.is_organizer(current_user, tournament):
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
        # save_tournament advances modified_at, so the member-level tournament self-heals
        # via the since-catch-up too (checkin_code/vekn_pushed_at drop) — the targeted push
        # below additionally tombstones the now-invisible private decks (the leak fix).
        bd = await save_tournament(tournament)
        broadcast_precomputed(bd)
        # Revoke access without a full resync: downgrade the tournament + tombstone the
        # private decks for just this user (offline removal is caught by the fp at connect).
        await _invalidate_organizer_view(tournament, organizer_uid, bd.modified_at)

    return Response(
        content=encoder.encode(tournament),
        media_type="application/json",
    )


# Banner endpoints — per-tournament hero / social-share image.
# Bytes live in the banners table (not the synced objects row); the Tournament
# only carries a versioned banner_path so a re-upload propagates via SSE while
# each version stays long-cacheable. Organizer-gated, mirrors the avatar flow.
MAX_BANNER_SIZE = 1024 * 1024  # 1MB


@router.post("/{uid}/banner")
async def upload_banner(
    uid: str,
    file: UploadFile,
    current_user: OptionalUser = None,
) -> Response:
    """Upload or replace a tournament banner (organizer only).

    Expects a 1.91:1 (1200×630) image, max 1MB. Client crops before upload.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not permissions.is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can set the banner"
        )
    # Mirror every other tournament mutation: refuse server-side writes while the
    # tournament is offline-locked, so banner_path can't diverge during the
    # offline window and get clobbered by the go-online snapshot overwrite.
    if tournament.offline_mode:
        raise HTTPException(status_code=423, detail="Tournament is in offline mode")

    if file.content_type not in ("image/webp", "image/png", "image/jpeg"):
        raise HTTPException(status_code=400, detail="Banner must be webp, png, or jpeg")

    data = await file.read()
    if len(data) > MAX_BANNER_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Banner too large. Max size: {MAX_BANNER_SIZE // 1024}KB",
        )

    await upsert_banner(uid, data, file.content_type or "image/webp")

    now = datetime.now(UTC)
    version = int(now.timestamp() * 1000)  # cache-busting token baked into the URL
    tournament.banner_path = f"/api/tournaments/{uid}/banner?v={version}"
    tournament.modified = now
    bd = await save_tournament(tournament)
    broadcast_precomputed(bd)

    return Response(content=b'{"success": true}', media_type="application/json")


@router.get("/{uid}/banner")
async def get_banner_image(uid: str, request: Request) -> Response:
    """Serve a tournament banner. A versioned (?v=) URL is immutable, so it can
    be cached aggressively; an unversioned request gets a short TTL."""
    result = await get_banner(uid)
    if not result:
        raise HTTPException(status_code=404, detail="Banner not found")

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


@router.delete("/{uid}/banner")
async def delete_banner_image(
    uid: str,
    current_user: OptionalUser = None,
) -> Response:
    """Delete a tournament banner (organizer only)."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not permissions.is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can remove the banner"
        )
    if tournament.offline_mode:
        raise HTTPException(status_code=423, detail="Tournament is in offline mode")

    deleted = await delete_banner(uid)
    if tournament.banner_path is not None:
        tournament.banner_path = None
        tournament.modified = datetime.now(UTC)
        bd = await save_tournament(tournament)
        broadcast_precomputed(bd)
    elif not deleted:
        raise HTTPException(status_code=404, detail="Banner not found")

    return Response(content=b'{"success": true}', media_type="application/json")


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
    round_time: int = 0
    finals_time: int = 0


def _parse_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


@router.post("/", status_code=201)
async def create_tournament(
    request: CreateTournamentRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Create a new tournament."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not permissions.is_official(current_user):
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

    # Validate league_uid: only league organizers (or IC) can link
    if request.league_uid:
        league = await get_league_by_uid(request.league_uid)
        if not league:
            raise HTTPException(status_code=400, detail="League not found")
        if Role.IC not in current_user.roles:
            is_nc_same_country = (
                Role.NC in current_user.roles and league.country == current_user.country
            )
            is_organizer = current_user.uid in league.organizers_uids
            if not (is_nc_same_country or is_organizer):
                raise HTTPException(
                    status_code=403,
                    detail="Only league organizers can link tournaments to this league",
                )

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
        round_time=request.round_time,
        finals_time=request.finals_time,
    )

    bd = await save_tournament(tournament)
    logger.info(f"Tournament {tournament.uid} created by {current_user.uid}")

    broadcast_precomputed(bd)

    # VEKN push: create calendar event. Background task — the response must not
    # wait on vekn.net (30-120s timeouts when it is down); batch_push retries.
    asyncio.create_task(_maybe_push_vekn_event(tournament))

    return Response(
        content=encoder.encode(tournament),
        media_type="application/json",
        status_code=201,
    )


# --- Static routes (must be before /{uid} to avoid path parameter capture) ---


@router.get("/archon-template")
async def download_archon_template() -> FileResponse:
    """Serve blank Archon v1.5l spreadsheet template. Public access."""
    # must live under backend/src/data to ship inside the installed wheel
    path = files("backend.src").joinpath("data", "thearchon1.5l.xlsx")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Template file not found")
    return FileResponse(
        path,
        filename="thearchon1.5l.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/fetch-deck")
async def fetch_deck_proxy(
    url: str,
    current_user: OptionalUser = None,
) -> Response:
    """Proxy to fetch deck data from external URLs (VDB, VTESDecks, Amaranth).

    Read-only — no mutation. Works around CORS restrictions on external APIs.
    Returns parsed deck: {name, author, comments, cards}.
    """
    import asyncio

    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

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


# --- Dynamic routes ---


@router.delete("/{uid}")
async def delete_tournament_endpoint(
    uid: str,
    current_user: OptionalUser = None,
) -> Response:
    """Delete a tournament (organizers only, PLANNED state only)."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not permissions.is_organizer(current_user, tournament):
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

    if result:
        broadcast_precomputed(result[1])

    return Response(
        content=encoder.encode({"message": "Tournament deleted"}),
        media_type="application/json",
    )


@router.post("/{uid}/archon-import")
async def archon_import(
    uid: str,
    file: UploadFile,
    current_user: OptionalUser = None,
) -> Response:
    """Import a filled-in Archon v1.5l spreadsheet into an existing tournament."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not permissions.is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403,
            detail="Only organizers can import",
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
        broadcast_tournament_event=broadcast_precomputed,
        broadcast_user_event=broadcast_precomputed,
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
    non_competing: bool | None = None  # For SetNonCompeting (proxy toggle)
    seating: list[list[str]] | None = None  # For AlterSeating
    player_uids: list[str] | None = None  # For SelfOrganizeRound: the chosen pod
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
    current_user: OptionalUser = None,
) -> Response:
    """Process a tournament event via the Rust engine.

    All tournament state mutations go through this endpoint, which delegates
    to the Rust engine for consistent behavior in online/offline modes.

    Uses SELECT ... FOR UPDATE to serialize concurrent writes per tournament,
    preventing lost updates when multiple actions arrive simultaneously.
    """
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
    if request.non_competing is not None:
        event_data["non_competing"] = request.non_competing
    if request.seating:
        event_data["seating"] = request.seating
    if request.player_uids is not None:
        event_data["player_uids"] = request.player_uids
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

        # Reads below run on tx_conn (the locked transaction connection) rather
        # than acquiring extra pooled connections while holding FOR UPDATE — a
        # single in-flight action consumes one pooled connection, so concurrent
        # actions can't starve the small pool (see db._acquire).
        # Build actor context for Rust engine
        can_organize = None
        if request.type == "UpdateConfig" and request.config:
            can_organize = await _get_user_organizable_league_uids(
                current_user, conn=tx_conn
            )
        actor_data = _build_actor_context(current_user, tournament, can_organize)

        # Fetch sanctions for this tournament + user-level suspension/DQ
        # sanctions for all tournament players (needed for CheckInAll etc.)
        tournament_sanctions = await get_sanctions_for_tournament(uid, conn=tx_conn)
        seen_uids = {s.uid for s in tournament_sanctions}
        player_uids = {p.user_uid for p in tournament.players if p.user_uid}
        # Single batched query (was one round-trip per player while locked)
        for s in await get_sanctions_for_users(player_uids, conn=tx_conn):
            if s.uid in seen_uids or s.deleted_at or s.lifted_at:
                continue
            if s.level in (
                SanctionLevel.SUSPENSION,
                SanctionLevel.DISQUALIFICATION,
            ):
                tournament_sanctions.append(s)
                seen_uids.add(s.uid)
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

        # Inject authoritative vekn_id for Register/AddPlayer/CheckIn (server overrides client)
        if request.type in ("Register", "AddPlayer") and request.user_uid:
            target_user = await get_user_by_uid(request.user_uid, conn=tx_conn)
            if target_user and target_user.vekn_id:
                event_data["vekn_id"] = target_user.vekn_id
        elif request.type == "CheckIn" and request.player_uid:
            target_user = await get_user_by_uid(request.player_uid, conn=tx_conn)
            if target_user and target_user.vekn_id:
                event_data["vekn_id"] = target_user.vekn_id

        # Serialize tournament to JSON for engine
        tournament_json = encoder.encode(tournament).decode("utf-8")
        event_json = msgspec.json.encode(event_data).decode("utf-8")
        actor_json = msgspec.json.encode(actor_data).decode("utf-8")
        sanctions_json = msgspec.json.encode(sanctions_data).decode("utf-8")
        decks_json = await _build_decks_json(uid, conn=tx_conn)

        # Backend pre-checks for cross-tournament sanctions
        if request.type in ("CheckIn", "Register", "AddPlayer"):
            player_uid = request.player_uid or request.user_uid
            if player_uid:
                await _check_player_barred(player_uid, uid, tournament, conn=tx_conn)

        # Call Rust engine
        engine = _engine
        try:
            result_json = engine.process_tournament_event(
                tournament_json, event_json, actor_json, sanctions_json, decks_json
            )
        except ValueError as e:
            # Engine rejections arrive as ValueError carrying the wire JSON
            raise EngineRejection.from_engine(e) from e

        # Parse new result format: {"tournament": {...}, "deck_ops": [...]}
        result = json.loads(result_json)
        # Normalize datetime fields: frontend sends "YYYY-MM-DDTHH:MM" (no seconds)
        # but msgspec requires at least "YYYY-MM-DDTHH:MM:SS" for RFC3339 decoding
        t_data = result["tournament"]
        for dt_field in ("start", "finish"):
            v = t_data.get(dt_field)
            if isinstance(v, str) and len(v) == 16:  # "YYYY-MM-DDTHH:MM"
                t_data[dt_field] = v + ":00"
        # Build the model straight from the engine's dict: msgspec.convert applies
        # the same coercion (incl. RFC3339 str→datetime) as a JSON decode but skips
        # the redundant whole-object encode→decode round-trip — meaningful event-loop
        # CPU on a 400-player object during a large scoring burst.
        updated = msgspec.convert(t_data, Tournament)
        updated.modified = datetime.now(UTC)
        # Stamp the actual end time when entering Finished without an explicit
        # finish date — the engine never sets finish, and ratings/VEKN push
        # rely on it (server-side hook, same as modified and the timer below)
        if (
            updated.state == TournamentState.FINISHED
            and tournament.state != TournamentState.FINISHED
            and updated.finish is None
        ):
            updated.finish = datetime.now(UTC)
        deck_ops = result.get("deck_ops", [])

        # Timer lifecycle hooks (online-only, not handled by Rust engine)
        # Skip timer reset if other rounds are still in progress (parallel rounds)
        if request.type in ("StartRound", "SelfOrganizeRound", "StartFinals"):
            in_progress = sum(
                1
                for r in (updated.rounds or [])
                if any(t.state != "Finished" for t in r)
            )
            if in_progress <= 1:
                updated.timer = TimerState()  # Fresh paused timer
                updated.table_extra_time = {}
        elif request.type in (
            "FinishRound",
            "CancelRound",
            "FinishTournament",
            "CancelFinals",
        ):
            # Only reset timer if tournament left Playing state (all rounds done)
            if updated.state != "Playing":
                if not updated.timer.paused and updated.timer.started_at:
                    # Accumulate elapsed time before pausing
                    elapsed = (
                        datetime.now(UTC) - updated.timer.started_at
                    ).total_seconds()
                    updated.timer = TimerState(
                        elapsed_before_pause=updated.timer.elapsed_before_pause
                        + elapsed,
                        paused=True,
                    )
                updated.table_extra_time = {}

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
    deck_bds = await _process_deck_ops(deck_ops, uid, org_uids=updated.organizers_uids)
    for bd in deck_bds:
        broadcast_precomputed(bd)

    broadcast_precomputed(tournament_bd)

    # Recompute ratings when the tournament enters/leaves Finished (state change),
    # or when a result-affecting action lands on an already-finished tournament
    # (e.g. SetScore/Override correction). Skip the recompute for finished-state
    # edits that can't move ranking points (deck/payment/raffle/check-in) — they
    # otherwise trigger a full window recompute + a broadcast per player on EVERY
    # such post-finish action.
    was_finished = pre_state == TournamentState.FINISHED
    is_finished = updated.state == TournamentState.FINISHED
    state_changed = was_finished != is_finished
    results_may_change = is_finished and request.type not in _RATING_IRRELEVANT_ACTIONS
    if state_changed or results_may_change:
        try:
            from ..ratings import (
                rating_category_for_tournament,
                recompute_ratings_for_players,
            )

            player_uids = {p.user_uid for p in updated.players if p.user_uid}
            category = rating_category_for_tournament(updated)
            results = await recompute_ratings_for_players(player_uids, category)
            for _user, bd in results:
                broadcast_precomputed(bd)
            # If category changed (format/online toggle), also recompute old category
            old_category = rating_category_for_tournament(tournament)
            if old_category != category:
                old_results = await recompute_ratings_for_players(
                    player_uids, old_category
                )
                for _user, bd in old_results:
                    broadcast_precomputed(bd)
        except Exception as e:
            logger.error(f"Error recomputing ratings for {uid}: {e}", exc_info=True)

    # TWDA auto-PR + VEKN push: trigger when tournament finishes. VEKN push runs
    # in the background — the response must not wait on vekn.net (30-120s
    # timeouts when it is down); batch_push retries.
    if is_finished and not was_finished:
        await _maybe_submit_twda(updated)
        asyncio.create_task(_maybe_push_vekn(updated))
    elif (
        is_finished
        and updated.winner
        and any(
            op.get("op") == "upsert" and op.get("player_uid") == updated.winner
            for op in deck_ops
        )
    ):
        # Winner's deck was edited on an already-finished tournament (organizers
        # only — players are deck-locked post-finish). Re-submit so the
        # idempotent TWDA PR (branch/file keyed on the vekn event id) picks up
        # the change, e.g. an added strategy writeup. Background: the deck save
        # already committed and _maybe_submit_twda self-contains its errors.
        asyncio.create_task(_maybe_submit_twda(updated))

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
    current_user: OptionalUser = None,
) -> Response:
    """Self check-in via QR code scanned at the venue."""
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
        current_user,
    )


# ============================================================================
# Deck endpoints
# ============================================================================


def _load_cards_json() -> str:
    """Load cards.json for the Rust engine (cached in memory by card_data)."""
    text = cards_json_text()
    if text is None:
        raise HTTPException(
            status_code=503, detail="Cards data not available. Run: just cards"
        )
    return text


@router.get("/{uid}/report")
async def tournament_report(
    uid: str,
    user: OptionalUser = None,
) -> Response:
    """Download a tournament report (JSON) with standings and results."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if tournament.state != TournamentState.FINISHED:
        raise HTTPException(status_code=400, detail="Tournament is not finished")

    if not permissions.is_organizer(user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can download reports"
        )

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
        content=json.dumps(report, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{uid}-report.json"'},
    )


# ============================================================================
# Timer endpoints (online-only, not processed by Rust engine)
# ============================================================================


# _check_organizer removed — auth now via OptionalUser dependency


def _validate_timer_tournament(user, tournament: Tournament | None):
    """Validate tournament state for timer operations (inside transaction)."""
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not permissions.is_organizer(user, tournament):
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
    user: OptionalUser = None,
) -> Response:
    """Start or resume the global timer."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
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
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


@router.post("/{uid}/timer/pause")
async def timer_pause(
    uid: str,
    user: OptionalUser = None,
) -> Response:
    """Pause the global timer."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
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
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


@router.post("/{uid}/timer/reset")
async def timer_reset(
    uid: str,
    user: OptionalUser = None,
) -> Response:
    """Reset the global timer to fresh paused state."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        tournament.timer = TimerState()
        tournament.table_extra_time = {}
        bd = await _save_timer_tx(tournament, tx_conn)
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


class AddTimeRequest(BaseModel):
    table: str  # table index as string key
    seconds: int


@router.post("/{uid}/timer/add-time")
async def timer_add_time(
    uid: str,
    request: AddTimeRequest,
    user: OptionalUser = None,
) -> Response:
    """Add extra time to a specific table."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        if request.seconds <= 0:
            raise HTTPException(status_code=400, detail="Seconds must be positive")
        current = tournament.table_extra_time.get(request.table, 0)
        if current + request.seconds > 600:
            raise HTTPException(
                status_code=400, detail="Max 600s (10 min) extra time per table"
            )
        tournament.table_extra_time[request.table] = current + request.seconds
        bd = await _save_timer_tx(tournament, tx_conn)
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


# ============================================================================
# Judge call endpoint (online-only)
# ============================================================================


class JudgeCallRequest(BaseModel):
    table: int


@router.post("/{uid}/call-judge", status_code=204)
async def call_judge(
    uid: str,
    request: JudgeCallRequest,
    user: OptionalUser = None,
) -> Response:
    """Player calls for judge assistance at their table."""
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
    current_user: OptionalUser = None,
) -> Response:
    """Lock a tournament for offline use on a specific device."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # SELECT FOR UPDATE: serialize the offline-lock get-then-update (TOCTOU)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")

        if not permissions.is_organizer(current_user, tournament):
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

        bd = await save_object(
            ObjectType.TOURNAMENT,
            tournament.uid,
            msgspec.to_builtins(tournament),
            conn=tx_conn,
        )

    logger.info(
        f"Tournament {uid} went offline (device={request.device_id}, user={current_user.uid})"
    )

    broadcast_precomputed(bd)

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
    player_data: OfflinePlayerData,
    tournament_country: str | None,
    organizer_uid: str | None = None,
) -> tuple[str, User]:
    """Resolve an offline player to a real user. Returns (temp_uid, real_user)."""
    # 1. Match by vekn_id (skip temp IDs)
    if player_data.vekn_id and not player_data.vekn_id.startswith("TEMP-"):
        user = await get_user_by_vekn_id(player_data.vekn_id)
        if user:
            return player_data.temp_uid, user

    # 2. Match by email
    if player_data.email:
        auth_method = await get_auth_method_by_identifier("email", player_data.email)
        if auth_method:
            user = await get_user_by_uid(auth_method.user_uid)
            if user:
                # If matched user lacks VEKN ID, allocate one
                if not user.vekn_id:
                    user.vekn_id = await allocate_next_vekn_id()
                    user.coopted_by = organizer_uid
                    user.coopted_at = datetime.now(UTC)
                    user.modified = datetime.now(UTC)
                    bd = await save_object_from_model(ObjectType.USER, user)
                    broadcast_precomputed(bd)
                return player_data.temp_uid, user

    # 3. Create new user with VEKN ID
    now = datetime.now(UTC)
    vekn_id = await allocate_next_vekn_id()
    new_user = User(
        uid=str(uuid7()),
        modified=now,
        name=player_data.name,
        country=tournament_country,
        vekn_id=vekn_id,
        coopted_by=organizer_uid,
        coopted_at=now,
    )
    bd = await save_user(new_user)
    logger.info(
        f"Created user {new_user.uid} (VEKN {vekn_id}) for offline player '{player_data.name}'"
    )

    broadcast_precomputed(bd)

    # Send invite email if provided
    if player_data.email:
        try:
            await send_invite_email(
                player_data.email.lower(), new_user.uid, new_user.name
            )
        except Exception:
            logger.warning(f"Failed to send invite email to {player_data.email}")

    return player_data.temp_uid, new_user


def _remap_uids_in_tournament(tournament_data: dict, uid_map: dict[str, str]) -> dict:
    """Replace all temp_uid references with real UIDs throughout tournament data.

    A whole-JSON byte replace, intentionally: temp UIDs are full 36-char UUIDs,
    so substring collisions are not a practical concern, and this covers every
    UID-bearing field (players, seating, standings, finals seed_order, raffles,
    winner) without having to enumerate — and miss — them. Decks and sanctions are
    flat single objects, so `go_online` repoints their one UID field directly; a
    deck's `attribution` (a vekn, not a UID) is repointed there too.
    """
    raw = msgspec.json.encode(tournament_data)
    for temp_uid, real_uid in uid_map.items():
        raw = raw.replace(temp_uid.encode(), real_uid.encode())
    return msgspec.json.decode(raw)


@router.post("/{uid}/go-online")
async def go_online(
    uid: str,
    request: GoOnlineRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Bring a tournament back online with full reconciliation."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Validate tournament UID matches URL (cheap, request-only — before any side effects)
    if request.tournament.get("uid") and request.tournament["uid"] != uid:
        raise HTTPException(status_code=400, detail="Tournament UID mismatch")
    request.tournament["uid"] = uid  # Force correct UID

    # Pre-lock gate: authorize and pre-check the device lock against current server
    # state BEFORE creating any users, so player resolution (save_user /
    # allocate_next_vekn_id / invite emails) never runs for an unauthorized or
    # wrong-device request. Re-checked authoritatively under the lock below; this
    # unlocked read only fails fast and gates side effects. A tournament created
    # offline may not exist server-side yet (existing is None → no org check, as
    # before).
    existing = await get_tournament_by_uid(uid)
    if existing:
        if not permissions.is_organizer(current_user, existing):
            raise HTTPException(
                status_code=403, detail="Only organizers can bring a tournament online"
            )
        if not existing.offline_mode:
            raise HTTPException(
                status_code=410,
                detail=(
                    "This tournament is no longer in offline mode — it was unlocked "
                    "by an admin or already brought online. Your offline changes "
                    "cannot be synced; reload to get the current state."
                ),
            )
        if (
            existing.offline_mode
            and existing.offline_device_id != request.device_id
            and not request.force
        ):
            raise HTTPException(
                status_code=409,
                detail="Tournament owned by another device. Use force to override.",
            )

    # Resolve offline players → real user accounts. Done OUTSIDE the lock: each
    # resolution may create a user and allocate a VEKN ID (its own advisory-locked
    # transaction), so holding the FOR UPDATE lock here would check out extra
    # pooled connections per player.
    # Benign race: if the caller's organizer rights are revoked between the
    # pre-check and the lock, the authoritative re-check below 403s after these
    # users were created — leaving orphaned (real, coopted) accounts. Acceptable.
    uid_map: dict[str, str] = {}  # temp player UID → resolved user UID
    vekn_remap: dict[
        str, str
    ] = {}  # offline TEMP- vekn → resolved real vekn (deck attribution)
    for player_data in request.offline_players:
        temp_uid, real_user = await _resolve_or_create_offline_player(
            player_data, request.tournament.get("country"), current_user.uid
        )
        uid_map[temp_uid] = real_user.uid
        if (player_data.vekn_id or "").startswith("TEMP-") and real_user.vekn_id:
            vekn_remap[player_data.vekn_id] = real_user.vekn_id

    # If a temp player resolves (by VEKN ID) to someone already in the tournament,
    # or two temps resolve to the same person, the remap below would create a
    # duplicate participant. We deliberately do NOT auto-merge tournament players
    # — fail early so the organizer removes the duplicate registration.
    final_player_uids = [
        uid_map.get(p.get("user_uid"), p.get("user_uid"))
        for p in request.tournament.get("players", [])
    ]
    dupes = {u for u in final_player_uids if u and final_player_uids.count(u) > 1}
    if dupes:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Offline sync would create {len(dupes)} duplicate participant(s) — "
                "the same person is registered both offline and already in the "
                "tournament. Remove the duplicate registration(s) before going online."
            ),
        )

    # SELECT FOR UPDATE: serialize the device-lock check with the save (TOCTOU) so
    # two devices can't both reconcile. A missing row yields None and the upsert
    # below inserts it within the same tx. Holds only tx_conn — no per-player work.
    async with tournament_transaction(uid) as (tournament, tx_conn):
        # Re-verify authorization + device lock authoritatively under the lock.
        if tournament and not permissions.is_organizer(current_user, tournament):
            raise HTTPException(
                status_code=403, detail="Only organizers can bring a tournament online"
            )
        # The server is no longer in offline mode (an IC force-unlocked it, or it
        # was already brought online). Refuse to blind-overwrite the authoritative
        # state with this device's stale offline snapshot — without this guard the
        # device-lock check below is skipped and the upsert clobbers. 410 Gone
        # distinguishes "offline session ended, discard + resync" from the
        # device-mismatch 409 (which offers a force override).
        if tournament and not tournament.offline_mode:
            raise HTTPException(
                status_code=410,
                detail=(
                    "This tournament is no longer in offline mode — it was unlocked "
                    "by an admin or already brought online. Your offline changes "
                    "cannot be synced; reload to get the current state."
                ),
            )
        if tournament and tournament.offline_mode:
            if tournament.offline_device_id != request.device_id and not request.force:
                raise HTTPException(
                    status_code=409,
                    detail="Tournament owned by another device. Use force to override.",
                )

        # Preserve original organizers (prevent client from removing them)
        if tournament:
            original_organizers = tournament.organizers_uids or []
            client_organizers = request.tournament.get("organizers_uids", [])
            merged = list(dict.fromkeys(original_organizers + client_organizers))
            request.tournament["organizers_uids"] = merged

            # Server-managed side-channel fields the offline WASM engine never
            # touches: re-pull them from the locked server row so a value that
            # changed server-side during the offline window (VEKN sync writes
            # external_ids/vekn_pushed_at; a re-uploaded banner_path) isn't
            # reverted by this device's stale snapshot. "Server wins" for
            # non-engine fields, same as organizers_uids above.
            request.tournament["banner_path"] = tournament.banner_path
            request.tournament["external_ids"] = tournament.external_ids
            request.tournament["checkin_code"] = tournament.checkin_code
            request.tournament["vekn_pushed_at"] = (
                tournament.vekn_pushed_at.isoformat()
                if tournament.vekn_pushed_at
                else None
            )

        # Remap temp UIDs → real user UIDs throughout tournament data
        tournament_data = request.tournament
        if uid_map:
            tournament_data = _remap_uids_in_tournament(tournament_data, uid_map)

        # Clear offline fields
        tournament_data["offline_mode"] = False
        tournament_data["offline_device_id"] = ""
        tournament_data["offline_user_uid"] = ""
        tournament_data["offline_since"] = None
        tournament_data["modified"] = datetime.now(UTC).isoformat()

        # Save tournament within the locked transaction (upsert handles insert)
        updated = msgspec.convert(tournament_data, Tournament)
        updated.modified = datetime.now(UTC)
        # A tournament finished offline arrives without a finish date (the
        # engine never stamps it) — use the sync time as the actual end time
        if updated.state == TournamentState.FINISHED and updated.finish is None:
            updated.finish = datetime.now(UTC)
        tournament_bd = await save_object(
            ObjectType.TOURNAMENT,
            updated.uid,
            msgspec.to_builtins(updated),
            conn=tx_conn,
        )

    # --- Transaction committed, row lock released ---
    logger.info(
        f"Tournament {uid} went back online (user={current_user.uid}, remapped={len(uid_map)} players)"
    )

    # 5. Save offline sanctions, repointing the target to the resolved user
    for sanction_data in request.offline_sanctions:
        sanction = msgspec.convert(sanction_data, Sanction)
        sanction.user_uid = uid_map.get(sanction.user_uid, sanction.user_uid)
        bd = await save_sanction(sanction)
        broadcast_precomputed(bd)

    # 6. Save offline decks, repointing the owner and the attribution. A deck's
    # attribution is a vekn (the "designed by" credit), so a temp player's own-deck
    # attribution is their offline TEMP- vekn; repoint it to their resolved real
    # vekn (or drop it if the temp player wasn't resolved).
    for deck_data in request.offline_decks:
        deck_obj = msgspec.convert(deck_data, DeckObject)
        deck_obj.tournament_uid = uid
        deck_obj.user_uid = uid_map.get(deck_obj.user_uid, deck_obj.user_uid)
        if deck_obj.attribution and deck_obj.attribution.startswith("TEMP-"):
            deck_obj.attribution = vekn_remap.get(deck_obj.attribution)
        bd = await save_object_from_model(ObjectType.DECK, deck_obj)
        bd.org_uids = updated.organizers_uids
        broadcast_precomputed(bd)

    # 7. Broadcast updated tournament — but NOT back to the initiating device:
    # it gets the authoritative reconciled tournament in this endpoint's HTTP
    # response (saveTournament), and its own offline_mode=false echo would race
    # ahead of that response and trip the client's lost-lock warning. Only the
    # tournament frame self-excludes; the resolved users / decks / sanctions /
    # ratings broadcasts above intentionally reach the device (it lacks them).
    broadcast_precomputed(tournament_bd, exclude_device_id=request.device_id)

    # An event run+finished offline would otherwise get its rating points only on
    # the next daily recompute (~24h late). Mirror the action route and recompute
    # immediately on go-online so players' ratings reflect the result right away.
    if updated.state == TournamentState.FINISHED:
        try:
            from ..ratings import (
                rating_category_for_tournament,
                recompute_ratings_for_players,
            )

            player_uids = {p.user_uid for p in updated.players if p.user_uid}
            category = rating_category_for_tournament(updated)
            results = await recompute_ratings_for_players(player_uids, category)
            for _user, bd in results:
                broadcast_precomputed(bd)
        except Exception as e:
            logger.error(f"Error recomputing ratings for {uid}: {e}", exc_info=True)

    return Response(content=encoder.encode(updated), media_type="application/json")


class ForceTakeoverRequest(BaseModel):
    device_id: str


@router.post("/{uid}/force-takeover")
async def force_takeover(
    uid: str,
    request: ForceTakeoverRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Transfer offline lock to a new device (any organizer of this tournament)."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # SELECT FOR UPDATE: serialize the offline-lock get-then-update (TOCTOU)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")

        if not permissions.is_organizer(current_user, tournament):
            raise HTTPException(
                status_code=403, detail="Only organizers can force-takeover"
            )

        if not tournament.offline_mode:
            raise HTTPException(
                status_code=400, detail="Tournament is not in offline mode"
            )

        old_device = tournament.offline_device_id
        tournament.offline_device_id = request.device_id
        tournament.offline_user_uid = current_user.uid
        tournament.modified = datetime.now(UTC)

        bd = await save_object(
            ObjectType.TOURNAMENT,
            tournament.uid,
            msgspec.to_builtins(tournament),
            conn=tx_conn,
        )

    logger.info(
        f"Tournament {uid} force-takeover: {old_device} → {request.device_id} by {current_user.uid}"
    )

    broadcast_precomputed(bd)

    return Response(content=encoder.encode(tournament), media_type="application/json")


class SyncOfflineRequest(BaseModel):
    device_id: str
    tournament: dict


@router.post("/{uid}/sync-offline")
async def sync_offline(
    uid: str,
    request: SyncOfflineRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Background data backup for offline tournament. Saves snapshot without unlocking."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # SELECT FOR UPDATE: serialize device-lock check with the snapshot write (TOCTOU)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")

        if not tournament.offline_mode:
            raise HTTPException(
                status_code=400, detail="Tournament is not in offline mode"
            )

        if tournament.offline_device_id != request.device_id:
            raise HTTPException(
                status_code=409, detail="Device does not hold the offline lock"
            )

        # Pin the write to the locked row: the FOR UPDATE lock and device-lock
        # check are keyed on the URL uid, so the snapshot must save there too.
        if request.tournament.get("uid") and request.tournament["uid"] != uid:
            raise HTTPException(status_code=400, detail="Tournament UID mismatch")
        request.tournament["uid"] = uid

        # Save tournament snapshot (keep offline_mode=True)
        tournament_data = request.tournament
        tournament_data["offline_mode"] = True
        tournament_data["offline_device_id"] = tournament.offline_device_id
        tournament_data["offline_user_uid"] = tournament.offline_user_uid
        if tournament.offline_since:
            tournament_data["offline_since"] = tournament.offline_since.isoformat()
        tournament_data["modified"] = datetime.now(UTC).isoformat()

        updated = msgspec.convert(tournament_data, Tournament)
        updated.modified = datetime.now(UTC)
        await save_object(
            ObjectType.TOURNAMENT,
            updated.uid,
            msgspec.to_builtins(updated),
            conn=tx_conn,
        )

    now = datetime.now(UTC)
    logger.info(f"Tournament {uid} offline sync from device {request.device_id}")

    return Response(
        content=encoder.encode({"synced_at": now.isoformat()}),
        media_type="application/json",
    )


@router.post("/{uid}/force-unlock")
async def force_unlock(
    uid: str,
    request: Request,
    current_user: OptionalUser = None,
) -> Response:
    """IC-only emergency unlock. Clears offline mode entirely."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Break-glass: first-party IC sessions only. An OAuth token (even
    # user:impersonate) must not be able to discard another organizer's offline
    # work — get_current_user stamps oauth_client_id on the request for any
    # OAuth token, so its presence flags a delegated credential.
    if getattr(request.state, "oauth_client_id", None):
        raise HTTPException(
            status_code=403, detail="OAuth tokens cannot force-unlock tournaments"
        )

    if Role.IC not in current_user.roles:
        raise HTTPException(
            status_code=403, detail="Only IC can force-unlock tournaments"
        )

    # SELECT FOR UPDATE: serialize the offline-lock get-then-update (TOCTOU)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")

        if not tournament.offline_mode:
            raise HTTPException(
                status_code=400, detail="Tournament is not in offline mode"
            )

        tournament.offline_mode = False
        tournament.offline_device_id = ""
        tournament.offline_user_uid = ""
        tournament.offline_since = None
        tournament.modified = datetime.now(UTC)

        bd = await save_object(
            ObjectType.TOURNAMENT,
            tournament.uid,
            msgspec.to_builtins(tournament),
            conn=tx_conn,
        )

    logger.info(f"Tournament {uid} force-unlocked by IC {current_user.uid}")

    broadcast_precomputed(bd)

    return Response(content=encoder.encode(tournament), media_type="application/json")
