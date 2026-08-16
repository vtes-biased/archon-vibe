"""The whole tournament object is re-broadcast on every push and replayed in
full on every (re)connect, so a wrong diff would re-post the entire backlog."""

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
    assert compute_announcement_posts(None, _ann("a", "b")) == []


def test_pruned_oldest_is_not_new() -> None:
    out = compute_announcement_posts(_ann("a", "b"), _ann("b", "c"))
    assert [aid for aid, _ in out] == ["c"]


def test_blank_body_skipped() -> None:
    out = compute_announcement_posts(
        {"announcements": []}, {"announcements": [{"id": "x", "body": "   "}]}
    )
    assert out == []
