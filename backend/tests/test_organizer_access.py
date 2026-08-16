"""Tests for implicit organizer access and VEKN sync organizer mapping."""

from datetime import UTC, datetime

from src import permissions
from src.models import (
    League,
    Role,
    Tournament,
    TournamentState,
    User,
)
from src.routes.tournaments import _build_actor_context
from src.vekn_tournament_sync import _map_vekn_to_tournament

NOW = datetime.now(UTC)


def _user(uid="u1", roles=None, country=None):
    return User(uid=uid, modified=NOW, name="Test", roles=roles or [], country=country)


def _league(country=None, organizers_uids=None, open_to_country_princes=False):
    return League(
        uid="lg1",
        modified=NOW,
        name="Test",
        country=country,
        organizers_uids=organizers_uids or [],
        open_to_country_princes=open_to_country_princes,
    )


def _tournament(organizers_uids=None, country=None):
    return Tournament(
        uid="t1",
        modified=NOW,
        name="Test",
        organizers_uids=organizers_uids or [],
        country=country,
    )


class TestIsOrganizer:
    def test_explicit_organizer(self):
        user = _user("org1")
        t = _tournament(organizers_uids=["org1"])
        assert permissions.is_organizer(user, t) is True

    def test_non_organizer(self):
        user = _user("random")
        t = _tournament(organizers_uids=["org1"])
        assert permissions.is_organizer(user, t) is False

    def test_ic_is_implicit_organizer(self):
        user = _user("ic-user", roles=[Role.IC])
        t = _tournament(organizers_uids=["someone-else"])
        assert permissions.is_organizer(user, t) is True

    def test_ic_implicit_even_on_empty_organizers(self):
        user = _user("ic-user", roles=[Role.IC])
        t = _tournament(organizers_uids=[])
        assert permissions.is_organizer(user, t) is True

    def test_nc_same_country_is_implicit_organizer(self):
        user = _user("nc-user", roles=[Role.NC], country="France")
        t = _tournament(organizers_uids=["someone-else"], country="France")
        assert permissions.is_organizer(user, t) is True

    def test_prince_same_country_not_implicit_organizer(self):
        user = _user("prince-user", roles=[Role.PRINCE], country="France")
        t = _tournament(organizers_uids=[], country="France")
        assert permissions.is_organizer(user, t) is False

    def test_nc_different_country_not_organizer(self):
        user = _user("nc-user", roles=[Role.NC], country="France")
        t = _tournament(organizers_uids=[], country="Spain")
        assert permissions.is_organizer(user, t) is False

    def test_nc_no_country_not_organizer(self):
        user = _user("nc-user", roles=[Role.NC])
        t = _tournament(organizers_uids=[], country="France")
        assert permissions.is_organizer(user, t) is False

    def test_nc_tournament_no_country_not_organizer(self):
        user = _user("nc-user", roles=[Role.NC], country="France")
        t = _tournament(organizers_uids=[])
        assert permissions.is_organizer(user, t) is False


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


class TestCanLinkTournamentToLeague:
    """The open_to_country_princes flag governs the same-country Prince attach grant.
    Engine logic is covered in permissions.rs; this pins the one seam it can't reach —
    the flag surviving permissions.py's marshalling into OwnedResource."""

    def test_prince_attach_gated_by_flag(self):
        prince = _user("p", roles=[Role.PRINCE], country="France")
        assert permissions.can_link_tournament_to_league(
            prince, _league(country="France", open_to_country_princes=True)
        )
        # Same Prince, msgspec default (flag unset) → denied
        assert not permissions.can_link_tournament_to_league(
            prince, _league(country="France")
        )


class TestVeknOrganizerMapping:
    def _users_by_vekn(self):
        return {
            "1000001": _user("uid-org", roles=[]),
            "2000001": _user("uid-player1", roles=[]),
            "3000001": _user("uid-player2", roles=[]),
        }

    def test_organizer_mapped_from_veknid(self):
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
