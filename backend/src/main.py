"""FastAPI application entry point."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import jwt
import msgspec
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse

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
    update_sanction,
)
from .db_oauth import cleanup_expired_oauth_codes, cleanup_expired_oauth_tokens
from .models import (
    DataLevel,
    ObjectType,
    Role,
    User,
)
from .routes import (
    admin,
    api_v1,
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
            bd = await update_sanction(updated)
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
    if os.getenv("VEKN_PUSH", "").lower() != "true":
        return
    try:
        from .vekn_api import VEKNAPIClient
        from .vekn_push import batch_push

        logger.info("Starting VEKN batch push")
        client = VEKNAPIClient()
        try:
            stats = await batch_push(client)
            logger.info(f"VEKN batch push complete: {stats}")
        finally:
            await client.close()
    except Exception as e:
        logger.error(f"Error during VEKN batch push: {e}", exc_info=True)


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
app.include_router(api_v1.router)


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


@app.get("/snapshot")
async def get_snapshot(token: str | None = None) -> Response:
    """Serve pre-computed gzip snapshot for the viewer's access level.

    In dev: reads file from disk and streams directly.
    In prod: would use X-Accel-Redirect for nginx to serve the file.
    """
    from .snapshots import get_snapshot_path

    viewer = await _resolve_user_from_token(token)
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


@app.get("/stream")
async def stream_updates(
    since: str | None = None, token: str | None = None
) -> StreamingResponse:
    """Stream object updates via SSE (new sync architecture).

    Reads pre-computed access level columns — no per-item filtering.
    Personal overlay sends full-level data for own objects and
    role-based full access (NC/Prince same country, organizer).
    """
    from .db import _pool, stream_objects_new

    stream_user = await _resolve_user_from_token(token)
    if stream_user:
        logger.info(f"SSE connection authenticated as user {stream_user.uid}")

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
        conn = SSEConnection(user=stream_user)
        _sse_connections.add(conn)

        try:
            yield ": connected\n\n"

            if force_resync:
                yield 'data: {"type":"resync"}\n\n'

            import time

            start_time = time.time()
            last_timestamp: str | None = None
            totals: dict[str, int] = {}

            # Catch-up phase: stream from objects table
            for obj_type in _STREAM_TYPES:
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

                        if json_strings:
                            joined = ",".join(json_strings)
                            yield f'data: {{"type":"{batch_type}","data":[{joined}]}}\n\n'
                except Exception as e:
                    logger.error(f"Error streaming {obj_type} (non-fatal): {e}")

                totals[obj_type] = count

            # Personal overlay phase: send full-level data for own objects
            if stream_user and level == DataLevel.MEMBER and _pool:
                overlay_count = 0
                try:
                    async with _pool.connection() as db_conn:
                        # Own user profile at full level
                        row = await (
                            await db_conn.execute(
                                'SELECT "full"::text FROM objects WHERE uid = %s AND type = %s',
                                (stream_user.uid, ObjectType.USER),
                            )
                        ).fetchone()
                        if row and row[0]:
                            yield f'data: {{"type":"user","data":{row[0]}}}\n\n'
                            overlay_count += 1

                        # Own decks at full level (even if member=null)
                        rows = await (
                            await db_conn.execute(
                                'SELECT "full"::text FROM objects WHERE type = %s '
                                "AND \"full\"->>'user_uid' = %s AND deleted_at IS NULL",
                                (ObjectType.DECK, stream_user.uid),
                            )
                        ).fetchall()
                        if rows:
                            decks_json = ",".join(r[0] for r in rows)
                            yield f'data: {{"type":"decks","data":[{decks_json}]}}\n\n'
                            overlay_count += len(rows)

                        # NC/Prince: full for same-country users + tournaments
                        if stream_user.country and (
                            Role.NC in stream_user.roles
                            or Role.PRINCE in stream_user.roles
                        ):
                            # Same-country users
                            rows = await (
                                await db_conn.execute(
                                    'SELECT "full"::text FROM objects WHERE type = %s '
                                    "AND \"full\"->>'country' = %s AND deleted_at IS NULL",
                                    (ObjectType.USER, stream_user.country),
                                )
                            ).fetchall()
                            if rows:
                                for i in range(0, len(rows), 500):
                                    batch = rows[i : i + 500]
                                    joined = ",".join(r[0] for r in batch)
                                    yield f'data: {{"type":"users","data":[{joined}]}}\n\n'
                                overlay_count += len(rows)

                            # Same-country tournaments
                            rows = await (
                                await db_conn.execute(
                                    'SELECT "full"::text FROM objects WHERE type = %s '
                                    "AND \"full\"->>'country' = %s AND deleted_at IS NULL",
                                    (ObjectType.TOURNAMENT, stream_user.country),
                                )
                            ).fetchall()
                            if rows:
                                for i in range(0, len(rows), 100):
                                    batch = rows[i : i + 100]
                                    joined = ",".join(r[0] for r in batch)
                                    yield f'data: {{"type":"tournaments","data":[{joined}]}}\n\n'
                                overlay_count += len(rows)

                        # Organizer: full for organized tournaments + their decks
                        rows = await (
                            await db_conn.execute(
                                'SELECT uid, "full"::text FROM objects WHERE type = %s '
                                "AND \"full\"->'organizers_uids' ? %s AND deleted_at IS NULL",
                                (ObjectType.TOURNAMENT, stream_user.uid),
                            )
                        ).fetchall()
                        if rows:
                            t_uids = [r[0] for r in rows]
                            for i in range(0, len(rows), 100):
                                batch = rows[i : i + 100]
                                joined = ",".join(r[1] for r in batch)
                                yield f'data: {{"type":"tournaments","data":[{joined}]}}\n\n'
                            overlay_count += len(rows)

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
                                joined = ",".join(r[0] for r in deck_rows)
                                yield f'data: {{"type":"decks","data":[{joined}]}}\n\n'
                                overlay_count += len(deck_rows)

                    if overlay_count:
                        logger.info(
                            f"Personal overlay: {overlay_count} objects for {stream_user.uid}"
                        )
                except Exception as e:
                    logger.error(f"Error in personal overlay: {e}", exc_info=True)

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
        },
    )
