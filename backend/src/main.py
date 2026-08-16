"""FastAPI application entry point."""

import asyncio
import gzip
import logging
import os
import signal
import time
import zipfile
from collections.abc import AsyncIterator, Iterator
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
    base_data_level,
    cleanup_expired_tokens,
    close_db,
    compute_access_version,
    delete_sanction_hard,
    get_expired_sanctions,
    get_league_public_projection,
    get_sanctions_for_cleanup,
    get_tournament_public_projection,
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
    feedback,
    leagues,
    oauth,
    promos,
    push,
    sanctions,
    tournaments,
    users,
    vekn,
)
from .vekn_sync import VEKNSyncService
from .version import __version__

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_sync_service: VEKNSyncService | None = None

_shutdown_event: asyncio.Event | None = None


def _install_fast_shutdown_signals() -> None:
    """Flip _shutdown_event on SIGTERM/SIGINT before uvicorn's own handler runs, so
    /stream generators self-close within ~1s instead of stalling until uvicorn's
    post-drain lifespan-shutdown sets it too late. Chains onto uvicorn's plain
    `signal.signal` handler — breaks silently if uvicorn switches to `loop.add_signal_handler`."""

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

    try:
        from .twda_import import import_twda_decks

        logger.info("Starting TWDA deck import")
        stats = await import_twda_decks()
        logger.info(f"TWDA deck import: {stats}")
    except Exception as e:
        logger.error(f"Error during TWDA deck import: {e}", exc_info=True)

    # Ratings and snapshot both need tournaments up to date, hence run last.
    await run_rating_recompute()
    await run_snapshot_generation()


async def run_sanction_cleanup() -> None:
    """Soft-delete sanctions past 18 months, then hard-delete ones soft-deleted
    >30 days ago (scheduled task)."""
    from datetime import UTC, datetime

    try:
        logger.info("Starting sanction cleanup")

        expired = await get_expired_sanctions()
        now = datetime.now(UTC)

        for sanction in expired:
            updated = msgspec.structs.replace(sanction, modified=now, deleted_at=now)
            bd = await save_sanction(updated)
            broadcast_precomputed(bd)

        if expired:
            logger.info(f"Soft-deleted {len(expired)} expired sanctions")

        to_delete = await get_sanctions_for_cleanup(days=30)
        for sanction in to_delete:
            await delete_sanction_hard(sanction.uid)

        if to_delete:
            logger.info(f"Hard-deleted {len(to_delete)} old sanctions")

        logger.info("Sanction cleanup complete")

    except Exception as e:
        logger.error(f"Error during sanction cleanup: {e}", exc_info=True)


async def run_promo_stock_recompute() -> None:
    """Daily full promo stock recompute (self-healing consistency pass)."""
    try:
        from .promo_stock import recompute_promo_stock

        await recompute_promo_stock()
        logger.info("Promo stock recompute complete")
    except Exception as e:
        logger.error(f"Error during promo stock recompute: {e}", exc_info=True)


async def run_rating_recompute() -> None:
    """Full recomputation of all ratings and wins (scheduled daily).

    Ratings are now embedded in User objects, so we broadcast user events.
    """
    try:
        from .ratings import recompute_all_ratings

        logger.info("Starting daily rating recompute")
        updated = await recompute_all_ratings()
        logger.info(f"Daily rating recompute complete: {updated} users updated")
    except Exception as e:
        logger.error(f"Error during rating recompute: {e}", exc_info=True)


async def run_vekn_push() -> None:
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
    global _scheduler, _sync_service, _shutdown_event

    logger.info(f"Archon backend starting (version {__version__})")

    from .jwt_config import JWT_DEFAULT_SECRET, JWT_SECRET

    environment = os.getenv("ENVIRONMENT", "development")
    if JWT_SECRET == JWT_DEFAULT_SECRET and environment != "development":
        raise RuntimeError(
            "JWT_SECRET must be set to a secure value in non-development environments. "
            "Set the JWT_SECRET environment variable."
        )

    cards_data, _ = cards._load_cards()
    if cards_data is None:
        logger.warning(
            "engine/data/cards.json not found — card database unavailable. "
            "Run: python scripts/update_cards.py"
        )

    _shutdown_event = asyncio.Event()
    _install_fast_shutdown_signals()
    await init_db()

    if os.getenv("DISCORD_CLIENTID"):
        try:
            from .roles_hook import register_metadata

            await register_metadata()
        except Exception:
            logger.exception("Failed to register Discord Linked Roles metadata")

    _scheduler = AsyncIOScheduler()

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

        sync_interval_hours = int(os.getenv("VEKN_SYNC_INTERVAL_HOURS", "6"))
        _scheduler.add_job(
            run_vekn_sync,
            trigger=IntervalTrigger(hours=sync_interval_hours),
            id="vekn_sync",
            name="VEKN Member Sync",
            replace_existing=True,
        )
        logger.info(f"VEKN sync scheduled every {sync_interval_hours} hours")

        asyncio.create_task(run_vekn_sync())
        logger.info("Initial VEKN sync scheduled in background")
    else:
        logger.info("VEKN sync is disabled")

    _scheduler.add_job(
        run_sanction_cleanup,
        trigger=IntervalTrigger(hours=24),
        id="sanction_cleanup",
        name="Sanction Cleanup",
        replace_existing=True,
    )
    logger.info("Sanction cleanup scheduled daily")

    _scheduler.add_job(
        run_rating_recompute,
        trigger=IntervalTrigger(hours=24),
        id="rating_recompute",
        name="Rating Recompute",
        replace_existing=True,
    )
    logger.info("Rating recompute scheduled daily (initial run after VEKN sync)")

    _scheduler.add_job(
        run_promo_stock_recompute,
        trigger=IntervalTrigger(hours=24),
        id="promo_stock_recompute",
        name="Promo Stock Recompute",
        replace_existing=True,
    )
    logger.info("Promo stock recompute scheduled daily")

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

    _scheduler.add_job(
        run_oauth_cleanup,
        trigger=IntervalTrigger(hours=1),
        id="oauth_cleanup",
        name="OAuth Cleanup",
        replace_existing=True,
    )
    logger.info("OAuth cleanup scheduled hourly")

    _scheduler.add_job(
        run_snapshot_generation,
        trigger=IntervalTrigger(minutes=15),
        id="snapshot_gen",
        name="Snapshot Generation",
        replace_existing=True,
    )
    logger.info("Snapshot generation scheduled every 15 minutes")

    _scheduler.add_job(
        run_purge_deleted_objects,
        trigger=IntervalTrigger(hours=24),
        id="purge_deleted",
        name="Purge Deleted Objects",
        replace_existing=True,
    )
    logger.info("Purge of deleted objects scheduled daily")

    # Always regenerate at startup: until a file exists /snapshot 503s, blocking
    # bootstrap for the minutes the full sync chain would otherwise take.
    asyncio.create_task(run_snapshot_generation())

    _scheduler.start()

    yield

    if _shutdown_event:
        logger.info("Signaling SSE connections to close...")
        _shutdown_event.set()
        _wake_sse_connections()
        await asyncio.sleep(0.5)  # let connections close gracefully

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
    code+params are additive for frontend i18n."""
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
        # The snapshot's access-version fingerprint rides a custom response header;
        # a cross-origin dev frontend can only read it if it's explicitly exposed.
        expose_headers=["X-Access-Version"],
    )

    @app.exception_handler(Exception)
    async def cors_aware_500_handler(request: Request, exc: Exception) -> JSONResponse:
        """Dev-only: ServerErrorMiddleware wraps outside CORSMiddleware, so an
        unhandled 500 ships with no CORS headers and the cross-origin dev frontend
        sees a blocked response. Re-attach them; ServerErrorMiddleware still
        re-raises after, preserving uvicorn's traceback logging."""
        origin = request.headers.get("origin")
        headers = (
            {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Vary": "Origin",
            }
            if origin
            else {}
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"},
            headers=headers,
        )


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(vekn.router)
app.include_router(sanctions.router)
app.include_router(tournaments.router)
app.include_router(oauth.router)
app.include_router(cards.router)
app.include_router(leagues.router)
app.include_router(promos.router)
app.include_router(calendar.router)
app.include_router(push.router)
app.include_router(feedback.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "version": __version__}


@app.get("/api/time")
async def server_time() -> Response:
    """Microsecond server clock for the frontend's mini-NTP offset sync.

    The round timer diffs a server-stamped started_at against client
    Date.now(), so a mis-set device clock shows phantom elapsed time; the
    client probes this to correct the offset. Must not be cached.
    """
    body = msgspec.json.encode({"server_time": time.time_ns() // 1000})
    return Response(
        content=body,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/tournaments/{uid}")
async def tournament_og_stub(uid: str, request: Request) -> Response:
    """Open Graph stub for a tournament share link — reached ONLY by social
    crawlers (nginx UA-splits /tournaments/{uid}; humans get the static SPA).

    Serves the public projection only (no auth on a crawler request); an unknown
    or soft-deleted uid falls back to the site-wide card rather than erroring.
    """
    from .og import render_og_html

    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    pub = await get_tournament_public_projection(uid)
    html = render_og_html(f"{proto}://{host}", uid, pub)
    return Response(content=html, media_type="text/html")


@app.get("/leagues/{uid}")
async def league_og_stub(uid: str, request: Request) -> Response:
    """Open Graph stub for a league share link — same crawler-only UA-split
    as the tournament stub above; unknown/deleted uid → site-wide card."""
    from .og import render_league_og_html

    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    pub_count = await get_league_public_projection(uid)
    pub, count = pub_count if pub_count else (None, 0)
    html = render_league_og_html(f"{proto}://{host}", uid, pub, count)
    return Response(content=html, media_type="text/html")


@app.get("/help/{slug}")
async def help_og_stub(slug: str, request: Request) -> Response:
    """Open Graph stub for a help-page share link — same crawler-only UA-split.

    Static content, so no projection lookup; an unknown slug falls back to the
    site-wide card rather than erroring.
    """
    from .og import render_help_og_html

    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return Response(
        content=render_help_og_html(f"{proto}://{host}", slug),
        media_type="text/html",
    )


def _viewer_level(viewer: User | None) -> DataLevel:
    """Determine the viewer's base data level (delegates to db.base_data_level —
    the single source the access-version fingerprint also reuses)."""
    return DataLevel(base_data_level(viewer))


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


def _iter_file_chunks(path, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    """Yield a file's bytes in chunks, holding ONE fd open for the whole response.

    The held fd pins the inode, so an atomic os.rename mid-stream (snapshot
    regen) is safe. Sync generator → Starlette iterates it in a threadpool,
    keeping the blocking reads off the event loop.
    """
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            yield chunk


class _ZipSink:
    """Write-only, non-seekable sink zipfile can stream an archive into — the
    `tell()`-without-`seek()` combo triggers zipfile's data-descriptor fallback.
    `pos` must keep counting past a drain: it's the central-directory header offset."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self.pos = 0

    def write(self, data: bytes) -> int:
        self._buf += data
        self.pos += len(data)
        return len(data)

    def tell(self) -> int:
        return self.pos

    def flush(self) -> None:
        pass

    @property
    def pending(self) -> int:
        return len(self._buf)

    def take(self) -> bytes:
        chunk = bytes(self._buf)
        del self._buf[:]
        return chunk


def _iter_snapshot_zip(
    path, name: str, mtime: float, chunk_size: int = 64 * 1024
) -> Iterator[bytes]:
    """Yield a single-entry .zip holding the snapshot's JSONL, streamed.

    The stored snapshot is .gz, unreadable by stock Windows tools, so the
    export re-envelopes it: inflate and re-deflate through zipfile, sink
    drained every chunk_size bytes to keep heap bounded.
    """
    info = zipfile.ZipInfo(name, time.localtime(mtime)[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    # ZipInfo defaults external_attr to 0, which on the Unix create_system means
    # mode 0000 — some extractors honour that and unpack an unreadable file.
    info.external_attr = 0o644 << 16
    sink = _ZipSink()
    with (
        zipfile.ZipFile(sink, "w") as archive,
        gzip.open(path, "rb") as source,
        archive.open(info, "w") as entry,
    ):
        while chunk := source.read(chunk_size):
            entry.write(chunk)
            if sink.pending >= chunk_size:
                yield sink.take()
    # Exiting the block wrote the data descriptor and the central directory.
    yield sink.take()


@app.get("/snapshot")
async def get_snapshot(
    request: Request,
    token: str | None = None,
    download: bool = False,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Serve pre-computed gzip snapshot for the viewer's access level, streamed
    from disk — never read whole into heap. One fd held for the whole response,
    so a mid-stream atomic-rename regen leaves in-flight readers on their old inode.
    `download=1` re-envelopes the same content as a .zip attachment.
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

    # The snapshot body is per-LEVEL, so the per-USER access-version fingerprint
    # can't live in it — seed it as a header the client reads before /stream.
    headers = {
        "Cache-Control": "no-cache",
        "Accept-Ranges": "none",
        "X-Access-Version": await compute_access_version(viewer),
    }
    if download:
        # Dated from the file's mtime (regen time, not "now"). No Content-Encoding:
        # the .zip is the payload, so the browser writes it to disk, not inflated.
        mtime = snapshot_path.stat().st_mtime
        stem = f"archon-export-{level.value}-" + time.strftime(
            "%Y-%m-%d", time.localtime(mtime)
        )
        headers["Content-Disposition"] = f'attachment; filename="{stem}.zip"'
        return StreamingResponse(
            _iter_snapshot_zip(snapshot_path, f"{stem}.jsonl", mtime),
            media_type="application/zip",
            headers=headers,
        )

    headers["Content-Encoding"] = "gzip"
    return StreamingResponse(
        _iter_file_chunks(snapshot_path),
        media_type="application/x-ndjson",
        headers=headers,
    )


_STREAM_TYPES = list(ObjectType)

# The Discord bot's aiohttp StreamReader rejects lines over 512KB; keep frames
# well under that. A single object over budget is emitted alone, never split.
_SSE_LINE_BUDGET = 200_000


def _sse_object_lines(batch_type: str, json_strings: list[str]):
    """Yield SSE `data:` frames for `json_strings`, each under the byte budget.

    Sizes by UTF-8 byte length, not str length — multibyte names must count
    for what they weigh on the wire.
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
    """Member-level identity frames for a tournament's participants not in `sent`
    (mutated here). Deliberately not `entitled_level` — that would upgrade an
    organizer viewer to `full` and leak participant CONTACT INFO to the Discord process."""
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
    """Catch-up frames for a tournament-scoped SSE connection: one tournament +
    its sanctions + participant identities, far smaller than the full-corpus
    catch-up. Seeds `sent` so the first live event doesn't re-send everyone."""
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
    level, plus NC same-country and organizer full data. Buffers every frame
    while holding ONE pooled connection, then returns them so the caller releases
    it BEFORE draining — yielding inside the `async with` would pin the slot."""
    from .db import _pool

    frames: list[str] = []
    count = 0
    if not _pool:
        return frames, count

    async with _pool.connection() as db_conn:
        row = await (
            await db_conn.execute(
                'SELECT "full"::text FROM objects WHERE uid = %s AND type = %s',
                (viewer.uid, ObjectType.USER),
            )
        ).fetchone()
        if row and row[0]:
            frames.append(f'data: {{"type":"user","data":{row[0]}}}\n\n')
            count += 1

        # Own decks at full level, even when member=null.
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

        if viewer.country and Role.NC in viewer.roles:
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

        # Mirrors the entitled_level promo branch (NC full regardless of country)
        # — omitting this lets a resync re-deliver member-level promos to NC.
        if Role.NC in viewer.roles:
            rows = await (
                await db_conn.execute(
                    'SELECT "full"::text FROM objects WHERE type = %s '
                    "AND deleted_at IS NULL",
                    (ObjectType.PROMO,),
                )
            ).fetchall()
            if rows:
                frames.extend(_sse_object_lines("promos", [r[0] for r in rows]))
                count += len(rows)

        # Literal type (not %s) so the partial index's `type = 'tournament'`
        # predicate provably holds; @> (not ?) so its jsonb_path_ops applies.
        rows = await (
            await db_conn.execute(
                "SELECT uid, \"full\"::text FROM objects WHERE type = 'tournament' "
                "AND (\"full\"->'organizers_uids') @> %s::jsonb AND deleted_at IS NULL",
                (msgspec.json.encode([viewer.uid]).decode(),),
            )
        ).fetchall()
        if rows:
            t_uids = [r[0] for r in rows]
            frames.extend(_sse_object_lines("tournaments", [r[1] for r in rows]))
            count += len(rows)

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
    generated_at: str | None = None,
    av: str | None = None,
    token: str | None = None,
    tournament: str | None = None,
    device_id: str | None = None,
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """Stream object updates via SSE, reading pre-computed access columns — no
    per-item filtering. `tournament=<uid>` opens a bot-scoped stream: catch-up and
    live events restricted to that tournament + its sanctions, same access rule."""
    from .db import _pool, stream_objects_new

    stream_user = await _resolve_viewer(request, token, authorization)
    # One label per connection in every log line: who + scope — makes
    # open/close/overflow/sync-complete attributable when tracing an SSE issue.
    _who = stream_user.uid if stream_user else "anon"
    _scope = f"tournament={tournament}" if tournament else "full-corpus"
    conn_label = f"user={_who} {_scope}"
    logger.info(f"SSE connection opening: {conn_label}")

    level = _viewer_level(stream_user)

    from datetime import UTC, datetime, timedelta

    def _parse_ts(ts: str | None) -> datetime | None:
        if not ts:
            return None
        try:
            dt = datetime.fromisoformat(ts)
            return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
        except (ValueError, TypeError):
            return None

    # Effective "now" = later of the data cursor (`since`) and `generated_at` —
    # `since` alone lags real time on a quiet system and can't measure client-away time.
    fresh_dts = [d for d in (_parse_ts(since), _parse_ts(generated_at)) if d]
    fresh_dt = max(fresh_dts) if fresh_dts else None

    effective_since = since
    force_resync = False
    scoped_stream = tournament is not None

    # Sole access-change mechanism: a stale fp means an entitlement change a
    # since-delta can't repair. Scoped (bot) streams carry no `av`, so they skip this.
    if not scoped_stream and av != await compute_access_version(stream_user):
        force_resync = True
        effective_since = None

    # Orthogonal to entitlement: away >3 days risks a soft-delete already
    # hard-purged by the 30-day job, which a since-delta would miss.
    if fresh_dt and datetime.now(UTC) - fresh_dt > timedelta(days=3):
        force_resync = True
        effective_since = None

    async def event_generator():
        conn = SSEConnection(
            user=stream_user, tournament_uid=tournament, device_id=device_id
        )
        _sse_connections.add(conn)

        try:
            yield ": connected\n\n"

            # Scoped (bot) streams replay full state every connect, so a forced
            # resync is a no-op for them — skip and fall through to the replay.
            scoped = tournament is not None
            if force_resync and not scoped:
                # Client tears down on this line — streaming the corpus after it
                # is wasted, and a mid-fetchall teardown discards the pooled connection.
                yield 'data: {"type":"resync"}\n\n'
                return

            import time

            start_time = time.time()
            last_timestamp: str | None = None
            totals: dict[str, int] = {}

            # Only that tournament + its sanctions, skipping the catch-up/overlay
            # below. `since` ignored — scoped state always replays in full.
            if scoped:
                frames, last_timestamp = await _scoped_catchup_frames(
                    stream_user, tournament, conn.sent_participant_uids
                )
                for line in frames:
                    if _shutdown_event and _shutdown_event.is_set():
                        return
                    yield line

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

            # Built off one pooled connection (_overlay_frames), then drained —
            # never pinned across a client read.
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

            keepalive_counter = 0
            while True:
                if _shutdown_event and _shutdown_event.is_set():
                    return

                # Queue overflow: end the stream so EventSource reconnects, instead
                # of staying OPEN on a connection that no longer receives broadcasts.
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
                    # Clear the flag BEFORE fetching so a concurrent set isn't lost;
                    # fetch into a list with the pool released before yielding.
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
