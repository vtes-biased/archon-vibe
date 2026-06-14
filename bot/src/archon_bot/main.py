"""Archon Discord Bot — entry point.

Manages online VTES tournaments inside Discord servers via the Archon webapp.
"""

import logging

import hikari
import lightbulb
import miru

from . import config
from .archon_api import ArchonAPI
from .commands.judge import SanctionCommand
from .commands.player import (
    CheckinCommand,
    JudgeCommand,
    RegisterCommand,
    ReportCommand,
)
from .commands.setup import AnnounceCommand, SetupCommand, TeardownCommand
from .oauth_callback import set_context, start_callback_server
from .sse_listener import start_sse
from .token_store import TokenStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@lightbulb.hook(lightbulb.ExecutionSteps.PRE_INVOKE)
async def _auto_defer(
    _pipeline: lightbulb.ExecutionPipeline, ctx: lightbulb.Context
) -> None:
    """Defer every command response ephemerally before invoke runs.

    Commands do backend-API / Discord-REST I/O before their first response;
    without a deferral that can blow Discord's 3s interaction window ("the
    application did not respond"). Every command response is already ephemeral,
    and none opens a modal as its first response (modals come from miru button
    callbacks, separate interactions), so a blanket ephemeral defer is safe.
    """
    await ctx.defer(ephemeral=True)


async def _on_unhandled_command_error(
    exc: lightbulb.exceptions.ExecutionPipelineFailedException,
) -> bool:
    """Last-resort handler: log the traceback and replace the deferred
    "thinking…" with a visible error instead of a silent hang."""
    logger.error("Unhandled command error", exc_info=exc)
    try:
        await exc.context.respond(
            "Something went wrong handling that command. Please try again.",
            flags=hikari.MessageFlag.EPHEMERAL,
        )
    except Exception:
        logger.exception("Failed to send command error response")
    return True


def main() -> None:
    bot = hikari.GatewayBot(
        config.DISCORD_BOT_TOKEN,
        intents=hikari.Intents.GUILDS | hikari.Intents.GUILD_VOICE_STATES,
    )

    client = lightbulb.client_from_app(bot, hooks=[_auto_defer])
    # Surface command crashes as a message instead of a silent/perpetual defer.
    client.error_handler(_on_unhandled_command_error, priority=-10)
    # Subscribe lightbulb client start to bot starting event
    bot.subscribe(hikari.StartingEvent, client.start)

    miru_client = miru.Client(bot)

    # Shared state
    store = TokenStore()
    api = ArchonAPI(store)

    # Register shared deps for command access via lightbulb v3 dependency injection
    registry = client.di.registry_for(lightbulb.di.Contexts.DEFAULT)
    registry.register_value(TokenStore, store)
    registry.register_value(ArchonAPI, api)
    registry.register_value(miru.Client, miru_client)

    # Register commands
    client.register(SetupCommand)
    client.register(TeardownCommand)
    client.register(AnnounceCommand)
    client.register(RegisterCommand)
    client.register(CheckinCommand)
    client.register(ReportCommand)
    client.register(JudgeCommand)
    client.register(SanctionCommand)

    # hikari's GatewayBot has no data store in v2.5; share via this closure
    callback_runner = None

    @bot.listen(hikari.StartedEvent)
    async def on_started(event: hikari.StartedEvent) -> None:
        nonlocal callback_runner
        await store.init()
        await api.init()
        set_context(bot, store, api)

        # Start OAuth callback HTTP server
        callback_runner = await start_callback_server(
            config.CALLBACK_HOST, config.CALLBACK_PORT
        )

        # Resume SSE listeners for all linked tournaments (reconnect after restart)
        all_tournaments = await store.get_all_guild_tournaments()
        for gt in all_tournaments:
            await start_sse(
                bot,
                api,
                store,
                gt["guild_id"],
                gt["tournament_uid"],
                gt["organizer_discord_id"],
            )
        if all_tournaments:
            logger.info("Resumed SSE for %d tournament(s)", len(all_tournaments))

        logger.info("Archon Discord Bot is ready!")

    @bot.listen(hikari.StoppingEvent)
    async def on_stopping(event: hikari.StoppingEvent) -> None:
        if callback_runner:
            await callback_runner.cleanup()
        await api.close()
        await store.close()

    bot.run()


if __name__ == "__main__":
    main()
