"""Tests for access level projection functions."""

import pytest

from src.access_levels import compute_full, compute_member, compute_public


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

def _make_user(**overrides) -> dict:
    """Create a base user dict with sensible defaults."""
    base = {
        "uid": "u-001",
        "modified": "2026-01-01T00:00:00",
        "deleted_at": None,
        "name": "Alice",
        "country": "FR",
        "vekn_id": "1000001",
        "city": "Paris",
        "state": None,
        "nickname": "alice_v",
        "roles": [],
        "avatar_path": "/avatars/alice.webp",
        "contact_email": "alice@example.com",
        "contact_discord": "alice#1234",
        "contact_phone": "+33612345678",
        "coopted_by": "u-prince",
        "coopted_at": "2025-01-01T00:00:00",
        "vekn_synced": True,
        "vekn_synced_at": "2025-06-01T00:00:00",
        "local_modifications": [],
        "vekn_prefix": None,
        "resync_after": None,
        "calendar_token": "cal_secret_token",
        # Rating fields (after merge)
        "constructed_online": {"total": 100, "tournaments": []},
        "constructed_offline": None,
        "limited_online": None,
        "limited_offline": None,
        "wins": ["t-001"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# User: public level
# ---------------------------------------------------------------------------

class TestUserPublic:
    def test_regular_user_hidden(self):
        """Regular users (no NC/Prince role) are hidden at public level."""
        user = _make_user(roles=[])
        assert compute_public("user", user) is None

    def test_nc_user_visible(self):
        """NC users get a public representation with contact info."""
        user = _make_user(roles=["NC"], vekn_prefix="100")
        result = compute_public("user", user)
        assert result is not None
        assert result["uid"] == "u-001"
        assert result["name"] == "Alice"
        assert result["country"] == "FR"
        assert result["roles"] == ["NC"]
        assert result["vekn_prefix"] == "100"
        # Contact info included for NC/Prince
        assert result["contact_email"] == "alice@example.com"
        assert result["contact_discord"] == "alice#1234"
        assert result["contact_phone"] == "+33612345678"

    def test_prince_user_visible(self):
        """Prince users get a public representation."""
        user = _make_user(roles=["Prince"])
        result = compute_public("user", user)
        assert result is not None
        assert result["roles"] == ["Prince"]

    def test_public_excludes_member_fields(self):
        """Public projection should not include member-only fields."""
        user = _make_user(roles=["NC"])
        result = compute_public("user", user)
        assert "vekn_id" not in result
        assert "city" not in result
        assert "nickname" not in result
        assert "avatar_path" not in result
        assert "constructed_online" not in result
        assert "wins" not in result
        assert "calendar_token" not in result

    def test_ic_user_without_nc_prince_hidden(self):
        """IC user without NC/Prince role is hidden at public level."""
        user = _make_user(roles=["IC"])
        assert compute_public("user", user) is None

    def test_deleted_user_preserves_deleted_at(self):
        """Deleted NC user still has deleted_at in public projection."""
        user = _make_user(roles=["NC"], deleted_at="2026-02-01T00:00:00")
        result = compute_public("user", user)
        assert result is not None
        assert result["deleted_at"] == "2026-02-01T00:00:00"


# ---------------------------------------------------------------------------
# User: member level
# ---------------------------------------------------------------------------

class TestUserMember:
    def test_all_users_visible(self):
        """All users are visible at member level."""
        user = _make_user(roles=[])
        result = compute_member("user", user)
        assert result is not None
        assert result["uid"] == "u-001"

    def test_includes_identity_fields(self):
        """Member projection includes name, country, vekn_id, city, etc."""
        user = _make_user()
        result = compute_member("user", user)
        assert result["name"] == "Alice"
        assert result["country"] == "FR"
        assert result["vekn_id"] == "1000001"
        assert result["city"] == "Paris"
        assert result["nickname"] == "alice_v"
        assert result["avatar_path"] == "/avatars/alice.webp"

    def test_includes_rating_fields(self):
        """Member projection includes embedded rating data."""
        user = _make_user()
        result = compute_member("user", user)
        assert result["constructed_online"] == {"total": 100, "tournaments": []}
        assert result["wins"] == ["t-001"]

    def test_excludes_contact_info(self):
        """Member projection does not include contact info."""
        user = _make_user()
        result = compute_member("user", user)
        assert "contact_email" not in result
        assert "contact_discord" not in result
        assert "contact_phone" not in result

    def test_excludes_internal_fields(self):
        """Member projection excludes internal sync/admin fields."""
        user = _make_user()
        result = compute_member("user", user)
        assert "coopted_by" not in result
        assert "coopted_at" not in result
        assert "vekn_synced" not in result
        assert "local_modifications" not in result
        assert "resync_after" not in result
        assert "calendar_token" not in result


# ---------------------------------------------------------------------------
# User: full level
# ---------------------------------------------------------------------------

class TestUserFull:
    def test_includes_everything_except_calendar_token(self):
        """Full projection includes everything except calendar_token."""
        user = _make_user()
        result = compute_full("user", user)
        assert result["contact_email"] == "alice@example.com"
        assert result["coopted_by"] == "u-prince"
        assert result["resync_after"] is None
        assert "calendar_token" not in result

    def test_calendar_token_stripped(self):
        """Calendar token is always stripped from full projection."""
        user = _make_user(calendar_token="secret123")
        result = compute_full("user", user)
        assert "calendar_token" not in result


# ---------------------------------------------------------------------------
# Tournament fixtures
# ---------------------------------------------------------------------------

def _make_tournament(**overrides) -> dict:
    base = {
        "uid": "t-001",
        "modified": "2026-01-15T00:00:00",
        "deleted_at": None,
        "name": "Paris Open",
        "format": "Standard",
        "rank": "",
        "online": False,
        "start": "2026-03-01T10:00:00",
        "finish": "2026-03-01T18:00:00",
        "timezone": "Europe/Paris",
        "country": "FR",
        "league_uid": None,
        "state": "Playing",
        "organizers_uids": ["u-org1"],
        "venue": "Le Dernier Bar",
        "venue_url": "https://example.com",
        "address": "123 Rue de Rivoli",
        "map_url": "",
        "proxies": False,
        "multideck": False,
        "decklist_required": True,
        "description": "A fun tournament",
        "standings_mode": "Public",
        "decklists_mode": "Winner",
        "max_rounds": 3,
        "table_rooms": [],
        "round_time": 7200,
        "finals_time": 0,
        "time_extension_policy": "additions",
        "external_ids": {"vekn": "12345"},
        "checkin_code": "secret_checkin",
        "players": [],
        "rounds": [],
        "finals": None,
        "winner": "",
        "standings": [],
        "raffles": [],
        "vekn_pushed_at": "2026-02-01T00:00:00",
        "offline_mode": False,
        "offline_device_id": "",
        "offline_user_uid": "",
        "offline_since": None,
        "timer": {"started_at": None, "elapsed_before_pause": 0.0, "paused": True},
        "table_extra_time": {},
        "table_paused_at": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tournament: public level
# ---------------------------------------------------------------------------

class TestTournamentPublic:
    def test_minimal_fields_only(self):
        """Public projection only has core scheduling fields."""
        t = _make_tournament()
        result = compute_public("tournament", t)
        assert result["uid"] == "t-001"
        assert result["name"] == "Paris Open"
        assert result["state"] == "Playing"
        assert result["country"] == "FR"

    def test_excludes_sensitive_fields(self):
        """Public projection excludes organizer details, checkin code, etc."""
        t = _make_tournament()
        result = compute_public("tournament", t)
        assert "organizers_uids" not in result
        assert "checkin_code" not in result
        assert "players" not in result
        assert "rounds" not in result
        assert "decks" not in result
        assert "vekn_pushed_at" not in result
        assert "description" not in result


# ---------------------------------------------------------------------------
# Tournament: member level
# ---------------------------------------------------------------------------

class TestTournamentMember:
    def test_includes_most_fields(self):
        """Member projection includes nearly everything."""
        t = _make_tournament()
        result = compute_member("tournament", t)
        assert result["organizers_uids"] == ["u-org1"]
        assert result["description"] == "A fun tournament"
        assert result["players"] == []
        assert result["external_ids"] == {"vekn": "12345"}

    def test_excludes_checkin_code(self):
        """Member projection strips checkin_code."""
        t = _make_tournament(checkin_code="secret123")
        result = compute_member("tournament", t)
        assert "checkin_code" not in result

    def test_excludes_vekn_pushed_at(self):
        """Member projection strips vekn_pushed_at."""
        t = _make_tournament(vekn_pushed_at="2026-02-01T00:00:00")
        result = compute_member("tournament", t)
        assert "vekn_pushed_at" not in result


# ---------------------------------------------------------------------------
# Tournament: full level
# ---------------------------------------------------------------------------

class TestTournamentFull:
    def test_includes_everything(self):
        """Full projection includes all fields."""
        t = _make_tournament()
        result = compute_full("tournament", t)
        assert result["checkin_code"] == "secret_checkin"
        assert result["vekn_pushed_at"] == "2026-02-01T00:00:00"
        assert result["organizers_uids"] == ["u-org1"]


# ---------------------------------------------------------------------------
# Sanction
# ---------------------------------------------------------------------------

def _make_sanction(**overrides) -> dict:
    base = {
        "uid": "s-001",
        "modified": "2026-01-10T00:00:00",
        "deleted_at": None,
        "user_uid": "u-001",
        "issued_by_uid": "u-judge",
        "tournament_uid": "t-001",
        "level": "warning",
        "category": "procedural_error",
        "subcategory": "game_rule_violation",
        "round_number": 1,
        "description": "Minor rules violation",
        "issued_at": "2026-01-10T00:00:00",
        "expires_at": None,
        "lifted_at": None,
        "lifted_by_uid": None,
    }
    base.update(overrides)
    return base


class TestSanction:
    def test_public_hidden(self):
        """Sanctions are not visible at public level."""
        s = _make_sanction()
        assert compute_public("sanction", s) is None

    def test_member_sees_full(self):
        """Members see full sanction data."""
        s = _make_sanction()
        result = compute_member("sanction", s)
        assert result["uid"] == "s-001"
        assert result["level"] == "warning"
        assert result["description"] == "Minor rules violation"

    def test_full_same_as_member(self):
        """Full projection is identical to member for sanctions."""
        s = _make_sanction()
        assert compute_member("sanction", s) == compute_full("sanction", s)


# ---------------------------------------------------------------------------
# Deck
# ---------------------------------------------------------------------------

def _make_deck(**overrides) -> dict:
    base = {
        "uid": "d-001",
        "modified": "2026-02-01T00:00:00",
        "deleted_at": None,
        "tournament_uid": "t-001",
        "user_uid": "u-001",
        "round": None,
        "name": "Ventrue Lawfirm",
        "author": "Alice",
        "comments": "A classic deck",
        "cards": {"100001": 4, "100002": 2},
        "attribution": "1000001",
    }
    base.update(overrides)
    return base


class TestDeck:
    def test_public_hidden(self):
        """Decks are never visible at public level."""
        d = _make_deck()
        assert compute_public("deck", d) is None

    def test_member_hidden_when_not_public(self):
        """Decks without public flag are hidden at member level."""
        d = _make_deck()
        assert compute_member("deck", d) is None

    def test_member_visible_when_public(self):
        """Decks with public=True are visible at member level."""
        d = _make_deck(public=True)
        result = compute_member("deck", d)
        assert result is not None
        assert result["uid"] == "d-001"
        assert result["name"] == "Ventrue Lawfirm"
        assert result["public"] is True

    def test_member_hidden_when_public_false(self):
        """Decks with explicit public=False are hidden at member level."""
        d = _make_deck(public=False)
        assert compute_member("deck", d) is None

    def test_full_visible(self):
        """Full access always sees decks."""
        d = _make_deck()
        result = compute_full("deck", d)
        assert result["uid"] == "d-001"
        assert result["name"] == "Ventrue Lawfirm"
        assert result["cards"] == {"100001": 4, "100002": 2}


# ---------------------------------------------------------------------------
# League
# ---------------------------------------------------------------------------

def _make_league(**overrides) -> dict:
    base = {
        "uid": "l-001",
        "modified": "2026-01-01T00:00:00",
        "deleted_at": None,
        "name": "French National League",
        "kind": "League",
        "standings_mode": "RTP",
        "format": "Standard",
        "online": False,
        "country": "FR",
        "start": "2026-01-01T00:00:00",
        "finish": "2026-12-31T23:59:59",
        "timezone": "Europe/Paris",
        "description": "Year-long league",
        "organizers_uids": ["u-nc-fr"],
        "parent_uid": None,
        "allow_no_finals": False,
    }
    base.update(overrides)
    return base


class TestLeague:
    def test_public_full_data(self):
        """Leagues are fully visible at all levels."""
        lg = _make_league()
        result = compute_public("league", lg)
        assert result["name"] == "French National League"
        assert result["organizers_uids"] == ["u-nc-fr"]

    def test_all_levels_identical(self):
        """All three projections return the same data for leagues."""
        lg = _make_league()
        pub = compute_public("league", lg)
        mem = compute_member("league", lg)
        full = compute_full("league", lg)
        assert pub == mem == full


# ---------------------------------------------------------------------------
# Dispatch / error handling
# ---------------------------------------------------------------------------

class TestDispatch:
    def test_unknown_type_raises(self):
        """Unknown object type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown object type"):
            compute_public("foobar", {})
        with pytest.raises(ValueError, match="Unknown object type"):
            compute_member("foobar", {})
        with pytest.raises(ValueError, match="Unknown object type"):
            compute_full("foobar", {})
