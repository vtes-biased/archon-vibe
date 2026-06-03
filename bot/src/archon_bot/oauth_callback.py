"""HTTP server for OAuth redirect callback."""

import logging

from aiohttp import web

from .archon_api import ArchonAPI
from .token_store import TokenStore

logger = logging.getLogger(__name__)

# Will be set by main.py after bot is ready
_bot = None
_store: TokenStore | None = None
_api: ArchonAPI | None = None


def set_context(bot, store: TokenStore, api: ArchonAPI) -> None:
    global _bot, _store, _api
    _bot = bot
    _store = store
    _api = api


async def handle_callback(request: web.Request) -> web.Response:
    """Handle OAuth redirect from Archon."""
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

    # Look up pending OAuth flow
    pending = await _store.get_pending_oauth(state)
    if not pending:
        return web.Response(text="Unknown or expired OAuth state.", status=400)

    await _store.remove_pending_oauth(state)

    # Exchange code for tokens
    token_data = await _api.exchange_code(code, pending["code_verifier"])
    if not token_data:
        return web.Response(text="Token exchange failed. Please try again.", status=500)

    # Get user info to find archon_uid using the shared API session
    async with _api._session.get(
        "/oauth/userinfo",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    ) as resp:
        if resp.status != 200:
            return web.Response(text="Failed to get user info.", status=500)
        userinfo = await resp.json()

    archon_uid = userinfo["sub"]
    discord_id = pending["discord_id"]

    # Store tokens
    await _store.store_tokens(
        discord_id=discord_id,
        archon_uid=archon_uid,
        access_token=token_data["access_token"],
        refresh_token=token_data["refresh_token"],
    )

    # Notify the user in Discord that auth succeeded
    try:
        user = await _bot.rest.fetch_user(int(discord_id))
        await user.send(
            "Your Archon account is now linked! You can return to Discord and use the bot commands."
        )
    except Exception:
        logger.debug("Could not DM user %s after OAuth", discord_id)

    # Process the pending action
    action = pending["action"]

    if action == "setup":
        # The setup command will be completed by the SSE listener
        # For now, just confirm
        pass

    return web.Response(
        text="<html><body><h2>Authorization successful!</h2>"
        "<p>You can close this window and return to Discord.</p>"
        "</body></html>",
        content_type="text/html",
    )


async def start_callback_server(host: str, port: int) -> web.AppRunner:
    """Start the OAuth callback HTTP server."""
    app = web.Application()
    app.router.add_get("/oauth/callback", handle_callback)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("OAuth callback server listening on %s:%d", host, port)
    return runner
