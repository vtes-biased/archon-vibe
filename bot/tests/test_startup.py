"""The bot connects to Discord at runtime, so a broken client/DI wiring
crash-loops in production while CI stays green — without a live gateway, this
is the only thing that would catch it before deploy."""

from __future__ import annotations

import base64
import inspect
import os
import typing

import hikari
import lightbulb
import miru
import pytest

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot.archon_api import ArchonAPI  # noqa: E402
from archon_bot.main import COMMANDS, build_client  # noqa: E402
from archon_bot.token_store import TokenStore  # noqa: E402

# A well-formed (but fake) gateway token: GatewayBot validates its shape on
# construction — the first segment must base64-decode to the application id.
_FAKE_TOKEN = base64.b64encode(b"123456789012345678").decode() + ".Csabcd.efghij_klmno"


def _injected_types(command: type) -> set[type]:
    """The DI-injected dependency types of a command — its keyword-only invoke
    params (``ctx``/``self`` are positional, so excluded)."""
    hints = typing.get_type_hints(command.invoke)
    return {
        hints[name]
        for name, p in inspect.signature(command.invoke).parameters.items()
        if p.kind is inspect.Parameter.KEYWORD_ONLY
    }


@pytest.mark.asyncio
async def test_build_client_resolves_every_command_dependency() -> None:
    bot = hikari.GatewayBot(_FAKE_TOKEN, intents=hikari.Intents.GUILDS)
    store = TokenStore()
    api = ArchonAPI(store)
    miru_client = miru.Client(bot)

    client = build_client(bot, store, api, miru_client)  # raises on a wiring drift

    required: set[type] = set()
    for command in COMMANDS:
        required |= _injected_types(command)
    # The bot only ever injects these three; if a command grows a new dependency,
    # this set widens and the resolve below catches a missing register_value.
    assert required == {TokenStore, ArchonAPI, miru.Client}

    # Resolve through the COMMAND container nested in DEFAULT — the runtime shape.
    async with client.di.enter_context(lightbulb.di.Contexts.DEFAULT):
        async with client.di.enter_context(lightbulb.di.Contexts.COMMAND) as container:
            resolved = {dep: await container.get(dep) for dep in required}

    assert resolved[TokenStore] is store
    assert resolved[ArchonAPI] is api
    assert resolved[miru.Client] is miru_client
