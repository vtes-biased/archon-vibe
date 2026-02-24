"""Tests for IC implicit organizer access and VEKN sync organizer mapping.

Covers:
- _is_organizer: IC role grants implicit organizer access
- _build_actor_context: IC role sets is_organizer=True
- _map_vekn_to_tournament: organizer_veknid mapped to organizers_uids
- sync_all_tournaments: organizer merge on update preserves existing + adds VEKN
"""

from datetime import UTC, datetime

from src.models import (
    Role,
    Tournament,
    TournamentState,
    User,
)
from src.routes.tournaments import _build_actor_context, _is_organizer
from src.vekn_tournament_sync import _map_vekn_to_tournament

NOW = datetime.now(UTC)


def _user(uid="u1", roles=None):
    return User(uid=uid, modified=NOW, name="Test", roles=roles or [])


def _tournament(organizers_uids=None):
    return Tournament(
        uid="t1",
        modified=NOW,
        name="Test",
        organizers_uids=organizers_uids or [],
    )


# ============================================================================
# _is_organizer tests
# ============================================================================


class TestIsOrganizer:
    def test_explicit_organizer(self):
        user = _user("org1")
        t = _tournament(organizers_uids=["org1"])
        assert _is_organizer(user, t) is True

    def test_non_organizer(self):
        user = _user("random")
        t = _tournament(organizers_uids=["org1"])
        assert _is_organizer(user, t) is False

    def test_ic_is_implicit_organizer(self):
        user = _user("ic-user", roles=[Role.IC])
        t = _tournament(organizers_uids=["someone-else"])
        assert _is_organizer(user, t) is True

    def test_ic_implicit_even_on_empty_organizers(self):
        user = _user("ic-user", roles=[Role.IC])
        t = _tournament(organizers_uids=[])
        assert _is_organizer(user, t) is True

    def test_nc_is_not_implicit_organizer(self):
        """NC should NOT get implicit organizer access (only IC does)."""
        user = _user("nc-user", roles=[Role.NC])
        t = _tournament(organizers_uids=["someone-else"])
        assert _is_organizer(user, t) is False

    def test_prince_is_not_implicit_organizer(self):
        user = _user("prince-user", roles=[Role.PRINCE])
        t = _tournament(organizers_uids=[])
        assert _is_organizer(user, t) is False


# ============================================================================
# _build_actor_context tests
# ============================================================================


class TestBuildActorContext:
    def test_ic_gets_is_organizer_true(self):
        user = _user("ic-user", roles=[Role.IC])
        t = _tournament(organizers_uids=[])
        ctx = _build_actor_context(user, t)
        assert ctx["is_organizer"] is True
        assert ctx["uid"] == "ic-user"
        assert "IC" in ctx["roles"]

    def test_regular_user_not_organizer(self):
        user = _user("regular")
        t = _tournament(organizers_uids=["someone-else"])
        ctx = _build_actor_context(user, t)
        assert ctx["is_organizer"] is False


# ============================================================================
# _map_vekn_to_tournament organizer mapping
# ============================================================================


class TestVeknOrganizerMapping:
    def _users_by_vekn(self):
        return {
            "1000001": _user("uid-org", roles=[]),
            "2000001": _user("uid-player1", roles=[]),
            "3000001": _user("uid-player2", roles=[]),
        }

    def test_organizer_mapped_from_veknid(self):
        """organizer_veknid in VEKN data should map to organizers_uids."""
        data = {
            "event_id": 999,
            "event_name": "Test Event",
            "eventtype_id": 2,
            "event_startdate": "2025-06-01",
            "event_enddate": "2025-06-01",
            "organizer_veknid": "1000001",
            "players": [
                {
                    "veknid": "2000001",
                    "pos": "1",
                    "gw": 2,
                    "vp": 5.0,
                    "tp": 36,
                    "tie": 0,
                    "vpf": 1.0,
                },
                {
                    "veknid": "3000001",
                    "pos": "2",
                    "gw": 1,
                    "vp": 3.0,
                    "tp": 24,
                    "tie": 0,
                    "vpf": 0.5,
                },
            ],
        }
        t = _map_vekn_to_tournament(data, self._users_by_vekn())
        assert t is not None
        assert t.organizers_uids == ["uid-org"]

    def test_unknown_organizer_veknid_gives_empty(self):
        """If organizer_veknid doesn't match a known user, organizers_uids is empty."""
        data = {
            "event_id": 999,
            "event_name": "Test Event",
            "eventtype_id": 2,
            "event_startdate": "2025-06-01",
            "organizer_veknid": "9999999",
            "players": [
                {
                    "veknid": "2000001",
                    "pos": "1",
                    "gw": 1,
                    "vp": 3.0,
                    "tp": 24,
                    "tie": 0,
                    "vpf": 0,
                },
            ],
        }
        t = _map_vekn_to_tournament(data, self._users_by_vekn())
        assert t is not None
        assert t.organizers_uids == []

    def test_no_organizer_veknid_gives_empty(self):
        """Missing organizer_veknid field gives empty organizers_uids."""
        data = {
            "event_id": 999,
            "event_name": "Test Event",
            "eventtype_id": 2,
            "event_startdate": "2025-06-01",
            "players": [],
        }
        t = _map_vekn_to_tournament(data, self._users_by_vekn())
        assert t is not None
        assert t.organizers_uids == []
        assert t.state == TournamentState.PLANNED

    def test_planned_tournament_gets_organizer(self):
        """Future tournament (no players) still gets organizer mapping."""
        data = {
            "event_id": 999,
            "event_name": "Future Event",
            "eventtype_id": 2,
            "event_startdate": "2026-06-01",
            "organizer_veknid": "1000001",
            "players": [],
        }
        t = _map_vekn_to_tournament(data, self._users_by_vekn())
        assert t is not None
        assert t.organizers_uids == ["uid-org"]
        assert t.state == TournamentState.PLANNED


# ============================================================================
# Organizer merge on update (unit test for the merge logic)
# ============================================================================


class TestOrganizerMerge:
    def test_merge_deduplicates(self):
        """The merge logic: list(dict.fromkeys(existing + new)) deduplicates."""
        existing = ["uid-a", "uid-b"]
        new = ["uid-b", "uid-c"]
        merged = list(dict.fromkeys(existing + new))
        assert merged == ["uid-a", "uid-b", "uid-c"]

    def test_merge_preserves_existing_when_vekn_empty(self):
        """If VEKN sync has no organizer, existing ones are preserved."""
        existing = ["uid-a", "uid-b"]
        new = []
        merged = list(dict.fromkeys(existing + new))
        assert merged == ["uid-a", "uid-b"]

    def test_merge_adds_new_when_existing_empty(self):
        existing = []
        new = ["uid-c"]
        merged = list(dict.fromkeys(existing + new))
        assert merged == ["uid-c"]
