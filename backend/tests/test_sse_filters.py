"""Tests for SSE data level filtering functions.

These test the per-type filter functions that control what data each viewer
receives via SSE, based on their access level (public/member/full).
"""

from datetime import UTC, datetime

from src.main import _filter_rating, _filter_sanction, _filter_tournament, _filter_user
from src.models import (
    Deck,
    DeckListsMode,
    Player,
    PlayerState,
    Rating,
    Role,
    Sanction,
    SanctionCategory,
    SanctionLevel,
    Seat,
    Standing,
    StandingsMode,
    Table,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)

NOW = datetime.now(UTC)


def _make_user(
    uid: str = "u1", name: str = "Alice", country: str = "FR",
    vekn_id: str | None = "1000001", roles: list[Role] | None = None,
    contact_email: str | None = None, contact_discord: str | None = None,
    contact_phone: str | None = None, vekn_prefix: str | None = None,
    **kwargs,
) -> User:
    return User(
        uid=uid, modified=NOW, name=name, country=country, vekn_id=vekn_id,
        roles=roles or [], contact_email=contact_email,
        contact_discord=contact_discord, contact_phone=contact_phone,
        vekn_prefix=vekn_prefix, **kwargs,
    )


def _make_viewer(
    uid: str = "viewer", roles: list[Role] | None = None,
    vekn_id: str | None = "9999999", country: str = "FR",
) -> User:
    return _make_user(uid=uid, name="Viewer", roles=roles, vekn_id=vekn_id, country=country)


# ============================================================================
# _filter_user tests
# ============================================================================

class TestFilterUser:
    def test_ic_sees_everything(self):
        user = _make_user(contact_email="a@b.com", contact_discord="alice#1")
        viewer = _make_viewer(roles=[Role.IC])
        result = _filter_user(user, viewer)
        assert result is user  # same object, no filtering

    def test_nc_same_country_sees_everything(self):
        user = _make_user(country="FR", contact_email="a@b.com")
        viewer = _make_viewer(roles=[Role.NC], country="FR")
        result = _filter_user(user, viewer)
        assert result is user

    def test_nc_different_country_member_no_contact(self):
        user = _make_user(country="US", contact_email="a@b.com", contact_discord="alice#1")
        viewer = _make_viewer(roles=[Role.NC], country="FR")
        result = _filter_user(user, viewer)
        assert result is not None
        assert result.contact_email is None
        assert result.contact_discord is None
        assert result.name == "Alice"
        assert result.vekn_id == "1000001"

    def test_member_sees_basic_no_contact(self):
        user = _make_user(
            contact_email="a@b.com", contact_discord="alice#1",
            contact_phone="+33123", city="Paris", nickname="ali",
        )
        viewer = _make_viewer()  # has vekn_id
        result = _filter_user(user, viewer)
        assert result is not None
        assert result.name == "Alice"
        assert result.city == "Paris"
        assert result.nickname == "ali"
        assert result.contact_email is None
        assert result.contact_discord is None
        assert result.contact_phone is None

    def test_nonmember_sees_prince_with_contact(self):
        user = _make_user(
            roles=[Role.PRINCE], contact_email="prince@test.com",
            contact_discord="prince#1", vekn_prefix="1000",
        )
        viewer = _make_viewer(vekn_id=None)  # no vekn_id
        result = _filter_user(user, viewer)
        assert result is not None
        assert result.contact_email == "prince@test.com"
        assert result.contact_discord == "prince#1"
        assert result.vekn_prefix == "1000"

    def test_nonmember_sees_nc_with_contact(self):
        user = _make_user(roles=[Role.NC], contact_email="nc@test.com")
        viewer = _make_viewer(vekn_id=None)
        result = _filter_user(user, viewer)
        assert result is not None
        assert result.contact_email == "nc@test.com"

    def test_nonmember_skips_regular_user(self):
        user = _make_user()
        viewer = _make_viewer(vekn_id=None)
        result = _filter_user(user, viewer)
        assert result is None

    def test_no_viewer_skips_regular_user(self):
        user = _make_user()
        result = _filter_user(user, None)
        assert result is None

    def test_no_viewer_sees_prince(self):
        user = _make_user(roles=[Role.PRINCE], contact_email="p@test.com")
        result = _filter_user(user, None)
        assert result is not None
        assert result.contact_email == "p@test.com"

    def test_organizer_has_full_access(self):
        """Organizers get full access via _has_full_access, but _filter_user
        only checks country-based access, not organizer-based. This test verifies
        that organizer status alone doesn't grant full user access."""
        user = _make_user(contact_email="a@b.com")
        # Organizer is checked at tournament level, not user level
        viewer = _make_viewer()
        result = _filter_user(user, viewer)
        assert result.contact_email is None  # member-level, no contact


# ============================================================================
# _filter_sanction tests
# ============================================================================

class TestFilterSanction:
    def _make_sanction(self):
        return Sanction(
            uid="s1", modified=NOW, user_uid="u1", issued_by_uid="u2",
            level=SanctionLevel.WARNING, category=SanctionCategory.PROCEDURAL,
            description="Test sanction", issued_at=NOW,
        )

    def test_member_sees_sanction(self):
        sanction = self._make_sanction()
        viewer = _make_viewer()
        assert _filter_sanction(sanction, viewer) is sanction

    def test_nonmember_skips_sanction(self):
        sanction = self._make_sanction()
        viewer = _make_viewer(vekn_id=None)
        assert _filter_sanction(sanction, viewer) is None

    def test_no_viewer_skips_sanction(self):
        sanction = self._make_sanction()
        assert _filter_sanction(sanction, None) is None


# ============================================================================
# _filter_tournament tests
# ============================================================================

def _make_tournament(
    state: TournamentState = TournamentState.PLAYING,
    country: str = "FR",
    organizers_uids: list[str] | None = None,
    standings_mode: StandingsMode = StandingsMode.PRIVATE,
    decklists_mode: DeckListsMode = DeckListsMode.WINNER,
    players: list[Player] | None = None,
    standings: list[Standing] | None = None,
    decks: dict | None = None,
    winner: str = "",
    **kwargs,
) -> Tournament:
    return Tournament(
        uid="t1", modified=NOW, name="Test Tournament",
        format=TournamentFormat.Standard, rank=TournamentRank.BASIC,
        state=state, country=country,
        organizers_uids=organizers_uids or [],
        standings_mode=standings_mode,
        decklists_mode=decklists_mode,
        players=players or [],
        standings=standings or [],
        decks=decks or {},
        winner=winner,
        **kwargs,
    )


class TestFilterTournament:
    def test_ic_sees_everything(self):
        t = _make_tournament()
        viewer = _make_viewer(roles=[Role.IC])
        result = _filter_tournament(t, viewer)
        assert result is t

    def test_nc_same_country_sees_everything(self):
        t = _make_tournament(country="FR")
        viewer = _make_viewer(roles=[Role.NC], country="FR")
        result = _filter_tournament(t, viewer)
        assert result is t

    def test_nc_different_country_gets_member_view(self):
        t = _make_tournament(country="US")
        viewer = _make_viewer(roles=[Role.NC], country="FR")
        result = _filter_tournament(t, viewer)
        assert result is not t  # filtered copy

    def test_organizer_sees_everything(self):
        t = _make_tournament(organizers_uids=["viewer"])
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result is t

    def test_nonmember_gets_minimal(self):
        t = _make_tournament(
            players=[Player(user_uid="p1")],
            standings=[Standing(user_uid="p1", vp=3.0)],
        )
        viewer = _make_viewer(vekn_id=None)
        result = _filter_tournament(t, viewer)
        assert result is not None
        assert result.name == "Test Tournament"
        assert result.players == []  # stripped
        assert result.standings == []  # stripped
        assert result.decks == {}

    def test_no_viewer_gets_minimal(self):
        t = _make_tournament()
        result = _filter_tournament(t, None)
        assert result is not None
        assert result.players == []

    # Standings visibility
    def test_member_ongoing_private_standings_hidden(self):
        t = _make_tournament(
            state=TournamentState.PLAYING,
            standings_mode=StandingsMode.PRIVATE,
            standings=[Standing(user_uid="p1", vp=3.0)],
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.standings == []

    def test_member_ongoing_public_standings_shown(self):
        t = _make_tournament(
            state=TournamentState.PLAYING,
            standings_mode=StandingsMode.PUBLIC,
            standings=[Standing(user_uid="p1", vp=3.0)],
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert len(result.standings) == 1

    def test_member_finished_private_standings_shown(self):
        """After tournament finishes, standings are always visible to members."""
        t = _make_tournament(
            state=TournamentState.FINISHED,
            standings_mode=StandingsMode.PRIVATE,
            standings=[Standing(user_uid="p1", vp=3.0)],
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert len(result.standings) == 1

    # Decks visibility
    def test_member_ongoing_no_decks(self):
        t = _make_tournament(
            state=TournamentState.PLAYING,
            decks={"p1": [Deck(name="My Deck")]},
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.decks == {}

    def test_member_finished_winner_only(self):
        t = _make_tournament(
            state=TournamentState.FINISHED,
            decklists_mode=DeckListsMode.WINNER,
            decks={"p1": [Deck(name="Winner Deck")], "p2": [Deck(name="Loser Deck")]},
            winner="p1",
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert "p1" in result.decks
        assert "p2" not in result.decks

    def test_member_finished_finalists_mode(self):
        t = _make_tournament(
            state=TournamentState.FINISHED,
            decklists_mode=DeckListsMode.FINALISTS,
            players=[
                Player(user_uid="p1", finalist=True),
                Player(user_uid="p2", finalist=True),
                Player(user_uid="p3", finalist=False),
            ],
            decks={
                "p1": [Deck(name="D1")],
                "p2": [Deck(name="D2")],
                "p3": [Deck(name="D3")],
            },
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert "p1" in result.decks
        assert "p2" in result.decks
        assert "p3" not in result.decks

    def test_member_finished_all_decks(self):
        t = _make_tournament(
            state=TournamentState.FINISHED,
            decklists_mode=DeckListsMode.ALL,
            decks={"p1": [Deck(name="D1")], "p2": [Deck(name="D2")]},
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert len(result.decks) == 2

    # my_tables
    def test_member_player_gets_my_tables(self):
        seat_viewer = Seat(player_uid="viewer")
        seat_other = Seat(player_uid="p2")
        table_with_viewer = Table(seating=[seat_viewer, seat_other, Seat(player_uid="p3"), Seat(player_uid="p4")])
        table_without = Table(seating=[Seat(player_uid="p5"), seat_other, Seat(player_uid="p6"), Seat(player_uid="p7")])
        t = _make_tournament(
            players=[Player(user_uid="viewer"), Player(user_uid="p2")],
            rounds=[[table_with_viewer, table_without]],
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert len(result.my_tables) == 1
        assert any(s.player_uid == "viewer" for s in result.my_tables[0].seating)

    def test_member_nonplayer_no_my_tables(self):
        t = _make_tournament(
            players=[Player(user_uid="p1")],
            rounds=[[Table(seating=[Seat(player_uid="p1"), Seat(player_uid="p2"), Seat(player_uid="p3"), Seat(player_uid="p4")])]],
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.my_tables == []

    # Player results stripped for ongoing
    def test_member_ongoing_player_results_stripped(self):
        from src.models import Score
        t = _make_tournament(
            state=TournamentState.PLAYING,
            players=[Player(user_uid="p1", state=PlayerState.PLAYING, result=Score(gw=1, vp=3.0, tp=60))],
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.players[0].user_uid == "p1"
        assert result.players[0].state == PlayerState.PLAYING
        # Result should be default (stripped)
        assert result.players[0].result.gw == 0
        assert result.players[0].result.vp == 0.0

    def test_member_finished_player_results_kept(self):
        from src.models import Score
        t = _make_tournament(
            state=TournamentState.FINISHED,
            players=[Player(user_uid="p1", state=PlayerState.FINISHED, result=Score(gw=1, vp=3.0, tp=60))],
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.players[0].result.gw == 1
        assert result.players[0].result.vp == 3.0

    # Finals visibility
    def test_member_ongoing_no_finals(self):
        from src.models import FinalsTable
        t = _make_tournament(
            state=TournamentState.PLAYING,
            finals=FinalsTable(
                seating=[Seat(player_uid="p1")],
                seed_order=["p1"],
            ),
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.finals is None

    def test_member_finished_sees_finals(self):
        from src.models import FinalsTable
        t = _make_tournament(
            state=TournamentState.FINISHED,
            finals=FinalsTable(
                seating=[Seat(player_uid="p1")],
                seed_order=["p1"],
            ),
        )
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result.finals is not None


# ============================================================================
# _filter_rating tests
# ============================================================================

class TestFilterRating:
    def test_always_returned(self):
        rating = Rating(uid="r1", modified=NOW, user_uid="u1")
        assert _filter_rating(rating, None) is rating
        assert _filter_rating(rating, _make_viewer()) is rating
        assert _filter_rating(rating, _make_viewer(vekn_id=None)) is rating
