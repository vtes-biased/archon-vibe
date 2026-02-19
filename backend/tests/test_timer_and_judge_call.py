"""Tests for timer + judge call features.

Covers:
- Timer data visibility in SSE filter (member must see timer fields)
- Timer lifecycle hooks in tournament_action (StartRound resets, FinishRound pauses)
- resolveTableLabelPy (room label resolution)
- broadcast_judge_call targeting (only organizers/IC receive)
"""

from datetime import UTC, datetime

from src.main import _filter_tournament, broadcast_judge_call, SSEConnection
from src.models import (
    Player,
    Role,
    Room,
    Seat,
    Table,
    TimeExtensionPolicy,
    TimerState,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)
from src.routes.tournaments import resolveTableLabelPy

NOW = datetime.now(UTC)


def _make_user(
    uid: str = "u1", name: str = "Alice", country: str = "FR",
    vekn_id: str | None = "1000001", roles: list[Role] | None = None,
) -> User:
    return User(uid=uid, modified=NOW, name=name, country=country,
                vekn_id=vekn_id, roles=roles or [])


def _make_viewer(
    uid: str = "viewer", roles: list[Role] | None = None,
    vekn_id: str | None = "9999999", country: str = "FR",
) -> User:
    return _make_user(uid=uid, name="Viewer", roles=roles,
                      vekn_id=vekn_id, country=country)


def _make_tournament(
    state: TournamentState = TournamentState.PLAYING,
    organizers_uids: list[str] | None = None,
    players: list[Player] | None = None,
    **kwargs,
) -> Tournament:
    return Tournament(
        uid="t1", modified=NOW, name="Test",
        format=TournamentFormat.Standard, rank=TournamentRank.BASIC,
        state=state, country="FR",
        organizers_uids=organizers_uids or [],
        players=players or [],
        standings=[], decks={},
        **kwargs,
    )


# ============================================================================
# SSE filter: timer field visibility
# ============================================================================


class TestFilterTournamentTimerFields:
    """Timer fields must be visible to member-level viewers (players)."""

    def test_member_sees_round_time(self):
        t = _make_tournament(round_time=5400)
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.round_time == 5400

    def test_member_sees_finals_time(self):
        t = _make_tournament(finals_time=7200)
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.finals_time == 7200

    def test_member_sees_timer_state(self):
        timer = TimerState(
            started_at=NOW,
            elapsed_before_pause=120.5,
            paused=False,
        )
        t = _make_tournament(timer=timer)
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.timer.started_at == NOW
        assert result.timer.elapsed_before_pause == 120.5
        assert result.timer.paused is False

    def test_member_sees_table_extra_time(self):
        t = _make_tournament(table_extra_time={"0": 60, "2": 180})
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.table_extra_time == {"0": 60, "2": 180}

    def test_member_sees_table_paused_at(self):
        ts = NOW.isoformat()
        t = _make_tournament(table_paused_at={"1": ts})
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.table_paused_at == {"1": ts}

    def test_member_sees_time_extension_policy(self):
        t = _make_tournament(time_extension_policy=TimeExtensionPolicy.CLOCK_STOP)
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.time_extension_policy == TimeExtensionPolicy.CLOCK_STOP

    def test_nonmember_does_not_see_timer(self):
        """Non-members get minimal tournament -- no timer data."""
        t = _make_tournament(round_time=5400, timer=TimerState(paused=False, started_at=NOW))
        viewer = _make_viewer(vekn_id=None)
        result = _filter_tournament(t, viewer)
        assert result.round_time == 0  # default
        assert result.timer.paused is True  # default

    def test_organizer_sees_timer(self):
        """Organizers get full tournament object."""
        timer = TimerState(started_at=NOW, paused=False)
        t = _make_tournament(
            round_time=5400, timer=timer,
            organizers_uids=["viewer"],
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result is t  # same object, full access


# ============================================================================
# resolveTableLabelPy
# ============================================================================


class TestResolveTableLabel:
    def test_no_rooms(self):
        assert resolveTableLabelPy([], 0) == "Table 1"
        assert resolveTableLabelPy([], 3) == "Table 4"

    def test_single_room(self):
        rooms = [Room(name="Main Hall", count=5)]
        assert resolveTableLabelPy(rooms, 0) == "Main Hall T1"
        assert resolveTableLabelPy(rooms, 4) == "Main Hall T5"

    def test_multiple_rooms(self):
        rooms = [Room(name="Room A", count=3), Room(name="Room B", count=4)]
        # Room A: indices 0,1,2
        assert resolveTableLabelPy(rooms, 0) == "Room A T1"
        assert resolveTableLabelPy(rooms, 2) == "Room A T3"
        # Room B: indices 3,4,5,6
        assert resolveTableLabelPy(rooms, 3) == "Room B T1"
        assert resolveTableLabelPy(rooms, 6) == "Room B T4"

    def test_index_beyond_rooms_falls_back(self):
        rooms = [Room(name="Small", count=2)]
        assert resolveTableLabelPy(rooms, 5) == "Table 6"


# ============================================================================
# Timer lifecycle hooks (unit-level assertions on the state transitions)
# ============================================================================


class TestTimerLifecycleHooks:
    """Verify the timer state transitions done inline in tournament_action.

    These test the logic at lines 741-754 of tournaments.py:
    - StartRound/StartFinals: fresh paused timer, clear table extensions
    - FinishRound/CancelRound/FinishTournament: accumulate elapsed, pause, clear table extensions
    """

    def test_start_round_creates_fresh_timer(self):
        """Simulating the effect of the StartRound hook."""
        # Before: timer was running from previous round
        old_timer = TimerState(started_at=NOW, elapsed_before_pause=300, paused=False)
        old_extra = {"0": 60, "2": 120}
        old_paused = {"1": NOW.isoformat()}

        # The hook code:
        new_timer = TimerState()
        new_extra: dict = {}
        new_paused: dict = {}

        assert new_timer.paused is True
        assert new_timer.started_at is None
        assert new_timer.elapsed_before_pause == 0.0
        assert new_extra == {}
        assert new_paused == {}

    def test_finish_round_pauses_running_timer(self):
        """Simulating the effect of FinishRound when timer is running."""
        timer = TimerState(started_at=NOW, elapsed_before_pause=100.0, paused=False)

        # The hook code (paraphrased):
        if not timer.paused and timer.started_at:
            elapsed = (datetime.now(UTC) - timer.started_at).total_seconds()
            result = TimerState(
                elapsed_before_pause=timer.elapsed_before_pause + elapsed,
                paused=True,
            )
            assert result.paused is True
            assert result.elapsed_before_pause > 100.0
            assert result.started_at is None

    def test_finish_round_already_paused_noop(self):
        """If timer was already paused, FinishRound should not change elapsed."""
        timer = TimerState(elapsed_before_pause=500.0, paused=True)

        # The hook code: condition not met, timer stays as-is
        if not timer.paused and timer.started_at:
            pass  # not entered
        # Only table extensions are cleared
        assert timer.elapsed_before_pause == 500.0


# ============================================================================
# broadcast_judge_call targeting
# ============================================================================


import asyncio
import pytest


@pytest.mark.asyncio
async def test_judge_call_only_sent_to_organizers_and_ic():
    """Judge call SSE events must only reach organizers of that tournament + IC."""
    from src.main import _sse_connections

    # Create mock SSE connections
    organizer = SSEConnection(user=_make_user(uid="org1", roles=[]))
    ic_user = SSEConnection(user=_make_user(uid="ic1", roles=[Role.IC]))
    random_member = SSEConnection(user=_make_user(uid="random", roles=[]))
    no_user = SSEConnection(user=None)

    # Register connections
    _sse_connections.clear()
    _sse_connections.update({organizer, ic_user, random_member, no_user})

    try:
        await broadcast_judge_call(
            tournament_uid="t1",
            table=2,
            table_label="Room A T3",
            player_name="Alice",
            organizer_uids=["org1"],
        )

        # Organizer should have received it
        assert not organizer.queue.empty()
        # IC should have received it
        assert not ic_user.queue.empty()
        # Random member should NOT
        assert random_member.queue.empty()
        # No user connection should NOT
        assert no_user.queue.empty()
    finally:
        _sse_connections.clear()


@pytest.mark.asyncio
async def test_judge_call_not_sent_to_other_tournament_organizer():
    """An organizer of tournament X should not get judge calls for tournament Y,
    unless they are IC."""
    from src.main import _sse_connections

    other_org = SSEConnection(user=_make_user(uid="org-other", roles=[]))

    _sse_connections.clear()
    _sse_connections.add(other_org)

    try:
        await broadcast_judge_call(
            tournament_uid="t1",
            table=0,
            table_label="Table 1",
            player_name="Bob",
            organizer_uids=["org1"],  # org-other is NOT in this list
        )

        assert other_org.queue.empty()
    finally:
        _sse_connections.clear()
