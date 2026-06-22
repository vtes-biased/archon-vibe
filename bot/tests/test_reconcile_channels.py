"""Two behavioural invariants of ``reconcile_channels`` that hold regardless of the
exact REST calls it makes (so they're worth pinning even against a fake bot, which
can't validate the calls themselves — the bot has no Discord integration test):

  - IDEMPOTENT CONVERGENCE: a second reconcile of an already-matching Discord state
    creates and deletes nothing. This is what makes a reconnect / repeated /sync
    safe, and it's the property the whole "make state match, don't replay actions"
    design rests on.
  - NO PER-CHANNEL FETCH (principal-engineer HARD requirement): a survivor's
    permissions are reconciled from the overrides already on the
    ``fetch_guild_channels`` payload, never a per-channel ``fetch_channel`` — here
    the fake's ``fetch_channel`` RAISES, so any regression to re-fetching fails loud.

Run from bot/:
    DISCORD_BOT_TOKEN=x OAUTH_CLIENT_ID=x OAUTH_CLIENT_SECRET=x \
        uv run --with pytest --with pytest-asyncio pytest -q
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import hikari
import pytest

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot import sse_listener  # noqa: E402
from archon_bot.sse_listener import reconcile_channels  # noqa: E402

GUILD = "1"
TUID = "tour-1"
CATEGORY_ID = 100
JUDGES_ID = 60

# archon_uid → discord id
DISCORD = {"p1": 1001, "p2": 1002, "org1": 9001}
BOT_ID = 7777  # the bot's own member id — never a seated player/organizer


@dataclass
class FakeOverwrite:
    id: int
    type: hikari.PermissionOverwriteType


@dataclass
class FakeChannel:
    id: int
    name: str
    type: hikari.ChannelType
    parent_id: int | None
    permission_overwrites: dict = field(default_factory=dict)


def _member_ovw(*discord_ids: int) -> dict:
    ovw = {
        did: FakeOverwrite(did, hikari.PermissionOverwriteType.MEMBER)
        for did in discord_ids
    }
    # An @everyone ROLE override is always present and must be ignored.
    ovw[int(GUILD)] = FakeOverwrite(int(GUILD), hikari.PermissionOverwriteType.ROLE)
    return ovw


class FakeRest:
    def __init__(self, channels: list[FakeChannel]) -> None:
        self._channels = channels
        self._next_id = 5000
        self.created: list[str] = []
        self.deleted: list[int] = []
        self.edited_overwrites: list[tuple[int, int]] = []
        self.removed_overwrites: list[tuple[int, int]] = []
        self.fetch_channel_calls = 0

    async def fetch_guild_channels(self, guild_id):
        return self._channels

    async def create_guild_voice_channel(
        self, guild_id, name, category, permission_overwrites=None
    ):
        self._next_id += 1
        self.created.append(name)
        return FakeChannel(
            self._next_id, name, hikari.ChannelType.GUILD_VOICE, category
        )

    async def delete_channel(self, channel_id):
        self.deleted.append(int(channel_id))

    async def edit_permission_overwrite(self, channel_id, target, **kw):
        self.edited_overwrites.append((int(channel_id), int(target)))

    async def delete_permission_overwrite(self, channel_id, target):
        self.removed_overwrites.append((int(channel_id), int(target)))

    async def fetch_channel(self, channel_id):  # must NOT be reached by reconcile
        self.fetch_channel_calls += 1
        raise AssertionError("reconcile must not fetch per-channel (HARD req)")

    async def create_message(self, channel_id, content):
        pass


@dataclass
class FakeOwnUser:
    id: int


class FakeBot:
    def __init__(self, rest: FakeRest) -> None:
        self.rest = rest

    def get_me(self):
        return FakeOwnUser(BOT_ID)


class FakeStore:
    async def get_tournament_link(self, guild_id, tournament_uid):
        return {
            "category_id": str(CATEGORY_ID),
            "judges_channel_id": str(JUDGES_ID),
            "announcement_channel_id": "61",
            "lobby_channel_id": "62",
            "organizer_discord_id": "9001",
        }

    async def get_discord_ids_by_archon_uids(self, uids):
        return {u: str(DISCORD[u]) for u in uids if u in DISCORD}


def _category() -> FakeChannel:
    return FakeChannel(
        CATEGORY_ID, "Tournament", hikari.ChannelType.GUILD_CATEGORY, None
    )


def _key() -> str:
    return f"{GUILD}:{TUID}"


def _playing(*tables: list[str]) -> dict:
    return {
        "uid": TUID,
        "state": "Playing",
        "organizers_uids": ["org1"],
        "rounds": [[{"seating": [{"player_uid": u} for u in t]} for t in tables]],
    }


@pytest.fixture(autouse=True)
def _clean_state():
    sse_listener._table_channels.pop(_key(), None)
    yield
    sse_listener._table_channels.pop(_key(), None)


@pytest.mark.asyncio
async def test_second_reconcile_of_matching_state_is_a_noop() -> None:
    # Discord already exactly matches desired_channels(obj): two correctly-membered
    # tables and nothing else. A reconcile must create and delete nothing.
    channels = [
        _category(),
        FakeChannel(JUDGES_ID, "judges", hikari.ChannelType.GUILD_VOICE, CATEGORY_ID),
        FakeChannel(
            201,
            "R1 - Table 1",
            hikari.ChannelType.GUILD_VOICE,
            CATEGORY_ID,
            _member_ovw(1001, 9001),
        ),
        FakeChannel(
            202,
            "R1 - Table 2",
            hikari.ChannelType.GUILD_VOICE,
            CATEGORY_ID,
            _member_ovw(1002, 9001),
        ),
    ]
    rest = FakeRest(channels)
    obj = _playing(["p1"], ["p2"])

    summary = await reconcile_channels(FakeBot(rest), FakeStore(), GUILD, TUID, obj)

    assert summary.created == [] and summary.deleted == []
    assert rest.created == [] and rest.deleted == []
    # The two tables are adopted, in order, for the announcement layer.
    assert sse_listener._table_channels[_key()] == [201, 202]


@pytest.mark.asyncio
async def test_in_sync_survivor_uses_payload_overwrites_never_refetches() -> None:
    # Member overrides already equal the desired set → zero permission writes AND
    # zero per-channel fetches (fetch_channel raises if reached).
    ch = FakeChannel(
        201,
        "R1 - Table 1",
        hikari.ChannelType.GUILD_VOICE,
        CATEGORY_ID,
        _member_ovw(1001, 9001),
    )
    rest = FakeRest([_category(), ch])
    obj = _playing(["p1"])  # desired members {p1, org1} == overrides {1001, 9001}

    await reconcile_channels(FakeBot(rest), FakeStore(), GUILD, TUID, obj)

    assert rest.fetch_channel_calls == 0
    assert rest.edited_overwrites == [] and rest.removed_overwrites == []
    assert rest.created == [] and rest.deleted == []


@pytest.mark.asyncio
async def test_reconcile_preserves_the_bots_own_overwrite() -> None:
    # The bot grants itself an overwrite on every table voice channel so it can
    # later DELETE it (Discord needs CONNECT to delete a voice channel). The bot is
    # never a seated player, so a naive stale-diff would reap that overwrite —
    # leaving teardown unable to remove the channel. Reconcile must keep it.
    ch = FakeChannel(
        201,
        "R1 - Table 1",
        hikari.ChannelType.GUILD_VOICE,
        CATEGORY_ID,
        _member_ovw(1001, 9001, BOT_ID),
    )
    rest = FakeRest([_category(), ch])
    obj = _playing(["p1"])  # desired members {p1, org1}; the bot is not among them

    await reconcile_channels(FakeBot(rest), FakeStore(), GUILD, TUID, obj)

    assert (201, BOT_ID) not in rest.removed_overwrites
    assert rest.removed_overwrites == []
