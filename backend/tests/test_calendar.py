"""Tests for calendar feed logic."""

from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from src import db
from src.models import (
    Player,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)
from src.routes.calendar import (
    FINISHED_WINDOW_DAYS,
    _escape_ical,
    _format_dt,
    _matches_agenda,
    _tournament_to_vevent,
    tournament_calendar,
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


class TestMatchesAgenda:
    def test_organizer_always_matches(self):
        t = _make_tournament(organizers_uids=["user1"], state=TournamentState.FINISHED)
        assert _matches_agenda(t, "user1", "US", [], True) is True

    def test_participant_always_matches(self):
        t = _make_tournament(
            players=[Player(user_uid="user1")],
            state=TournamentState.FINISHED,
        )
        assert _matches_agenda(t, "user1", "US", [], True) is True

    def test_same_country_non_finished(self):
        t = _make_tournament(country="FR", state=TournamentState.PLANNED)
        assert _matches_agenda(t, "user1", "FR", [], True) is True

    def test_same_country_finished_no_match(self):
        """Finished tournaments only match if user organizes or participates."""
        t = _make_tournament(country="FR", state=TournamentState.FINISHED)
        assert _matches_agenda(t, "user1", "FR", [], True) is False

    def test_online_matches(self):
        t = _make_tournament(online=True, country="US", state=TournamentState.PLANNED)
        assert _matches_agenda(t, "user1", "FR", [], True) is True

    def test_online_finished_no_match(self):
        t = _make_tournament(online=True, state=TournamentState.FINISHED)
        assert _matches_agenda(t, "user1", "FR", [], True) is False

    def test_nc_same_continent(self):
        t = _make_tournament(country="DE", rank=TournamentRank.NC)
        assert _matches_agenda(t, "user1", "FR", ["FR", "DE", "ES"], True) is True

    def test_cc_same_continent(self):
        t = _make_tournament(country="DE", rank=TournamentRank.CC)
        assert _matches_agenda(t, "user1", "FR", ["FR", "DE"], True) is True

    def test_basic_different_country_no_match(self):
        t = _make_tournament(country="US")
        assert _matches_agenda(t, "user1", "FR", ["FR", "DE"], True) is False

    def test_nc_different_continent_no_match(self):
        t = _make_tournament(country="US", rank=TournamentRank.NC)
        assert _matches_agenda(t, "user1", "FR", ["FR", "DE"], True) is False

    def test_no_user_country(self):
        """User with no country -- only organizer/participant/online matches."""
        t = _make_tournament(country="FR")
        assert _matches_agenda(t, "user1", None, [], True) is False

    def test_online_opt_out_gates_discovery_only(self):
        """?online=false drops online events from discovery — never own events."""
        t = _make_tournament(online=True, country="US", state=TournamentState.PLANNED)
        assert _matches_agenda(t, "user1", "FR", [], False) is False
        own = _make_tournament(online=True, players=[Player(user_uid="user1")])
        assert _matches_agenda(own, "user1", "FR", [], False) is True


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

    def test_naive_anchored_in_tournament_timezone(self):
        """Naive wall-clock must be anchored in the event tz, not stamped UTC."""
        naive = datetime(2025, 6, 15, 14, 0, 0)  # CEST
        assert _format_dt(naive, "Europe/Paris") == "20250615T120000Z"

    def test_unknown_timezone_falls_back_to_utc(self):
        naive = datetime(2025, 6, 15, 14, 0, 0)
        assert _format_dt(naive, "Not/AZone") == "20250615T140000Z"

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

    def test_naive_start_uses_tournament_timezone(self):
        """A 10:00 Paris event must reach subscribers as 08:00 UTC, not 10:00 UTC."""
        t = _make_tournament(
            start=datetime(2025, 6, 15, 10, 0, 0), timezone="Europe/Paris"
        )
        result = _tournament_to_vevent(t, "20250101T000000Z")
        assert "DTSTART:20250615T080000Z" in result
        assert "DTEND:20250615T160000Z" in result

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


# Regression for the "always anonymous" bug: calendar_token must be queryable
# yet never leak into any SSE projection.


def _make_user(token: str | None = None) -> User:
    return User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Cal Tester",
        country="US",
        calendar_token=token,
    )


@pytest.mark.asyncio
async def test_calendar_token_lookup_round_trip(test_db):
    user = _make_user(token="tok-abc123")
    await db.save_user(user)

    found = await db.get_user_by_calendar_token("tok-abc123")
    assert found is not None
    assert found.uid == user.uid

    assert await db.get_user_by_calendar_token("nope") is None


@pytest.mark.asyncio
async def test_calendar_token_survives_read_modify_write(test_db):
    """A profile edit (load via get_user_by_uid → save) must not wipe the token.

    get_user_by_uid does NOT carry the token (kept out of "full"); preservation
    relies on save_object COALESCE, so the reloaded model has token=None yet the
    stored token survives the write.
    """
    user = _make_user(token="keep-me")
    await db.save_user(user)

    reloaded = await db.get_user_by_uid(user.uid)
    assert reloaded is not None
    assert reloaded.calendar_token is None  # stripped from "full"
    reloaded.name = "Renamed"
    await db.save_user(reloaded)

    assert (await db.get_user_by_calendar_token("keep-me")).uid == user.uid
    assert await db.get_calendar_token(user.uid) == "keep-me"


@pytest.mark.asyncio
async def test_calendar_token_preserved_by_unhydrated_writer(test_db):
    """Regression: the nightly VEKN sync rebuilds a User (token=None) and saves it.

    COALESCE must keep the stored token instead of nulling it.
    """
    user = _make_user(token="sync-safe")
    await db.save_user(user)

    # Simulate vekn_sync: a fresh model for the same uid, no token field set.
    rebuilt = User(
        uid=user.uid,
        modified=datetime.now(UTC),
        name="From VEKN",
        country="FR",
    )
    await db.save_user(rebuilt)

    assert (await db.get_user_by_calendar_token("sync-safe")).uid == user.uid


@pytest.mark.asyncio
async def test_clear_calendar_token(test_db):
    """clear_calendar_token drops the feed token even though save_object COALESCEs."""
    user = _make_user(token="revoke-me")
    await db.save_user(user)

    await db.clear_calendar_token(user.uid)

    assert await db.get_calendar_token(user.uid) is None
    assert await db.get_user_by_calendar_token("revoke-me") is None
    # A later unhydrated update must not resurrect it.
    reloaded = await db.get_user_by_uid(user.uid)
    reloaded.name = "Renamed"
    await db.save_user(reloaded)
    assert await db.get_user_by_calendar_token("revoke-me") is None


@pytest.mark.asyncio
async def test_calendar_token_absent_from_all_projections(test_db):
    """The token lives only in its column, never in public/member/full JSONB."""
    user = _make_user(token="secret-xyz")
    await db.save_user(user)

    async with db.get_connection() as conn:
        row = await (
            await conn.execute(
                'SELECT "public"::text, "member"::text, "full"::text, calendar_token '
                "FROM objects WHERE uid = %s",
                (user.uid,),
            )
        ).fetchone()

    public_json, member_json, full_json, col = row
    assert col == "secret-xyz"
    for level in (public_json, member_json, full_json):
        assert level is None or "secret-xyz" not in level
        assert level is None or "calendar_token" not in level


@pytest.mark.asyncio
async def test_calendar_token_not_resolved_for_deleted_user(test_db):
    user = _make_user(token="ghost")
    await db.save_user(user)
    await db.soft_delete_user(user.uid)

    assert await db.get_user_by_calendar_token("ghost") is None


@pytest.mark.asyncio
async def test_personal_feed_keeps_recently_finished_own_events(test_db):
    """Recently-finished own events stay in the personal feed (bounded window);
    finished discovery events and out-of-window own events do not — and the
    anonymous feed stays upcoming-only entirely."""
    user = _make_user(token="feed-window")
    await db.save_user(user)
    played = [Player(user_uid=user.uid)]
    now = datetime.now(UTC)

    recent_own = _make_tournament(
        uid=str(uuid7()),
        state=TournamentState.FINISHED,
        country="US",
        players=played,
        start=now - timedelta(days=10),
        finish=now - timedelta(days=9),
    )
    old_own = _make_tournament(
        uid=str(uuid7()),
        state=TournamentState.FINISHED,
        country="US",
        players=played,
        start=now - timedelta(days=FINISHED_WINDOW_DAYS + 10),
        finish=now - timedelta(days=FINISHED_WINDOW_DAYS + 9),
    )
    recent_other = _make_tournament(
        uid=str(uuid7()),
        state=TournamentState.FINISHED,
        country="US",
        start=now - timedelta(days=10),
        finish=now - timedelta(days=9),
    )
    async with db.get_connection() as conn:
        for t in (recent_own, old_own, recent_other):
            await db.save_tournament(t, conn=conn)

    async def feed(token):
        resp = await tournament_calendar(
            token=token, country=None, online=True, format=None, league=None
        )
        return resp.body.decode()

    personal = await feed("feed-window")
    assert recent_own.uid in personal
    assert old_own.uid not in personal
    assert recent_other.uid not in personal

    anonymous = await feed(None)
    assert recent_own.uid not in anonymous
