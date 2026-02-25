"""Tests for calendar feed logic.

Focuses on:
- _matches_agenda: personal agenda filtering (organizer, participant, geography)
- _escape_ical / _format_dt: iCal formatting edge cases
- _tournament_to_vevent: event generation
"""

from datetime import UTC, datetime

from src.models import (
    Player,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
)
from src.routes.calendar import (
    _escape_ical,
    _format_dt,
    _matches_agenda,
    _tournament_to_vevent,
)

NOW = datetime.now(UTC)
JUNE_15_10AM = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
JUNE_15_2PM = datetime(2025, 6, 15, 14, 0, 0, tzinfo=UTC)
JUNE_15_6PM = datetime(2025, 6, 15, 18, 0, 0, tzinfo=UTC)


def _make_tournament(
    uid: str = "t1",
    state: TournamentState = TournamentState.PLANNED,
    country: str = "FR",
    organizers_uids: list[str] | None = None,
    players: list[Player] | None = None,
    online: bool = False,
    rank: TournamentRank = TournamentRank.BASIC,
    start: datetime | None = None,
    finish: datetime | None = None,
    **kwargs,
) -> Tournament:
    return Tournament(
        uid=uid,
        modified=NOW,
        name="Test Tournament",
        format=TournamentFormat.Standard,
        rank=rank,
        state=state,
        country=country,
        organizers_uids=organizers_uids or [],
        players=players or [],
        online=online,
        start=start,
        finish=finish,
        **kwargs,
    )


# ============================================================================
# _matches_agenda tests
# ============================================================================


class TestMatchesAgenda:
    """Test personal agenda filtering logic."""

    def test_organizer_always_matches(self):
        t = _make_tournament(organizers_uids=["user1"], state=TournamentState.FINISHED)
        assert _matches_agenda(t, "user1", "US", []) is True

    def test_participant_always_matches(self):
        t = _make_tournament(
            players=[Player(user_uid="user1")],
            state=TournamentState.FINISHED,
        )
        assert _matches_agenda(t, "user1", "US", []) is True

    def test_same_country_non_finished(self):
        t = _make_tournament(country="FR", state=TournamentState.PLANNED)
        assert _matches_agenda(t, "user1", "FR", []) is True

    def test_same_country_finished_no_match(self):
        """Finished tournaments only match if user organizes or participates."""
        t = _make_tournament(country="FR", state=TournamentState.FINISHED)
        assert _matches_agenda(t, "user1", "FR", []) is False

    def test_online_matches(self):
        t = _make_tournament(online=True, country="US", state=TournamentState.PLANNED)
        assert _matches_agenda(t, "user1", "FR", []) is True

    def test_online_finished_no_match(self):
        t = _make_tournament(online=True, state=TournamentState.FINISHED)
        assert _matches_agenda(t, "user1", "FR", []) is False

    def test_nc_same_continent(self):
        """National Championship on same continent should match."""
        t = _make_tournament(country="DE", rank=TournamentRank.NC)
        assert _matches_agenda(t, "user1", "FR", ["FR", "DE", "ES"]) is True

    def test_cc_same_continent(self):
        t = _make_tournament(country="DE", rank=TournamentRank.CC)
        assert _matches_agenda(t, "user1", "FR", ["FR", "DE"]) is True

    def test_basic_different_country_no_match(self):
        """Basic tournament in another country, not organizer/participant."""
        t = _make_tournament(country="US")
        assert _matches_agenda(t, "user1", "FR", ["FR", "DE"]) is False

    def test_nc_different_continent_no_match(self):
        """NC tournament on different continent should not match."""
        t = _make_tournament(country="US", rank=TournamentRank.NC)
        assert _matches_agenda(t, "user1", "FR", ["FR", "DE"]) is False

    def test_no_user_country(self):
        """User with no country -- only organizer/participant/online matches."""
        t = _make_tournament(country="FR")
        assert _matches_agenda(t, "user1", None, []) is False


# ============================================================================
# iCal formatting tests
# ============================================================================


class TestEscapeIcal:
    def test_semicolons_escaped(self):
        assert _escape_ical("a;b") == "a\\;b"

    def test_commas_escaped(self):
        assert _escape_ical("a,b") == "a\\,b"

    def test_newlines_escaped(self):
        assert _escape_ical("line1\nline2") == "line1\\nline2"

    def test_backslash_escaped_first(self):
        assert _escape_ical("a\\;b") == "a\\\\\\;b"


class TestFormatDt:
    def test_datetime_utc(self):
        assert _format_dt(JUNE_15_2PM) == "20250615T140000Z"

    def test_datetime_naive(self):
        naive = datetime(2025, 6, 15, 14, 0, 0)
        assert _format_dt(naive) == "20250615T140000Z"

    def test_none_returns_empty(self):
        assert _format_dt(None) == ""


class TestTournamentToVevent:
    def test_basic_event(self):
        t = _make_tournament(
            uid="t-abc",
            start=JUNE_15_10AM,
            finish=JUNE_15_6PM,
        )
        result = _tournament_to_vevent(t, "20250101T000000Z")
        assert "BEGIN:VEVENT" in result
        assert "END:VEVENT" in result
        assert "UID:t-abc@archon.vekn.net" in result
        assert "DTSTART:20250615T100000Z" in result
        assert "DTEND:20250615T180000Z" in result
        assert "SUMMARY:Test Tournament" in result

    def test_no_start_returns_empty(self):
        t = _make_tournament(start=None)
        assert _tournament_to_vevent(t, "20250101T000000Z") == ""

    def test_no_finish_defaults_to_8h(self):
        t = _make_tournament(start=JUNE_15_10AM)
        result = _tournament_to_vevent(t, "20250101T000000Z")
        assert "DTEND:20250615T180000Z" in result

    def test_online_location(self):
        t = _make_tournament(start=JUNE_15_10AM, online=True)
        result = _tournament_to_vevent(t, "20250101T000000Z")
        assert "LOCATION:Online" in result

    def test_url_format(self):
        t = _make_tournament(uid="t-abc", start=JUNE_15_10AM)
        result = _tournament_to_vevent(t, "20250101T000000Z")
        assert "URL;VALUE=URI:" in result

    def test_no_duplicate_url_in_description(self):
        t = _make_tournament(start=JUNE_15_10AM)
        result = _tournament_to_vevent(t, "20250101T000000Z")
        lines = result.split("\r\n")
        url_lines = [line for line in lines if "tournaments/t1" in line]
        assert len(url_lines) == 1
        assert url_lines[0].startswith("URL;VALUE=URI:")
