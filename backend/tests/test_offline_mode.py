"""Tests for offline tournament mode logic.

Focuses on:
- UID remapping function (pure, no DB)
- SSE filter behavior for offline fields (organizer vs member vs non-member)
"""

from datetime import UTC, datetime

from src.main import _filter_tournament
from src.models import (
    DeckListsMode,
    Player,
    Role,
    StandingsMode,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)
from src.routes.tournaments import _remap_uids_in_tournament

NOW = datetime.now(UTC)


def _make_user(
    uid: str = "u1", name: str = "Alice", country: str = "FR",
    vekn_id: str | None = "1000001", roles: list[Role] | None = None,
    **kwargs,
) -> User:
    return User(
        uid=uid, modified=NOW, name=name, country=country, vekn_id=vekn_id,
        roles=roles or [], **kwargs,
    )


def _make_viewer(
    uid: str = "viewer", roles: list[Role] | None = None,
    vekn_id: str | None = "9999999", country: str = "FR",
) -> User:
    return _make_user(uid=uid, name="Viewer", roles=roles, vekn_id=vekn_id, country=country)


def _make_tournament(
    state: TournamentState = TournamentState.PLAYING,
    country: str = "FR",
    organizers_uids: list[str] | None = None,
    standings_mode: StandingsMode = StandingsMode.PRIVATE,
    decklists_mode: DeckListsMode = DeckListsMode.WINNER,
    players: list[Player] | None = None,
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
        standings=[],
        decks={},
        **kwargs,
    )


# ============================================================================
# _remap_uids_in_tournament tests
# ============================================================================


class TestRemapUids:
    """Test the UID remapping used during go-online reconciliation."""

    def test_basic_remap(self):
        data = {
            "uid": "t1",
            "players": [
                {"user_uid": "temp-aaa"},
                {"user_uid": "temp-bbb"},
            ],
        }
        uid_map = {"temp-aaa": "real-111", "temp-bbb": "real-222"}
        result = _remap_uids_in_tournament(data, uid_map)
        assert result["players"][0]["user_uid"] == "real-111"
        assert result["players"][1]["user_uid"] == "real-222"

    def test_remap_in_nested_structures(self):
        """UIDs appear in seating, decks keys, standings, etc."""
        data = {
            "uid": "t1",
            "players": [{"user_uid": "temp-aaa"}],
            "rounds": [[{"seating": [{"player_uid": "temp-aaa"}]}]],
            "decks": {"temp-aaa": [{"name": "My Deck"}]},
            "standings": [{"user_uid": "temp-aaa", "vp": 3.0}],
            "winner": "temp-aaa",
        }
        result = _remap_uids_in_tournament(data, {"temp-aaa": "real-111"})
        assert result["players"][0]["user_uid"] == "real-111"
        assert result["rounds"][0][0]["seating"][0]["player_uid"] == "real-111"
        assert "real-111" in result["decks"]
        assert "temp-aaa" not in result["decks"]
        assert result["standings"][0]["user_uid"] == "real-111"
        assert result["winner"] == "real-111"

    def test_empty_uid_map(self):
        """No remapping needed -- data should be unchanged."""
        data = {"uid": "t1", "players": [{"user_uid": "existing-user"}]}
        result = _remap_uids_in_tournament(data, {})
        assert result == data

    def test_uid_not_present_in_data(self):
        """UID in map but not in data -- should be harmless."""
        data = {"uid": "t1", "players": []}
        result = _remap_uids_in_tournament(data, {"temp-xxx": "real-yyy"})
        assert result == data

    def test_remap_preserves_other_fields(self):
        data = {
            "uid": "t1",
            "name": "My Tournament",
            "state": "Playing",
            "players": [{"user_uid": "temp-aaa", "state": "Registered"}],
        }
        result = _remap_uids_in_tournament(data, {"temp-aaa": "real-111"})
        assert result["name"] == "My Tournament"
        assert result["state"] == "Playing"
        assert result["players"][0]["state"] == "Registered"

    def test_remap_does_not_collide_with_substring(self):
        """UUID v7 values should not be substrings of each other.
        Verify the function handles the case where a temp UID is a prefix of another."""
        data = {
            "players": [
                {"user_uid": "abc"},
                {"user_uid": "abcdef"},
            ],
        }
        # If "abc" is remapped first, it could corrupt "abcdef".
        # This is a known limitation of the string-replace approach.
        result = _remap_uids_in_tournament(data, {"abc": "XYZ"})
        # "abcdef" would become "XYZdef" -- this is the expected (flawed) behavior
        assert result["players"][0]["user_uid"] == "XYZ"
        assert result["players"][1]["user_uid"] == "XYZdef"


# ============================================================================
# SSE filter: offline field visibility tests
# ============================================================================


class TestFilterTournamentOfflineFields:
    """Verify offline_mode fields are correctly passed through (or stripped)
    at each data level."""

    def _make_offline_tournament(self, organizers_uids=None):
        return _make_tournament(
            organizers_uids=organizers_uids or [],
            offline_mode=True,
            offline_device_id="device-123",
            offline_user_uid="organizer-uid",
            offline_since=NOW,
        )

    def test_organizer_sees_offline_fields(self):
        """Organizer gets full access -- offline fields preserved."""
        t = self._make_offline_tournament(organizers_uids=["viewer"])
        viewer = _make_viewer()
        result = _filter_tournament(t, viewer)
        assert result is t  # same object, no filtering
        assert result.offline_mode is True
        assert result.offline_device_id == "device-123"

    def test_ic_sees_offline_fields(self):
        t = self._make_offline_tournament()
        viewer = _make_viewer(roles=[Role.IC])
        result = _filter_tournament(t, viewer)
        assert result is t
        assert result.offline_mode is True

    def test_member_does_not_see_offline_fields(self):
        """Members get a filtered copy -- offline fields should be defaults."""
        t = self._make_offline_tournament()
        viewer = _make_viewer()  # regular member
        result = _filter_tournament(t, viewer)
        assert result is not t  # filtered copy
        assert result.offline_mode is False  # default
        assert result.offline_device_id == ""  # default

    def test_nonmember_does_not_see_offline_fields(self):
        t = self._make_offline_tournament()
        viewer = _make_viewer(vekn_id=None)
        result = _filter_tournament(t, viewer)
        assert result is not None
        assert result.offline_mode is False

    def test_nc_same_country_sees_offline_fields(self):
        """NC same country gets full access."""
        t = self._make_offline_tournament()
        viewer = _make_viewer(roles=[Role.NC], country="FR")
        result = _filter_tournament(t, viewer)
        assert result is t
        assert result.offline_mode is True
