import asyncio
import logging

from aiohttp import web

from .archon_api import ArchonAPI
from .sse_listener import start_sse, sync_now
from .token_store import TokenStore

logger = logging.getLogger(__name__)

_bot = None
_store: TokenStore | None = None
_api: ArchonAPI | None = None
# Holds the grant reconciles until they finish: asyncio keeps only weak
# references to tasks, so an unheld one can be collected mid-run.
_grant_reconciles: set[asyncio.Task] = set()


def set_context(bot, store: TokenStore, api: ArchonAPI) -> None:
    global _bot, _store, _api
    _bot = bot
    _store = store
    _api = api


async def handle_callback(request: web.Request) -> web.Response:
    assert _store and _api and _bot

    code = request.query.get("code")
    state = request.query.get("state")
    error = request.query.get("error")

    if error:
        return web.Response(
            text=f"Authorization denied: {error}. You can close this window.",
            content_type="text/html",
        )

    if not code or not state:
        return web.Response(text="Missing code or state.", status=400)

    pending = await _store.get_pending_oauth(state)
    if not pending:
        return web.Response(text="Unknown or expired OAuth state.", status=400)

    await _store.remove_pending_oauth(state)

    tokens = await _api.exchange_code(code, pending["code_verifier"])
    if not tokens:
        return web.Response(text="Token exchange failed. Please try again.", status=500)

    discord_id = pending["discord_id"]
    tournament_uid = pending["tournament_uid"]
    await _store.store_tokens(
        discord_id=discord_id, tournament_uid=tournament_uid, **tokens
    )

    for gt in await _store.get_all_guild_tournaments():
        if gt["tournament_uid"] != tournament_uid:
            continue
        if gt["organizer_discord_id"] == discord_id:
            await start_sse(
                _bot, _api, _store, gt["guild_id"], tournament_uid, discord_id
            )
        # A fresh grant changes no tournament structure, so nothing else would
        # reconcile the holder's table CONNECT until the next round.
        task = asyncio.create_task(
            _reconcile_after_grant(gt["guild_id"], tournament_uid)
        )
        _grant_reconciles.add(task)
        task.add_done_callback(_grant_reconciles.discard)

    try:
        user = await _bot.rest.fetch_user(int(discord_id))
        await user.send(
            "Your Archon account is now linked! You can return to Discord and use the bot commands."
        )
    except Exception:
        logger.debug("Could not DM user %s after OAuth", discord_id)

    return web.Response(
        text="<html><body><h2>Authorization successful!</h2>"
        "<p>You can close this window and return to Discord.</p>"
        "</body></html>",
        content_type="text/html",
    )


async def _reconcile_after_grant(guild_id: str, tournament_uid: str) -> None:
    try:
        await sync_now(_bot, _store, guild_id, tournament_uid)
    except Exception as e:
        logger.error("Reconcile after grant failed for %s: %s", tournament_uid, e)


async def start_callback_server(host: str, port: int) -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/oauth/callback", handle_callback)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("OAuth callback server listening on %s:%d", host, port)
    return runner
