"""Mirroring organizer in-app announcements to the Discord announcement channel.

``compute_announcement_posts`` diffs the tournament's append-only ``announcements``
list (newest last, capped at 20) by ``id`` and returns only the new entries. The
regression that matters is idempotency: the whole tournament object is
re-broadcast on every push and replayed in full on every (re)connect, so a wrong
diff would re-post the entire backlog into Discord — once per push, and again on
every reconnect. This pins:

  - a genuinely new id posts exactly once;
  - an unchanged list posts nothing;
  - prev=None (the catch-up seed) posts nothing — the snapshot is the
    don't-replay-history guard;
  - an id pruned off the front of the capped list is not mistaken for new.

Pure function, no bot/REST — only env vars to satisfy the config import.

Run from bot/:
    DISCORD_BOT_TOKEN=x OAUTH_CLIENT_ID=x OAUTH_CLIENT_SECRET=x \
        uv run --with pytest --with pytest-asyncio pytest -q
"""

from __future__ import annotations

import os

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot.sse_listener import compute_announcement_posts  # noqa: E402


def _ann(*ids: str) -> dict:
    return {"announcements": [{"id": i, "body": f"msg-{i}"} for i in ids]}


def test_new_announcement_posted_once() -> None:
    out = compute_announcement_posts(_ann("a"), _ann("a", "b"))
    assert len(out) == 1
    aid, msg = out[0]
    assert aid == "b" and "msg-b" in msg


def test_unchanged_list_posts_nothing() -> None:
    assert compute_announcement_posts(_ann("a", "b"), _ann("a", "b")) == []


def test_prev_none_seeds_silently() -> None:
    # Catch-up seeds the snapshot with prev=None; the backlog must not be replayed.
    assert compute_announcement_posts(None, _ann("a", "b")) == []


def test_pruned_oldest_is_not_new() -> None:
    # List capped at 20: "a" dropped off the front, "c" appended. Only "c" is new.
    out = compute_announcement_posts(_ann("a", "b"), _ann("b", "c"))
    assert [aid for aid, _ in out] == ["c"]


def test_blank_body_skipped() -> None:
    out = compute_announcement_posts(
        {"announcements": []}, {"announcements": [{"id": "x", "body": "   "}]}
    )
    assert out == []
