"""Archon Discord Bot — entry point.

Manages online VTES tournaments inside Discord servers via the Archon webapp.
"""

import asyncio
import logging

import hikari
import lightbulb
import miru

from . import config
from .archon_api import ArchonAPI
from .commands.judge import SanctionCommand
from .commands.player import CheckinCommand, JudgeCommand, RegisterCommand, ReportCommand
from .commands.setup import AnnounceCommand, SetupCommand, TeardownCommand
from .oauth_callback import set_context, start_callback_server
from .sse_listener import start_sse
from .token_store import TokenStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    bot = hikari.GatewayBot(
        config.DISCORD_BOT_TOKEN,
        intents=hikari.Intents.GUILDS | hikari.Intents.GUILD_VOICE_STATES,
    )

    client = lightbulb.client_from_app(bot)
    # Subscribe lightbulb client start to bot starting event
    bot.subscribe(hikari.StartingEvent, client.start)

    miru_client = miru.Client(bot)

    # Shared state
    store = TokenStore()
    api = ArchonAPI(store)

    # Attach to client.d for command access
    client.d["store"] = store
    client.d["api"] = api
    client.d["miru"] = miru_client

    # Register commands
    client.register(SetupCommand)
    client.register(TeardownCommand)
    client.register(AnnounceCommand)
    client.register(RegisterCommand)
    client.register(CheckinCommand)
    client.register(ReportCommand)
    client.register(JudgeCommand)
    client.register(SanctionCommand)

    @bot.listen(hikari.StartedEvent)
    async def on_started(event: hikari.StartedEvent) -> None:
        await store.init()
        await api.init()
        set_context(bot, store, api)

        # Start OAuth callback HTTP server
        runner = await start_callback_server(config.CALLBACK_HOST, config.CALLBACK_PORT)
        bot.d["callback_runner"] = runner

        # Resume SSE listeners for all linked tournaments (reconnect after restart)
        all_tournaments = await store.get_all_guild_tournaments()
        for gt in all_tournaments:
            await start_sse(
                bot, api, store,
                gt["guild_id"], gt["tournament_uid"], gt["organizer_discord_id"],
            )
        if all_tournaments:
            logger.info("Resumed SSE for %d tournament(s)", len(all_tournaments))

        logger.info("Archon Discord Bot is ready!")

    @bot.listen(hikari.StoppingEvent)
    async def on_stopping(event: hikari.StoppingEvent) -> None:
        runner = bot.d.get("callback_runner")
        if runner:
            await runner.cleanup()
        await api.close()
        await store.close()

    bot.run()


if __name__ == "__main__":
    main()
