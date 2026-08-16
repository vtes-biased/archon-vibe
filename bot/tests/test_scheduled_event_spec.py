"""A wrong ``_parse_start`` shape mix-up would silently shift event times."""

from __future__ import annotations

import os
from datetime import UTC, datetime

os.environ.setdefault("DISCORD_BOT_TOKEN", "test-token")
os.environ.setdefault("OAUTH_CLIENT_ID", "test-client")
os.environ.setdefault("OAUTH_CLIENT_SECRET", "test-secret")

from archon_bot.scheduled_events import (  # noqa: E402
    DEFAULT_DURATION,
    _build_spec,
    _parse_start,
    event_signature,
)

UID = "tournament-uid-1"


def _online(**over: object) -> dict:
    base = {
        "online": True,
        "name": "Spring Online",
        "start": "2099-07-01T10:00:00",
        "timezone": "UTC",
        "state": "Registration",
    }
    base.update(over)
    return base


def test_parse_start_absolute_instant_is_kept_as_utc():
    # An offset/Z value is an absolute instant — timezone field must NOT shift it.
    obj = {"start": "2099-07-01T08:00:00+02:00", "timezone": "America/New_York"}
    assert _parse_start(obj) == datetime(2099, 7, 1, 6, 0, tzinfo=UTC)


def test_parse_start_naive_is_localized_with_tournament_timezone():
    # A naive wall-clock is interpreted in the tournament zone, then UTC-normalized.
    obj = {"start": "2099-07-01T10:00:00", "timezone": "Europe/Paris"}  # CEST = +02:00
    assert _parse_start(obj) == datetime(2099, 7, 1, 8, 0, tzinfo=UTC)


def test_parse_start_missing_or_garbage_is_none():
    assert _parse_start({"start": None}) is None
    assert _parse_start({"start": "not-a-date"}) is None


def test_spec_none_unless_online_with_start():
    assert _build_spec(_online(online=False), UID) is None
    assert _build_spec(_online(start=None), UID) is None
    assert _build_spec(_online(state="Finished"), UID) is None
    assert _build_spec(_online(deleted_at="2099-01-01T00:00:00Z"), UID) is None


def test_spec_end_defaults_to_duration_then_honours_finish():
    spec = _build_spec(_online(finish=None), UID)
    assert spec is not None
    assert spec.end - spec.start == DEFAULT_DURATION

    later = _build_spec(_online(finish="2099-07-01T20:00:00"), UID)
    assert later is not None
    assert later.end == datetime(2099, 7, 1, 20, 0, tzinfo=UTC)

    # A finish at/*before* start is ignored — never a non-positive duration.
    bad = _build_spec(_online(finish="2099-07-01T09:00:00"), UID)
    assert bad is not None and bad.end - bad.start == DEFAULT_DURATION


def test_event_signature_flips_on_cover_and_description_edits():
    base = _online()
    # Banner (cover) change.
    assert event_signature(base) != event_signature(
        _online(banner_path="/api/tournaments/x/banner?v=2")
    )
    # format + description feed the event blurb, so a config edit must re-ensure
    # (else the Discord event keeps a stale description).
    assert event_signature(base) != event_signature(_online(description="New blurb"))
    assert event_signature(base) != event_signature(_online(format="Limited"))
