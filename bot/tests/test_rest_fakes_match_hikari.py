"""Guard for the REST fakes: the bot has no Discord to talk to, so the suite
stands fakes in for hikari's client. A fake that drifts from hikari's real
signature keeps passing here while production raises on the first call, so
every call shape the bot uses is bound against the real client *and* against
each fake that claims to answer it.

Attribute access is the same trap from the other side: a fake channel carrying
an attr hikari never had makes the parser look covered.
"""

from __future__ import annotations

import inspect
import os

import hikari
import pytest

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

import test_reconcile_channels as reconcile  # noqa: E402
import test_round_channels as round_channels  # noqa: E402
import test_teardown_tournament as teardown  # noqa: E402

# The shapes archon_bot actually calls: (positional count after self, kwargs).
CALLS: dict[str, tuple[int, tuple[str, ...]]] = {
    "fetch_guild_channels": (1, ()),
    "fetch_channel": (1, ()),
    "delete_channel": (1, ()),
    "create_guild_category": (1, ("name",)),
    "create_guild_text_channel": (1, ("name", "category", "permission_overwrites")),
    "create_guild_voice_channel": (1, ("name", "category", "permission_overwrites")),
    "edit_permission_overwrite": (2, ("target_type", "allow", "deny")),
    "delete_permission_overwrite": (2, ()),
    "create_message": (2, ()),
}

FAKES = [reconcile.FakeRest, teardown.FakeRest]

_ANY = object()


def _bind(func, positionals: int, kwargs: tuple[str, ...]) -> None:
    inspect.signature(func).bind(
        _ANY, *[_ANY] * positionals, **dict.fromkeys(kwargs, _ANY)
    )


@pytest.mark.parametrize("name", sorted(CALLS))
def test_call_shape_is_the_real_hikari_one(name: str) -> None:
    positionals, kwargs = CALLS[name]
    _bind(getattr(hikari.impl.RESTClientImpl, name), positionals, kwargs)


@pytest.mark.parametrize("fake", FAKES, ids=lambda f: f.__module__)
def test_fake_rest_answers_the_same_shapes(fake) -> None:
    """A fake may cover a subset of the API, but never a different API."""
    covered = [n for n in CALLS if hasattr(fake, n)]
    assert covered, f"{fake.__module__}.FakeRest fakes nothing the bot calls"
    for name in covered:
        positionals, kwargs = CALLS[name]
        _bind(getattr(fake, name), positionals, kwargs)


@pytest.mark.parametrize(
    "fake_channel",
    [reconcile.FakeChannel, round_channels.FakeChannel, teardown.FakeChannel],
    ids=lambda f: f.__module__,
)
def test_fake_channel_attrs_exist_on_a_real_channel(fake_channel) -> None:
    for attr in fake_channel.__dataclass_fields__:
        assert hasattr(hikari.GuildVoiceChannel, attr), (
            f"{fake_channel.__module__}.FakeChannel.{attr} is not a hikari attr"
        )


def test_fake_overwrite_attrs_exist_on_a_real_overwrite() -> None:
    for attr in reconcile.FakeOverwrite.__dataclass_fields__:
        assert hasattr(hikari.PermissionOverwrite, attr)
