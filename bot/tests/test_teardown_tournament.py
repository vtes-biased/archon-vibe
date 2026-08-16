"""Even when the bot has lost its in-memory channel map (restart) or a child
got orphaned out of the category by an earlier partial teardown, a re-run
must still remove everything."""

from __future__ import annotations

import os
from dataclasses import dataclass

import hikari
import pytest

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot.channel_manager import teardown_tournament  # noqa: E402

CATEGORY_ID = 100


@dataclass
class FakeChannel:
    """Duck-types the two attrs teardown reads off a hikari channel."""

    id: int
    parent_id: int | None


class FakeRest:
    def __init__(self, channels, *, not_found=(), errors=(), list_raises=False):
        self._channels = channels
        self._not_found = set(not_found)
        self._errors = set(errors)
        self._list_raises = list_raises
        self.deleted: list[int] = []

    async def fetch_guild_channels(self, guild_id):
        if self._list_raises:
            raise RuntimeError("api down")
        return self._channels

    async def delete_channel(self, channel_id):
        cid = int(channel_id)
        self.deleted.append(cid)
        if cid in self._not_found:
            raise hikari.NotFoundError(url="u", headers={}, raw_body="")
        if cid in self._errors:
            raise RuntimeError("missing Manage Channels")


class FakeBot:
    def __init__(self, rest):
        self.rest = rest


@pytest.mark.asyncio
async def test_deletes_children_and_orphans_category_last() -> None:
    rest = FakeRest(
        [
            FakeChannel(1, CATEGORY_ID),
            FakeChannel(2, CATEGORY_ID),
            FakeChannel(3, None),  # orphaned table — drifted out of the category
            FakeChannel(900, 999),  # a different tournament's channel
        ]
    )
    # The orphan (3) is only reachable via extras; the category id may also appear
    # there and must not be deleted twice.
    failed = await teardown_tournament(
        FakeBot(rest),
        guild_id=1,
        category_id=CATEGORY_ID,
        extra_channel_ids=[3, CATEGORY_ID],
    )

    assert failed == []
    assert set(rest.deleted) == {1, 2, 3, CATEGORY_ID}
    assert 900 not in rest.deleted  # foreign category untouched
    assert rest.deleted[-1] == CATEGORY_ID  # category last
    assert rest.deleted.count(CATEGORY_ID) == 1  # and exactly once


@pytest.mark.asyncio
async def test_reports_real_failures_ignores_already_gone() -> None:
    rest = FakeRest(
        [FakeChannel(1, CATEGORY_ID), FakeChannel(2, CATEGORY_ID)],
        not_found=[1],  # already deleted — not a failure
        errors=[2],  # genuine failure (e.g. missing permission)
    )
    failed = await teardown_tournament(
        FakeBot(rest), guild_id=1, category_id=CATEGORY_ID
    )
    assert failed == [2]
    # A child delete failed, so the category is kept as the survivor's anchor —
    # deleting it would un-parent channel 2 to the guild root.
    assert CATEGORY_ID not in rest.deleted


@pytest.mark.asyncio
async def test_still_deletes_known_ids_when_listing_fails() -> None:
    rest = FakeRest([], list_raises=True)
    failed = await teardown_tournament(
        FakeBot(rest),
        guild_id=1,
        category_id=CATEGORY_ID,
        extra_channel_ids=[7, 8],
    )
    assert failed == []
    assert set(rest.deleted) == {7, 8, CATEGORY_ID}
    assert rest.deleted[-1] == CATEGORY_ID
