"""Tests for offline tournament mode logic.

Focuses on:
- UID remapping function (pure, no DB)
"""

from src.routes.tournaments import _remap_uids_in_tournament


class TestRemapUids:
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
        """Temp UIDs appear in seating, standings, finals, raffles, winner."""
        data = {
            "uid": "t1",
            "players": [{"user_uid": "temp-aaa"}],
            "rounds": [[{"seating": [{"player_uid": "temp-aaa"}]}]],
            "finals": {"seating": [{"player_uid": "temp-aaa"}]},
            "standings": [{"user_uid": "temp-aaa", "vp": 3.0}],
            "raffles": [{"winners": ["temp-aaa", "real-existing"]}],
            "winner": "temp-aaa",
        }
        result = _remap_uids_in_tournament(data, {"temp-aaa": "real-111"})
        assert result["players"][0]["user_uid"] == "real-111"
        assert result["rounds"][0][0]["seating"][0]["player_uid"] == "real-111"
        assert result["finals"]["seating"][0]["player_uid"] == "real-111"
        assert result["standings"][0]["user_uid"] == "real-111"
        assert result["raffles"][0]["winners"] == ["real-111", "real-existing"]
        assert result["winner"] == "real-111"

    def test_empty_uid_map(self):
        data = {"uid": "t1", "players": [{"user_uid": "existing-user"}]}
        result = _remap_uids_in_tournament(data, {})
        assert result == data

    def test_uid_not_present_in_data(self):
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
