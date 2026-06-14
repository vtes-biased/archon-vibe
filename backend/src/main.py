"""FastAPI application entry point."""

import asyncio
import logging
import os
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import jwt
import msgspec
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .broadcast import (
    SSEConnection,
    _sse_connections,
    _wake_sse_connections,
    broadcast_precomputed,
    encoder,
)
from .db import (
    cleanup_expired_tokens,
    close_db,
    delete_sanction_hard,
    get_expired_sanctions,
    get_sanctions_for_cleanup,
    init_db,
    save_sanction,
)
from .db_oauth import cleanup_expired_oauth_codes, cleanup_expired_oauth_tokens
from .engine_errors import EngineRejection
from .middleware.auth import get_current_user
from .models import (
    DataLevel,
    ObjectType,
    Role,
    User,
)
from .routes import (
    admin,
    auth,
    calendar,
    cards,
    leagues,
    oauth,
    sanctions,
    tournaments,
    users,
    vekn,
)
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


def _install_fast_shutdown_signals() -> None:
    """Flip _shutdown_event the instant SIGTERM/SIGINT arrives so the long-lived
    /stream generators self-close within ~1s instead of stalling the restart.

    uvicorn shuts down gracefully on these signals, but its lifespan-shutdown —
    where _shutdown_event would otherwise be set — runs only AFTER it has drained
    open connections. The SSE generators never end on their own, so that signal
    arrives too late and the drain blocks until --timeout-graceful-shutdown (or,
    absent that, systemd's SIGKILL at TimeoutStopSec) cuts it off. Setting the
    event from the signal handler itself — before uvicorn's handler flips
    should_exit and the loop begins the drain — lets the generators (which poll
    it every <=1s) return promptly, so the drain finishes in ~1s instead of
    waiting out the graceful timeout.

    Mechanism (version-coupled): uvicorn installs handle_exit via plain
    signal.signal (its capture_signals()), so signal.getsignal() returns that
    real handler for us to chain. We run inside the same synchronous signal
    invocation — set the event first, then call uvicorn's handler (which only
    sets should_exit) — so the event is provably set before the loop drains. If
    uvicorn ever switched to loop.add_signal_handler, getsignal() would return
    asyncio's no-op instead and this chain would silently stop driving uvicorn's
    shutdown; revisit then.

    Only Event.set() is touched here, and no coroutine ever waits on
    _shutdown_event (the generators only read .is_set()), so set() is a plain
    attribute write with no loop interaction — safe from a signal handler.
    """

    def _make_handler(prev):
        def _handler(signum, frame):
            if _shutdown_event is not None:
                _shutdown_event.set()
            if callable(prev):
                prev(signum, frame)

        return _handler

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _make_handler(signal.getsignal(sig)))
        except ValueError:
            # Not in the main thread (e.g. Starlette TestClient) — uvicorn didn't
            # install its handlers here either, so there is nothing to accelerate.
            pass


async def run_member_sync() -> None:
    """VEKN member sync with status recording (vekn_status).

    Shared by the scheduled run and the admin 'Run now' endpoint, so both record
    the same member_sync health and the manual trigger stays a quick dispatch.
    """
    if not _sync_service:
        return

    from .vekn_status import record_error, record_success

    try:
        stats = await _sync_service.sync_all_members()
        record_success("member_sync", stats if isinstance(stats, dict) else None)
    except TimeoutError:
        logger.error("VEKN member sync timed out - the API may be slow or unreachable")
        record_error("member_sync", "timed out — API slow or unreachable")
    except Exception as e:
        logger.error(f"Error during VEKN member sync: {e}", exc_info=True)
        record_error("member_sync", str(e))


async def run_tournament_sync() -> None:
    """VEKN tournament sync with status recording (vekn_status).

    Shared by the scheduled run and the admin 'Run now' endpoint.
    """
    if not _sync_service:
        return

    from .vekn_status import record_error, record_success

    try:
        from .vekn_tournament_sync import sync_all_tournaments

        stats = await sync_all_tournaments(_sync_service.client)
        record_success("tournament_sync", stats if isinstance(stats, dict) else None)
    except TimeoutError:
        logger.error("VEKN tournament sync timed out")
        record_error("tournament_sync", "timed out")
    except Exception as e:
        logger.error(f"Error during VEKN tournament sync: {e}", exc_info=True)
        record_error("tournament_sync", str(e))


async def run_vekn_sync() -> None:
    """Full scheduled chain: members → tournaments → TWDA → ratings → snapshot."""
    if not _sync_service:
        return

    await run_member_sync()
    # Tournament sync runs after member sync (needs user UIDs).
    await run_tournament_sync()

    # Import TWDA winner decklists for matched tournaments
    try:
        from .twda_import import import_twda_decks

        logger.info("Starting TWDA deck import")
        stats = await import_twda_decks()
        logger.info(f"TWDA deck import: {stats}")
    except Exception as e:
        logger.error(f"Error during TWDA deck import: {e}", exc_info=True)

    # Recompute ratings after tournaments are up to date
    await run_rating_recompute()

    # Generate snapshot after all data is up to date
    await run_snapshot_generation()


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
            updated = msgspec.structs.replace(sanction, modified=now, deleted_at=now)
            bd = await save_sanction(updated)
            # Broadcast the soft-delete so clients can sync
            broadcast_precomputed(bd)

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


async def run_rating_recompute() -> None:
    """Full recomputation of all ratings and wins (scheduled daily).

    Ratings are now embedded in User objects, so we broadcast user events.
    """
    try:
        from .ratings import recompute_all_ratings

        logger.info("Starting daily rating recompute")
        results = await recompute_all_ratings()
        for _user, bd in results:
            broadcast_precomputed(bd)
        logger.info(f"Daily rating recompute complete: {len(results)} users updated")
    except Exception as e:
        logger.error(f"Error during rating recompute: {e}", exc_info=True)


async def run_vekn_push() -> None:
    """Run VEKN push batch (scheduled task)."""
    from .vekn_status import record_error, record_success

    try:
        from .vekn_push import batch_push, vekn_push_client

        async with vekn_push_client() as client:
            if client is None:
                return
            logger.info("Starting VEKN batch push")
            stats = await batch_push(client)
            logger.info(f"VEKN batch push complete: {stats}")
            if stats.get("aborted"):
                record_error("batch_push", "aborted — VEKN unreachable")
            else:
                record_success("batch_push", stats)
    except Exception as e:
        logger.error(f"Error during VEKN batch push: {e}", exc_info=True)
        record_error("batch_push", str(e))


async def run_snapshot_generation() -> None:
    """Generate access-level snapshots (scheduled every 15 minutes)."""
    try:
        from .snapshots import generate_snapshots

        stats = await generate_snapshots()
        logger.info(f"Snapshots generated: {stats}")
    except Exception as e:
        logger.error(f"Error generating snapshots: {e}", exc_info=True)


async def run_purge_deleted_objects() -> None:
    """Hard-delete objects that were soft-deleted more than 30 days ago."""
    try:
        from .db import purge_deleted_objects

        count = await purge_deleted_objects(days=30)
        if count:
            logger.info(f"Purged {count} soft-deleted objects")
    except Exception as e:
        logger.error(f"Error purging deleted objects: {e}", exc_info=True)


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

    # Check cards.json availability
    cards_data, _ = cards._load_cards()
    if cards_data is None:
        logger.warning(
            "engine/data/cards.json not found — card database unavailable. "
            "Run: python scripts/update_cards.py"
        )

    _shutdown_event = asyncio.Event()
    _install_fast_shutdown_signals()
    await init_db()

    # Register Discord Linked Roles metadata (idempotent)
    if os.getenv("DISCORD_CLIENTID"):
        try:
            from .roles_hook import register_metadata

            await register_metadata()
        except Exception:
            logger.exception("Failed to register Discord Linked Roles metadata")

    # Initialize scheduler for background jobs
    _scheduler = AsyncIOScheduler()

    # Initialize VEKN sync if enabled
    sync_enabled = os.getenv("VEKN_SYNC_ENABLED", "false").lower() == "true"
    if sync_enabled:
        logger.info("VEKN sync is enabled")
        _sync_service = VEKNSyncService()
        admin.set_sync_service(_sync_service)
        # Recorded runners the admin 'Run now' dispatches in the background
        # (instead of awaiting the multi-minute sync inline in the request).
        admin.set_sync_runners(
            member_sync=run_member_sync, tournament_sync=run_tournament_sync
        )

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

    # Schedule daily rating recompute (consistency check)
    _scheduler.add_job(
        run_rating_recompute,
        trigger=IntervalTrigger(hours=24),
        id="rating_recompute",
        name="Rating Recompute",
        replace_existing=True,
    )
    logger.info("Rating recompute scheduled daily (initial run after VEKN sync)")

    # Schedule VEKN push batch (runs hourly if VEKN_PUSH enabled)
    if os.getenv("VEKN_PUSH", "").lower() == "true":
        push_interval = int(os.getenv("VEKN_PUSH_INTERVAL_HOURS", "1"))
        _scheduler.add_job(
            run_vekn_push,
            trigger=IntervalTrigger(hours=push_interval),
            id="vekn_push",
            name="VEKN Push",
            replace_existing=True,
        )
        logger.info(f"VEKN push scheduled every {push_interval} hours")

    # Schedule OAuth token/code cleanup (runs every hour)
    _scheduler.add_job(
        run_oauth_cleanup,
        trigger=IntervalTrigger(hours=1),
        id="oauth_cleanup",
        name="OAuth Cleanup",
        replace_existing=True,
    )
    logger.info("OAuth cleanup scheduled hourly")

    # Schedule snapshot generation (every 15 minutes)
    _scheduler.add_job(
        run_snapshot_generation,
        trigger=IntervalTrigger(minutes=15),
        id="snapshot_gen",
        name="Snapshot Generation",
        replace_existing=True,
    )
    logger.info("Snapshot generation scheduled every 15 minutes")

    # Schedule purge of soft-deleted objects (runs daily)
    _scheduler.add_job(
        run_purge_deleted_objects,
        trigger=IntervalTrigger(hours=24),
        id="purge_deleted",
        name="Purge Deleted Objects",
        replace_existing=True,
    )
    logger.info("Purge of deleted objects scheduled daily")

    # Generate initial snapshot (if VEKN sync disabled; otherwise run_vekn_sync handles it)
    if not sync_enabled:
        asyncio.create_task(run_snapshot_generation())

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


@app.exception_handler(EngineRejection)
async def engine_rejection_handler(request, exc: EngineRejection) -> JSONResponse:
    """Engine domain rejection: detail stays a human string (bot/legacy clients),
    code+params are additive for frontend i18n (#107)."""
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "code": exc.code, "params": exc.params},
    )


# CORS: only needed in development (nginx handles it in production)
if os.getenv("ENVIRONMENT", "development") == "development":
    from fastapi.middleware.cors import CORSMiddleware

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
app.include_router(calendar.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


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


async def _resolve_viewer(
    request: Request, token: str | None, authorization: str | None
) -> User | None:
    """Resolve the SSE/snapshot viewer. The bot sends an `Authorization` header
    (revocation-aware, oauth-aware via get_current_user); the browser EventSource
    can't set headers and passes a `token` query param. A supplied-but-invalid
    credential raises 401; only a wholly absent one yields None (anonymous public).
    """
    if authorization and authorization.startswith("Bearer "):
        return await get_current_user(request, authorization)
    if token:
        viewer = await _resolve_user_from_token(token)
        if viewer is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token",
                headers={"Cache-Control": "no-cache"},
            )
        return viewer
    return None


@app.get("/snapshot")
async def get_snapshot(
    request: Request,
    token: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Serve pre-computed gzip snapshot for the viewer's access level.

    In dev: reads file from disk and streams directly.
    In prod: would use X-Accel-Redirect for nginx to serve the file.
    """
    from .snapshots import get_snapshot_path

    viewer = await _resolve_viewer(request, token, authorization)
    level = _viewer_level(viewer)

    snapshot_path = get_snapshot_path(level.value)
    if not snapshot_path:
        return Response(
            content='{"error":"snapshot not available yet"}',
            status_code=503,
            media_type="application/json",
            headers={"Retry-After": "60"},
        )

    # Read and serve the gzip file directly
    data = snapshot_path.read_bytes()
    return Response(
        content=data,
        media_type="application/json",
        headers={
            "Content-Encoding": "gzip",
            "Cache-Control": "no-cache",
        },
    )


# ---------------------------------------------------------------------------
# SSE stream types for catch-up
# ---------------------------------------------------------------------------
_STREAM_TYPES = list(ObjectType)

# Max bytes of joined object JSON packed into a single SSE `data:` line. The
# browser EventSource has no per-line cap, but the Discord bot's aiohttp
# StreamReader rejects any line over 512KB ("Got more than 524288 bytes when
# reading"), so an unbounded catch-up frame (all objects of a type in one line)
# crash-loops the bot. Keep frames well under that limit. A single object larger
# than the budget is emitted alone (never split).
_SSE_LINE_BUDGET = 200_000


def _sse_object_lines(batch_type: str, json_strings: list[str]):
    """Yield SSE `data:` frames for `json_strings`, each payload under the byte
    budget so no single line exceeds the bot client's StreamReader limit.

    Sizes by UTF-8 byte length (not str length) — the 512KB limit is in bytes,
    so multibyte names (CJK/accents) must count for what they weigh on the wire.
    """
    batch: list[str] = []
    size = 0
    for s in json_strings:
        s_bytes = len(s.encode()) + 1  # +1 for the joining comma
        if batch and size + s_bytes > _SSE_LINE_BUDGET:
            yield f'data: {{"type":"{batch_type}","data":[{",".join(batch)}]}}\n\n'
            batch, size = [], 0
        batch.append(s)
        size += s_bytes
    if batch:
        yield f'data: {{"type":"{batch_type}","data":[{",".join(batch)}]}}\n\n'


async def _participant_user_frames(
    db_conn, tournament_uid: str, sent: set[str]
) -> list[str]:
    """Member-level identity frames for a tournament's participants not in `sent`.

    The bot's tournament-scoped stream otherwise carries no user objects (see
    broadcast._scope_matches), so it can't resolve seated players' names. This
    pushes each participant's User object (player user_uids + organizers) so the
    bot renders names/nicknames; `sent` dedups across calls and is mutated here.

    Sends the MEMBER column for ALL participants regardless of viewer
    entitlement — deliberately NOT entitled_level. The bot needs only
    name/nickname (both in member); routing through entitled_level would upgrade
    an organizer viewer to `full` and stream participant CONTACT INFO to the
    Discord process. Member is the minimal projection that carries identity.

    Caller passes an open pooled connection (catch-up reuses its own; the live
    refresh opens+releases one) — never yield while holding the pool.
    """
    row = await (
        await db_conn.execute(
            'SELECT "full"::text FROM objects WHERE uid = %s AND type = %s '
            "AND deleted_at IS NULL",
            (tournament_uid, ObjectType.TOURNAMENT),
        )
    ).fetchone()
    if not row or not row[0]:
        return []
    t = msgspec.json.decode(row[0].encode())
    uids = {p["user_uid"] for p in t.get("players", []) if p.get("user_uid")}
    uids |= set(t.get("organizers_uids") or [])
    new_uids = [u for u in uids if u not in sent]
    if not new_uids:
        return []
    urows = await (
        await db_conn.execute(
            "SELECT member::text FROM objects WHERE type = %s "
            "AND uid = ANY(%s) AND deleted_at IS NULL",
            (ObjectType.USER, new_uids),
        )
    ).fetchall()
    # Mark all attempted uids sent (incl. any without a member row) so a steady
    # stream of roster-unchanged tournament events does no further DB work.
    sent.update(new_uids)
    return list(_sse_object_lines("users", [r[0] for r in urows if r[0]]))


async def _scoped_catchup_frames(
    viewer, tournament_uid: str, sent: set[str]
) -> tuple[list[str], str | None]:
    """Catch-up frames for a tournament-scoped SSE connection.

    Returns (frames, last_modified_at) for the one tournament + its sanctions +
    its participants' identities, each at the viewer's entitled projection (the
    same access rule the live broadcast uses). Far smaller than the full-corpus
    catch-up — this is what lets the bot watch a tournament without streaming the
    whole database. Seeds `sent` with the participant uids it emits so the first
    live tournament event doesn't re-send everyone.
    """
    from .broadcast import entitled_level
    from .db import _pool

    frames: list[str] = []
    last_ts: str | None = None
    if not _pool:
        return frames, last_ts

    async with _pool.connection() as conn:
        row = await (
            await conn.execute(
                'SELECT public::text, member::text, "full"::text, modified_at '
                "FROM objects WHERE uid = %s AND type = %s AND deleted_at IS NULL",
                (tournament_uid, ObjectType.TOURNAMENT),
            )
        ).fetchone()
        if row and row[2]:
            full_dict = msgspec.json.decode(row[2].encode())
            level = entitled_level(
                viewer,
                obj_type=ObjectType.TOURNAMENT,
                uid=tournament_uid,
                country=full_dict.get("country"),
                org_uids=full_dict.get("organizers_uids"),
                obj_user_uid=None,
            )
            col = {"public": row[0], "member": row[1], "full": row[2]}.get(level)
            if col:
                frames.append(f'data: {{"type":"tournament","data":{col}}}\n\n')
                if row[3]:
                    last_ts = row[3].isoformat()

        # Sanctions are an identity projection (full content at member/full,
        # nothing at public), so the level is viewer-only — compute it once.
        sanction_level = entitled_level(
            viewer,
            obj_type=ObjectType.SANCTION,
            uid="",
            country=None,
            org_uids=None,
            obj_user_uid=None,
        )
        srows = await (
            await conn.execute(
                'SELECT public::text, member::text, "full"::text, modified_at '
                "FROM objects WHERE type = %s "
                "AND \"full\"->>'tournament_uid' = %s AND deleted_at IS NULL "
                "ORDER BY modified_at ASC",
                (ObjectType.SANCTION, tournament_uid),
            )
        ).fetchall()
        sjson: list[str] = []
        for sr in srows:
            col = {"public": sr[0], "member": sr[1], "full": sr[2]}.get(sanction_level)
            if col:
                sjson.append(col)
            if sr[3] and (last_ts is None or sr[3].isoformat() > last_ts):
                last_ts = sr[3].isoformat()
        frames.extend(_sse_object_lines("sanctions", sjson))

        # Reuse this same pooled connection (no second acquisition) to seed the
        # bot with participant identities; mutates `sent` for the live diff.
        frames.extend(await _participant_user_frames(conn, tournament_uid, sent))

    return frames, last_ts


async def _overlay_frames(viewer) -> tuple[list[str], int]:
    """Personal-overlay frames for a member connection: own profile/decks at full
    level, plus NC/Prince same-country and organizer full data.

    Buffers every frame while holding ONE pooled connection, then returns them so
    the caller can release the connection BEFORE draining to the client. Yielding
    inside `async with _pool.connection()` would pin the slot for the whole client
    read and, on a mid-drain disconnect, return an ACTIVE connection to the pool
    (which then fails its reset-rollback and is discarded). Mirrors
    _scoped_catchup_frames.
    """
    from .db import _pool

    frames: list[str] = []
    count = 0
    if not _pool:
        return frames, count

    async with _pool.connection() as db_conn:
        # Own user profile at full level
        row = await (
            await db_conn.execute(
                'SELECT "full"::text FROM objects WHERE uid = %s AND type = %s',
                (viewer.uid, ObjectType.USER),
            )
        ).fetchone()
        if row and row[0]:
            frames.append(f'data: {{"type":"user","data":{row[0]}}}\n\n')
            count += 1

        # Own decks at full level (even if member=null)
        rows = await (
            await db_conn.execute(
                'SELECT "full"::text FROM objects WHERE type = %s '
                "AND \"full\"->>'user_uid' = %s AND deleted_at IS NULL",
                (ObjectType.DECK, viewer.uid),
            )
        ).fetchall()
        if rows:
            frames.extend(_sse_object_lines("decks", [r[0] for r in rows]))
            count += len(rows)

        # NC/Prince: full for same-country users + tournaments
        if viewer.country and (Role.NC in viewer.roles or Role.PRINCE in viewer.roles):
            rows = await (
                await db_conn.execute(
                    'SELECT "full"::text FROM objects WHERE type = %s '
                    "AND \"full\"->>'country' = %s AND deleted_at IS NULL",
                    (ObjectType.USER, viewer.country),
                )
            ).fetchall()
            if rows:
                frames.extend(_sse_object_lines("users", [r[0] for r in rows]))
                count += len(rows)

            rows = await (
                await db_conn.execute(
                    'SELECT "full"::text FROM objects WHERE type = %s '
                    "AND \"full\"->>'country' = %s AND deleted_at IS NULL",
                    (ObjectType.TOURNAMENT, viewer.country),
                )
            ).fetchall()
            if rows:
                frames.extend(_sse_object_lines("tournaments", [r[0] for r in rows]))
                count += len(rows)

        # Organizer: full for organized tournaments + their decks
        rows = await (
            await db_conn.execute(
                'SELECT uid, "full"::text FROM objects WHERE type = %s '
                "AND \"full\"->'organizers_uids' ? %s AND deleted_at IS NULL",
                (ObjectType.TOURNAMENT, viewer.uid),
            )
        ).fetchall()
        if rows:
            t_uids = [r[0] for r in rows]
            frames.extend(_sse_object_lines("tournaments", [r[1] for r in rows]))
            count += len(rows)

            # Decks for organized tournaments (single IN query)
            placeholders = ", ".join(["%s"] * len(t_uids))
            deck_rows = await (
                await db_conn.execute(
                    f'SELECT "full"::text FROM objects WHERE type = %s '  # ty: ignore[invalid-argument-type]
                    f"AND \"full\"->>'tournament_uid' IN ({placeholders}) "
                    f"AND deleted_at IS NULL",
                    (ObjectType.DECK, *t_uids),
                )
            ).fetchall()
            if deck_rows:
                frames.extend(_sse_object_lines("decks", [r[0] for r in deck_rows]))
                count += len(deck_rows)

    return frames, count


@app.get("/stream")
async def stream_updates(
    request: Request,
    since: str | None = None,
    token: str | None = None,
    tournament: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """Stream object updates via SSE (new sync architecture).

    Reads pre-computed access level columns — no per-item filtering.
    Personal overlay sends full-level data for own objects and
    role-based full access (NC/Prince same country, organizer).

    `tournament=<uid>` opens a tournament-scoped stream (the Discord bot): the
    catch-up carries only that tournament + its sanctions, and live events are
    filtered to that tournament (its object, sanctions, judge calls). Access is
    unchanged — the same per-object projection rule applies, just restricted to
    one tournament's objects — so it adds no new visibility.
    """
    from .db import _pool, stream_objects_new

    stream_user = await _resolve_viewer(request, token, authorization)
    # One label identifies this connection in every log line below: who + scope
    # (a tournament-scoped bot stream vs a full-corpus browser stream). Makes
    # open/close/overflow/sync-complete attributable — the gap that made the bot
    # SSE-listener wedge hard to trace from backend logs.
    _who = stream_user.uid if stream_user else "anon"
    _scope = f"tournament={tournament}" if tournament else "full-corpus"
    conn_label = f"user={_who} {_scope}"
    logger.info(f"SSE connection opening: {conn_label}")

    # Determine base level
    level = _viewer_level(stream_user)

    # Resync detection
    effective_since = since
    force_resync = False
    threshold_parts = [MINIMUM_SYNC_EPOCH]
    if stream_user and stream_user.resync_after:
        threshold_parts.append(stream_user.resync_after.isoformat())
    threshold = max(threshold_parts)
    if since and threshold > since:
        force_resync = True
        effective_since = None

    # Stale SSE prevention: if since is older than 3 days, force resync via snapshot
    if since:
        from datetime import UTC, datetime, timedelta

        try:
            since_dt = datetime.fromisoformat(since)
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=UTC)
            if datetime.now(UTC) - since_dt > timedelta(days=3):
                force_resync = True
                effective_since = None
        except (ValueError, TypeError):
            pass

    async def event_generator():
        """Generate SSE events from pre-computed columns."""
        conn = SSEConnection(user=stream_user, tournament_uid=tournament)
        _sse_connections.add(conn)

        try:
            yield ": connected\n\n"

            if force_resync:
                yield 'data: {"type":"resync"}\n\n'

            import time

            start_time = time.time()
            last_timestamp: str | None = None
            totals: dict[str, int] = {}

            # Tournament-scoped catch-up (the Discord bot): only that tournament
            # + its sanctions, instead of the whole corpus. Skips the per-type
            # catch-up and personal overlay below. `since` is ignored here — the
            # scoped state is small, so every (re)connect replays it in full.
            scoped = tournament is not None
            if scoped:
                frames, last_timestamp = await _scoped_catchup_frames(
                    stream_user, tournament, conn.sent_participant_uids
                )
                for line in frames:
                    if _shutdown_event and _shutdown_event.is_set():
                        return
                    yield line

            # Catch-up phase: stream from objects table
            for obj_type in [] if scoped else _STREAM_TYPES:
                count = 0
                batch_type = obj_type + "s"  # "users", "tournaments", etc.
                try:
                    async for json_strings, batch_max in stream_objects_new(
                        obj_type=obj_type,
                        level=level.value,
                        since=effective_since,
                    ):
                        if _shutdown_event and _shutdown_event.is_set():
                            return

                        count += len(json_strings)
                        if batch_max and (
                            last_timestamp is None or batch_max > last_timestamp
                        ):
                            last_timestamp = batch_max

                        for line in _sse_object_lines(batch_type, json_strings):
                            yield line
                except Exception as e:
                    logger.error(f"Error streaming {obj_type} (non-fatal): {e}")

                totals[obj_type] = count

            # Personal overlay phase: full-level data for own objects. Built off
            # the pooled connection (see _overlay_frames), then drained — so the
            # connection is never pinned across a client read.
            if not scoped and stream_user and level == DataLevel.MEMBER and _pool:
                try:
                    overlay, overlay_count = await _overlay_frames(stream_user)
                except Exception as e:
                    logger.error(f"Error in personal overlay: {e}", exc_info=True)
                    overlay, overlay_count = [], 0
                for line in overlay:
                    if _shutdown_event and _shutdown_event.is_set():
                        return
                    yield line
                if overlay_count:
                    logger.info(
                        f"Personal overlay: {overlay_count} objects for {stream_user.uid}"
                    )

            total_time = time.time() - start_time
            parts = ", ".join(f"{v} {k}" for k, v in totals.items())
            # Scoped (bot) catch-up has empty per-type totals — label it explicitly
            # so an empty "Sync complete" isn't mistaken for a broken full sync.
            summary = parts if parts else ("scoped" if scoped else "0 objects")
            logger.info(f"Sync complete ({conn_label}): {summary} in {total_time:.3f}s")

            sync_complete = {"type": "sync_complete", "timestamp": last_timestamp}
            yield f"data: {encoder.encode(sync_complete).decode('utf-8')}\n\n"

            # Real-time updates
            keepalive_counter = 0
            while True:
                if _shutdown_event and _shutdown_event.is_set():
                    return

                # Queue overflowed: end the stream so the browser EventSource
                # reconnects and runs a catch-up sync instead of staying OPEN
                # on a connection that no longer receives broadcasts.
                if conn.closed:
                    logger.warning(
                        f"SSE connection closed after queue overflow ({conn_label}); "
                        "ending stream for reconnect"
                    )
                    return

                try:
                    message = await asyncio.wait_for(conn.queue.get(), timeout=1.0)
                    if message:
                        yield message
                    keepalive_counter = 0
                    # A tournament delivery may have added participants; push their
                    # identities so the bot can name newly-seated players. Clear the
                    # flag BEFORE fetching so a concurrent set isn't lost, and fetch
                    # into a list with the pool released before yielding (the
                    # _overlay_frames/_scoped_catchup contract).
                    if scoped and conn.needs_participant_refresh and _pool:
                        conn.needs_participant_refresh = False
                        try:
                            async with _pool.connection() as db_conn:
                                pframes = await _participant_user_frames(
                                    db_conn, tournament, conn.sent_participant_uids
                                )
                        except Exception as e:
                            logger.error(
                                f"Participant refresh failed ({conn_label}): {e}"
                            )
                            pframes = []
                        for line in pframes:
                            if _shutdown_event and _shutdown_event.is_set():
                                return
                            yield line
                except TimeoutError:
                    keepalive_counter += 1
                    if keepalive_counter >= 30:
                        yield ": keepalive\n\n"
                        keepalive_counter = 0

        except Exception as e:
            logger.error(f"Error in SSE generator ({conn_label}): {e}", exc_info=True)
            raise
        finally:
            _sse_connections.discard(conn)
            logger.info(f"SSE connection closed ({conn_label})")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
