"""Round-timer reminder scheduling math (post warnings to table voice chats).

``compute_timer_reminders`` is the pure half of the timer feature: given a
tournament snapshot, the live table channels, and ``now`` (UTC epoch), it returns
the per-table reminders to schedule with their wall-clock delays. The listener
only sleeps and posts; if this math drifts, players get a "5 minutes left" that
isn't, a missed time-up, or a reminder on every table on every push. This pins
the contract that mirrors the frontend countdown (TimerDisplay.svelte):

  remaining = total - (elapsed_before_pause + (now - started_at)) + table_extra
  total     = (finals_time or round_time) for finals, else round_time

A reminder's ``delay`` is when the table hits that threshold relative to ``now``;
negative means already passed (the listener suppresses those without posting).

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

from archon_bot.sse_listener import (  # noqa: E402
    _parse_started_at_epoch,
    compute_timer_reminders,
)

STARTED = "2026-06-25T12:00:00+00:00"
EPOCH = _parse_started_at_epoch(STARTED)  # whole-second epoch → exact float math


def _tourney(
    *,
    state: str = "Playing",
    round_time: int = 1200,
    finals_time: int = 0,
    started_at: str | None = STARTED,
    paused: bool = False,
    elapsed: float = 0.0,
    extra: dict | None = None,
    tables: int = 1,
    finals: bool = False,
) -> dict:
    obj: dict = {
        "state": state,
        "round_time": round_time,
        "finals_time": finals_time,
        "timer": {
            "started_at": started_at,
            "paused": paused,
            "elapsed_before_pause": elapsed,
        },
        "table_extra_time": extra or {},
    }
    if finals:
        obj["finals"] = {"seating": [{"player_uid": "a"}]}
    else:
        obj["rounds"] = [[{"seating": []} for _ in range(tables)]]
    return obj


def _delays_by_channel(reminders) -> dict[int, list[float]]:
    by_ch: dict[int, list[float]] = {}
    for r in reminders:
        by_ch.setdefault(r.channel_id, []).append(r.delay)
    return {ch: sorted(v) for ch, v in by_ch.items()}


def test_fresh_round_schedules_15_5_and_timeup() -> None:
    out = compute_timer_reminders(_tourney(round_time=1200), [111], EPOCH)
    # 20-min round just started: warn at 5:00 in (1200-900), 15:00 in (1200-300),
    # time-up at 20:00.
    assert _delays_by_channel(out) == {111: [300.0, 900.0, 1200.0]}
    assert "15 minutes remaining" in next(r for r in out if r.token[2] == 900).message
    assert "5 minutes remaining" in next(r for r in out if r.token[2] == 300).message
    assert "Time!" in next(r for r in out if r.token[2] == 0).message


def test_elapsed_before_pause_shifts_deadline_in() -> None:
    # 10 min already accrued before a pause/resume → only 20 min of a 30-min round
    # remains, so all three thresholds move 600s closer (vs 900/1500/1800 fresh).
    out = compute_timer_reminders(
        _tourney(round_time=1800, elapsed=600.0), [111], EPOCH
    )
    assert _delays_by_channel(out) == {111: [300.0, 900.0, 1200.0]}


def test_finals_uses_finals_time() -> None:
    out = compute_timer_reminders(
        _tourney(finals=True, finals_time=1800, round_time=1200), [999], EPOCH
    )
    # total=1800 (finals_time), not 1200 (round_time) → 900/1500/1800.
    assert _delays_by_channel(out) == {999: [900.0, 1500.0, 1800.0]}
    assert any("Finals" in r.message for r in out)


def test_per_table_extra_time_extends_only_that_table() -> None:
    out = compute_timer_reminders(
        _tourney(tables=2, extra={"1": 120}), [111, 222], EPOCH
    )
    # Table 0 unchanged; table 1 (channel 222) gets +120s on every threshold.
    assert _delays_by_channel(out) == {
        111: [300.0, 900.0, 1200.0],
        222: [420.0, 1020.0, 1320.0],
    }


def test_passed_threshold_yields_negative_delay() -> None:
    # 16:40 into a 20-min round: the 5:00 and 15:00 warnings are in the past (the
    # caller suppresses them), time-up is still 3:20 ahead.
    out = compute_timer_reminders(_tourney(), [111], EPOCH + 1000)
    by_thr = {r.token[2]: r.delay for r in out}
    assert by_thr[900] == -700.0  # 15-min warning already passed
    assert by_thr[300] == -100.0  # 5-min warning already passed
    assert by_thr[0] == 200.0  # time-up still upcoming


def test_zero_sentinel_channel_skipped() -> None:
    # A failed reconcile create leaves a 0 in _table_channels; that table is skipped.
    out = compute_timer_reminders(_tourney(tables=2), [111, 0], EPOCH)
    assert {r.channel_id for r in out} == {111}


def test_only_pending_tables_get_reminders() -> None:
    # Any table whose result is reported/voided/finalized has stopped play — no
    # reminder. Only 'In Progress' (or an unset default) is pending.
    obj = _tourney(tables=4)
    obj["rounds"][-1][0]["state"] = "Finished"
    obj["rounds"][-1][1]["state"] = "Invalid"
    obj["rounds"][-1][2]["state"] = "Cancelled"
    obj["rounds"][-1][3]["state"] = "In Progress"  # the only pending table
    out = compute_timer_reminders(obj, [111, 222, 333, 444], EPOCH)
    assert {r.channel_id for r in out} == {444}

    # An override (judge-finalized, state still In Progress) also stops reminders.
    ov = _tourney(tables=1)
    ov["rounds"][-1][0]["override"] = {"judge_uid": "j"}
    assert compute_timer_reminders(ov, [111], EPOCH) == []

    # A finished finals (seating still populated, tournament not yet finalized) must
    # not keep a stale "Time!" scheduled — the over-trigger the reviewer flagged.
    fin = _tourney(finals=True, finals_time=600)
    fin["finals"]["state"] = "Finished"
    assert compute_timer_reminders(fin, [999], EPOCH) == []


def test_no_reminders_when_clock_not_running() -> None:
    assert compute_timer_reminders(_tourney(paused=True), [111], EPOCH) == []
    assert compute_timer_reminders(_tourney(state="Waiting"), [111], EPOCH) == []
    assert compute_timer_reminders(_tourney(round_time=0), [111], EPOCH) == []
    assert compute_timer_reminders(_tourney(started_at=None), [111], EPOCH) == []


def test_parallel_rounds_suppress_all_reminders() -> None:
    # >1 live prelim round (e.g. self-organized pods) deactivates the single shared
    # timer entirely — the frontend hides it in the same case.
    obj = _tourney()
    obj["rounds"] = [[{"seating": [], "state": "In Progress"}]] * 2
    assert compute_timer_reminders(obj, [111], EPOCH) == []
    # A single live round (an earlier round fully Finished) still schedules normally.
    obj["rounds"] = [
        [{"seating": [], "state": "Finished"}],
        [{"seating": [], "state": "In Progress"}],
    ]
    assert compute_timer_reminders(obj, [111], EPOCH) != []
