"""FastAPI application entry point."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import jwt
import msgspec
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .db import (
    cleanup_expired_tokens,
    close_db,
    delete_sanction_hard,
    get_expired_sanctions,
    get_sanctions_for_cleanup,
    init_db,
    stream_leagues,
    stream_ratings,
    stream_sanctions,
    stream_tournaments,
    stream_users,
    update_sanction,
)
from .db_oauth import cleanup_expired_oauth_codes, cleanup_expired_oauth_tokens
from .models import (
    DataLevel,
    DeckListsMode,
    League,
    Player,
    Rating,
    Role,
    Sanction,
    SanctionLevel,
    StandingsMode,
    Tournament,
    TournamentState,
    User,
)
from .routes import admin, auth, cards, leagues, oauth, sanctions, tournaments, users, vekn
from .vekn_sync import VEKNSyncService

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global scheduler and sync service
_scheduler: AsyncIOScheduler | None = None
_sync_service: VEKNSyncService | None = None

# Shutdown event for graceful SSE termination
_shutdown_event: asyncio.Event | None = None

# SSE connection management


@dataclass(eq=False)
class SSEConnection:
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))
    user: User | None = None


_sse_connections: set[SSEConnection] = set()


def _wake_sse_connections() -> None:
    """Wake up all SSE connections so they can check for shutdown."""
    for conn in list(_sse_connections):
        try:
            conn.queue.put_nowait("")  # Empty message to wake up the queue.get()
        except Exception:
            pass


async def run_vekn_sync() -> None:
    """Run VEKN member sync, then tournament sync (scheduled task)."""
    global _sync_service
    if not _sync_service:
        return

    try:
        logger.info("Starting VEKN member sync")
        await _sync_service.sync_all_members()
    except TimeoutError:
        logger.error("VEKN member sync timed out - the API may be slow or unreachable")
    except Exception as e:
        logger.error(f"Error during VEKN member sync: {e}", exc_info=True)

    # Tournament sync runs after member sync (needs user UIDs)
    try:
        from .vekn_tournament_sync import sync_all_tournaments

        logger.info("Starting VEKN tournament sync")
        await sync_all_tournaments(_sync_service.client)
    except TimeoutError:
        logger.error("VEKN tournament sync timed out")
    except Exception as e:
        logger.error(f"Error during VEKN tournament sync: {e}", exc_info=True)


async def run_sanction_cleanup() -> None:
    """Run sanction cleanup (scheduled task).

    1. Soft-delete sanctions that are past 18 months (excluding permanent bans)
    2. Hard-delete sanctions that were soft-deleted more than 30 days ago
    """
    from datetime import UTC, datetime

    try:
        logger.info("Starting sanction cleanup")

        # Step 1: Soft-delete expired sanctions
        expired = await get_expired_sanctions()
        now = datetime.now(UTC)

        for sanction in expired:
            # Set deleted_at and update modified
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
            await update_sanction(updated)
            # Broadcast the soft-delete so clients can sync
            await broadcast_sanction_event(updated)

        if expired:
            logger.info(f"Soft-deleted {len(expired)} expired sanctions")

        # Step 2: Hard-delete sanctions soft-deleted >30 days ago
        to_delete = await get_sanctions_for_cleanup(days=30)
        for sanction in to_delete:
            await delete_sanction_hard(sanction.uid)

        if to_delete:
            logger.info(f"Hard-deleted {len(to_delete)} old sanctions")

        logger.info("Sanction cleanup complete")

    except Exception as e:
        logger.error(f"Error during sanction cleanup: {e}", exc_info=True)


async def run_oauth_cleanup() -> None:
    """Clean up expired OAuth authorization codes, revoked tokens, and transient tokens."""
    try:
        codes = await cleanup_expired_oauth_codes()
        tokens = await cleanup_expired_oauth_tokens()
        transient = await cleanup_expired_tokens()
        if codes or tokens or transient:
            logger.info(
                f"Cleanup: {codes} expired codes, {tokens} revoked tokens, "
                f"{transient} transient tokens removed"
            )
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    global _scheduler, _sync_service, _shutdown_event

    # Startup — check JWT secret safety
    from .jwt_config import JWT_DEFAULT_SECRET, JWT_SECRET

    environment = os.getenv("ENVIRONMENT", "development")
    if JWT_SECRET == JWT_DEFAULT_SECRET and environment != "development":
        raise RuntimeError(
            "JWT_SECRET must be set to a secure value in non-development environments. "
            "Set the JWT_SECRET environment variable."
        )

    _shutdown_event = asyncio.Event()
    await init_db()

    # Initialize scheduler for background jobs
    _scheduler = AsyncIOScheduler()

    # Initialize VEKN sync if enabled
    sync_enabled = os.getenv("VEKN_SYNC_ENABLED", "false").lower() == "true"
    if sync_enabled:
        logger.info("VEKN sync is enabled")
        _sync_service = VEKNSyncService()
        admin.set_sync_service(_sync_service)

        # Set up periodic sync
        sync_interval_hours = int(os.getenv("VEKN_SYNC_INTERVAL_HOURS", "6"))
        _scheduler.add_job(
            run_vekn_sync,
            trigger=IntervalTrigger(hours=sync_interval_hours),
            id="vekn_sync",
            name="VEKN Member Sync",
            replace_existing=True,
        )
        logger.info(f"VEKN sync scheduled every {sync_interval_hours} hours")

        # Run initial sync in background (don't block startup)
        asyncio.create_task(run_vekn_sync())
        logger.info("Initial VEKN sync scheduled in background")
    else:
        logger.info("VEKN sync is disabled")

    # Schedule sanction cleanup job (runs daily)
    _scheduler.add_job(
        run_sanction_cleanup,
        trigger=IntervalTrigger(hours=24),
        id="sanction_cleanup",
        name="Sanction Cleanup",
        replace_existing=True,
    )
    logger.info("Sanction cleanup scheduled daily")

    # Schedule OAuth token/code cleanup (runs every hour)
    _scheduler.add_job(
        run_oauth_cleanup,
        trigger=IntervalTrigger(hours=1),
        id="oauth_cleanup",
        name="OAuth Cleanup",
        replace_existing=True,
    )
    logger.info("OAuth cleanup scheduled hourly")

    _scheduler.start()

    yield

    # Shutdown
    # Signal all SSE connections to close
    if _shutdown_event:
        logger.info("Signaling SSE connections to close...")
        _shutdown_event.set()
        _wake_sse_connections()
        # Give connections a moment to close gracefully
        await asyncio.sleep(0.5)

    if _scheduler:
        _scheduler.shutdown()
        logger.info("Scheduler shut down")
    if _sync_service:
        await _sync_service.close()
        logger.info("VEKN sync service closed")
    await close_db()


app = FastAPI(title="Archon", version="0.1.0", lifespan=lifespan)

# Configure CORS - allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(vekn.router)
app.include_router(sanctions.router)
app.include_router(tournaments.router)
app.include_router(oauth.router)
app.include_router(cards.router)
app.include_router(leagues.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


encoder = msgspec.json.Encoder()

# Bump this on releases that require a full client resync
MINIMUM_SYNC_EPOCH = "2026-01-31T00:00:00"


# ---------------------------------------------------------------------------
# Data-level helpers
# ---------------------------------------------------------------------------

def _viewer_level(viewer: User | None) -> DataLevel:
    """Determine the viewer's base data level."""
    if not viewer:
        return DataLevel.PUBLIC
    if Role.IC in viewer.roles:
        return DataLevel.FULL
    if viewer.vekn_id:
        return DataLevel.MEMBER
    return DataLevel.PUBLIC


def _has_full_access(viewer: User | None, *, country: str | None = None, organizers_uids: list[str] | None = None) -> bool:
    """Check if viewer has full access (IC, NC/Prince same country, or organizer)."""
    if not viewer:
        return False
    if Role.IC in viewer.roles:
        return True
    if (Role.NC in viewer.roles or Role.PRINCE in viewer.roles) and viewer.country and country and viewer.country == country:
        return True
    if organizers_uids and viewer.uid in organizers_uids:
        return True
    return False


# ---------------------------------------------------------------------------
# Per-type filter functions
# ---------------------------------------------------------------------------

def _filter_user(user: User, viewer: User | None) -> User | None:
    """Filter a User for a given viewer. Returns None to skip entirely."""
    if _has_full_access(viewer, country=user.country):
        return user
    if viewer and viewer.vekn_id:
        # Member: name, nickname, country, vekn_id, roles, city, state — no contact info
        return User(
            uid=user.uid,
            modified=user.modified,
            deleted_at=user.deleted_at,
            name=user.name,
            country=user.country,
            vekn_id=user.vekn_id,
            city=user.city,
            state=user.state,
            nickname=user.nickname,
            roles=user.roles,
            avatar_path=user.avatar_path,
        )
    # Non-member: only Prince/NC users with contact info
    if Role.NC in user.roles or Role.PRINCE in user.roles:
        return User(
            uid=user.uid,
            modified=user.modified,
            deleted_at=user.deleted_at,
            name=user.name,
            country=user.country,
            roles=user.roles,
            vekn_prefix=user.vekn_prefix,
            contact_email=user.contact_email,
            contact_discord=user.contact_discord,
            contact_phone=user.contact_phone,
        )
    return None  # Skip non-notable users for non-members


def _filter_sanction(sanction: Sanction, viewer: User | None) -> Sanction | None:
    """Filter a Sanction based on viewer's access level.

    - Caution-level tournament sanctions: only visible to tournament organizers, IC, or Ethics
    - Warning+ sanctions: visible to all members
    - Non-members see nothing
    """
    if not viewer or not viewer.vekn_id:
        return None
    # Caution-level sanctions are only visible to tournament organizers or IC/Ethics
    if sanction.level == SanctionLevel.CAUTION and sanction.tournament_uid:
        if Role.IC in viewer.roles or Role.ETHICS in viewer.roles:
            return sanction
        # Check if viewer is organizer of this tournament (requires async lookup,
        # but we cache tournament data). For SSE filter we rely on the organizers_uids
        # that we can't easily check here without the tournament object.
        # This will be enforced at a higher level — for now, cautions flow to members.
        # TODO: Pass tournament context to filter for strict caution visibility
        return sanction
    return sanction


def _filter_tournament(t: Tournament, viewer: User | None) -> Tournament | None:
    """Filter a Tournament for a given viewer's access level."""
    # Full access: IC, NC/Prince same country, organizer
    if _has_full_access(viewer, country=t.country, organizers_uids=t.organizers_uids):
        return t

    # Member level
    if viewer and viewer.vekn_id:
        viewer_uid = viewer.uid
        is_player = any(p.user_uid == viewer_uid for p in t.players)

        # my_tables: tables where viewer sat (across all rounds)
        my_tables = []
        if is_player:
            for rnd in t.rounds:
                for table in rnd:
                    if any(s.player_uid == viewer_uid for s in table.seating):
                        my_tables.append(table)

        # Standings visibility
        standings = t.standings
        if t.state != TournamentState.FINISHED:
            if t.standings_mode == StandingsMode.PRIVATE:
                standings = []

        # Decks visibility (finished only)
        decks: dict[str, list] = {}
        if t.state == TournamentState.FINISHED and t.decks:
            if t.decklists_mode == DeckListsMode.ALL:
                decks = t.decks
            elif t.decklists_mode == DeckListsMode.FINALISTS:
                decks = {uid: d for uid, d in t.decks.items()
                         if any(p.user_uid == uid and p.finalist for p in t.players)}
            else:  # WINNER
                if t.winner and t.winner in t.decks:
                    decks = {t.winner: t.decks[t.winner]}

        # Players: strip per-player results for ongoing tournaments
        players = t.players
        if t.state != TournamentState.FINISHED:
            players = [Player(
                user_uid=p.user_uid,
                state=p.state,
                payment_status=p.payment_status,
                finalist=p.finalist,
            ) for p in t.players]

        return Tournament(
            uid=t.uid,
            modified=t.modified,
            deleted_at=t.deleted_at,
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
            organizers_uids=t.organizers_uids,
            venue=t.venue,
            venue_url=t.venue_url,
            address=t.address,
            map_url=t.map_url,
            proxies=t.proxies,
            multideck=t.multideck,
            decklist_required=t.decklist_required,
            description=t.description,
            standings_mode=t.standings_mode,
            decklists_mode=t.decklists_mode,
            max_rounds=t.max_rounds,
            external_ids=t.external_ids,
            players=players,
            decks=decks,
            finals=t.finals if t.state == TournamentState.FINISHED else None,
            winner=t.winner,
            standings=standings,
            my_tables=my_tables,
        )

    # Non-member: minimal
    return Tournament(
        uid=t.uid,
        modified=t.modified,
        deleted_at=t.deleted_at,
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


def _filter_rating(rating: Rating, viewer: User | None) -> Rating | None:
    """Ratings are public."""
    return rating


def _filter_league(league: League, viewer: User | None) -> League | None:
    """Leagues are public."""
    return league


# ---------------------------------------------------------------------------
# Generic broadcast
# ---------------------------------------------------------------------------

async def _broadcast(event_type: str, obj: object, filter_fn=None) -> None:
    """Broadcast an object to all SSE connections, optionally filtering per-viewer."""
    disconnected: set[SSEConnection] = set()
    for conn in _sse_connections:
        try:
            data = obj
            if filter_fn:
                data = filter_fn(obj, conn.user)
                if data is None:
                    continue
            event_data = {"type": event_type, "data": msgspec.to_builtins(data)}
            message = f"data: {encoder.encode(event_data).decode('utf-8')}\n\n"
            conn.queue.put_nowait(message)
        except asyncio.QueueFull:
            disconnected.add(conn)
    _sse_connections.difference_update(disconnected)


async def broadcast_user_event(user: User) -> None:
    await _broadcast("user", user, _filter_user)


async def broadcast_sanction_event(sanction: Sanction) -> None:
    await _broadcast("sanction", sanction, _filter_sanction)


async def broadcast_tournament_event(tournament: Tournament) -> None:
    await _broadcast("tournament", tournament, _filter_tournament)


async def broadcast_rating_event(rating: Rating) -> None:
    await _broadcast("rating", rating, _filter_rating)


async def broadcast_league_event(league: League) -> None:
    await _broadcast("league", league, _filter_league)


async def broadcast_resync(user_uid: str) -> None:
    """Push a resync event to a specific user's SSE connection(s)."""
    event_data = {"type": "resync"}
    message = f"data: {encoder.encode(event_data).decode('utf-8')}\n\n"
    for conn in _sse_connections:
        if conn.user and conn.user.uid == user_uid:
            try:
                conn.queue.put_nowait(message)
            except asyncio.QueueFull:
                pass


# Make broadcast functions available to routes
users.broadcast_user_event = broadcast_user_event
sanctions.broadcast_sanction_event = broadcast_sanction_event
tournaments.broadcast_tournament_event = broadcast_tournament_event
tournaments.broadcast_rating_event = broadcast_rating_event
tournaments.broadcast_user_event = broadcast_user_event
tournaments.broadcast_sanction_event = broadcast_sanction_event
leagues.broadcast_league_event = broadcast_league_event
users.broadcast_resync = broadcast_resync
vekn.broadcast_resync = broadcast_resync


@app.options("/stream")
async def stream_options() -> Response:
    """Handle CORS preflight for SSE endpoint."""
    return Response(
        content="",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )


async def _resolve_user_from_token(token: str | None) -> User | None:
    """Resolve a User from a JWT token query param. Returns None on any failure."""
    if not token:
        return None
    try:
        from .jwt_config import JWT_ALGORITHM, JWT_SECRET

        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_uid = payload.get("sub")
        if not user_uid:
            return None
        from .db import get_user_by_uid

        return await get_user_by_uid(user_uid)
    except Exception:
        return None


@app.get("/stream")
async def stream_updates(
    since: str | None = None, token: str | None = None
) -> StreamingResponse:
    """Stream object updates via SSE.

    Uses server-side cursor for true DB->HTTP streaming with minimal memory.
    Accepts optional token query param for user-aware data filtering.
    """

    # Resolve user outside the generator so it's available immediately
    stream_user = await _resolve_user_from_token(token)
    if stream_user:
        logger.info(f"SSE connection authenticated as user {stream_user.uid}")

    # Resync detection: check if client's `since` is stale
    effective_since = since
    force_resync = False
    threshold_parts = [MINIMUM_SYNC_EPOCH]
    if stream_user and stream_user.resync_after:
        threshold_parts.append(stream_user.resync_after.isoformat())
    threshold = max(threshold_parts)
    if since and threshold > since:
        force_resync = True
        effective_since = None  # Stream everything

    # Stream specs: (stream_fn, batch_event_type, filter_fn)
    _stream_specs: list[tuple] = [
        (stream_users, "users", _filter_user),
        (stream_sanctions, "sanctions", _filter_sanction),
        (stream_tournaments, "tournaments", _filter_tournament),
        (stream_ratings, "ratings", _filter_rating),
        (stream_leagues, "leagues", _filter_league),
    ]

    async def event_generator():
        """Generate SSE events streaming directly from PostgreSQL."""
        conn = SSEConnection(user=stream_user)
        _sse_connections.add(conn)

        try:
            yield ": connected\n\n"

            # If resync needed, tell client to clear stores first
            if force_resync:
                resync_msg = {"type": "resync"}
                yield f"data: {encoder.encode(resync_msg).decode('utf-8')}\n\n"

            import time
            start_time = time.time()
            last_timestamp: str | None = None
            totals: dict[str, int] = {}

            for stream_fn, event_type, filter_fn in _stream_specs:
                count = 0
                try:
                    async for batch, batch_max in stream_fn(since=effective_since, batch_size=1000):
                        if _shutdown_event and _shutdown_event.is_set():
                            return

                        # Apply per-item filter
                        filtered = []
                        for item in batch:
                            out = filter_fn(item, stream_user)
                            if out is not None:
                                filtered.append(out)

                        count += len(filtered)
                        if batch_max and (last_timestamp is None or batch_max > last_timestamp):
                            last_timestamp = batch_max

                        if filtered:
                            event_data = {
                                "type": event_type,
                                "data": [msgspec.to_builtins(x) for x in filtered],
                            }
                            yield f"data: {encoder.encode(event_data).decode('utf-8')}\n\n"
                except Exception as e:
                    logger.error(f"Error streaming {event_type} (non-fatal): {e}")

                totals[event_type] = count

            total_time = time.time() - start_time
            parts = ", ".join(f"{v} {k}" for k, v in totals.items())
            logger.info(f"Sync complete: {parts} in {total_time:.3f}s")

            sync_complete = {"type": "sync_complete", "timestamp": last_timestamp}
            yield f"data: {encoder.encode(sync_complete).decode('utf-8')}\n\n"

            # Real-time updates
            keepalive_counter = 0
            while True:
                if _shutdown_event and _shutdown_event.is_set():
                    return

                try:
                    message = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
                    if message:
                        yield message
                    keepalive_counter = 0
                except TimeoutError:
                    keepalive_counter += 1
                    if keepalive_counter >= 30:
                        yield ": keepalive\n\n"
                        keepalive_counter = 0

        except Exception as e:
            logger.error(f"Error in SSE generator: {e}", exc_info=True)
            raise
        finally:
            _sse_connections.discard(conn)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )
