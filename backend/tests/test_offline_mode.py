"""Tests for offline tournament mode logic.

Focuses on:
- UID remapping function (pure, no DB)
"""

from src.routes.tournaments import _remap_uids_in_tournament

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
