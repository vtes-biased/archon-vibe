"""Tests for access level projection functions."""

import base64

import msgspec
import pytest
from src.access_levels import (
    _API_SYNC_FIELDS,
    _PLAYER_API_EXCLUDE,
    _TOURNAMENT_API_EXCLUDE,
    _TOURNAMENT_MEMBER_EXCLUDE,
    _USER_API_FIELDS,
    compute_api,
    compute_full,
    compute_member,
    compute_public,
)
from src.models import ObjectType, Player, Tournament, User


def _make_user(**overrides) -> dict:
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
        "community_links": [
            {"type": "discord", "url": "https://discord.gg/test", "label": "Test"}
        ],
        "coopted_by": "u-prince",
        "coopted_at": "2025-01-01T00:00:00",
        "vekn_synced": True,
        "vekn_synced_at": "2025-06-01T00:00:00",
        "local_modifications": [],
        "vekn_prefix": None,
        "calendar_token": "cal_secret_token",
        "deceased_at": "2026-05-01T00:00:00",
        "deceased_by_uid": "u-nc-fr",
        "constructed_online": {"total": 100, "tournaments": []},
        "constructed_offline": None,
        "limited_online": None,
        "limited_offline": None,
        "wins": ["t-001"],
    }
    base.update(overrides)
    return base


class TestUserPublic:
    def test_regular_user_hidden(self):
        user = _make_user(roles=[], community_links=[])
        assert compute_public(ObjectType.USER, user) is None

    def test_regular_user_with_links_visible(self):
        user = _make_user(roles=[])
        result = compute_public(ObjectType.USER, user)
        assert result is not None
        assert result["community_links"] == [
            {"type": "discord", "url": "https://discord.gg/test", "label": "Test"}
        ]
        assert result["country"] == "FR"
        assert "name" not in result
        assert "contact_email" not in result

    def test_nc_user_visible(self):
        user = _make_user(roles=["NC"], vekn_prefix="100")
        result = compute_public(ObjectType.USER, user)
        assert result is not None
        assert result["uid"] == "u-001"
        assert result["name"] == "Alice"
        assert result["country"] == "FR"
        assert result["roles"] == ["NC"]
        assert result["vekn_prefix"] == "100"
        # Email/phone are base64-cloaked in the public projection (decoded client-side)
        # so the plaintext never appears in the public snapshot; Discord isn't cloaked.
        assert result["contact_email"].startswith("#b64#")
        assert "alice@example.com" not in result["contact_email"]
        assert (
            base64.b64decode(result["contact_email"][len("#b64#") :]).decode()
            == "alice@example.com"
        )
        assert result["contact_phone"].startswith("#b64#")
        assert "@" not in str(result)
        assert result["contact_discord"] == "alice#1234"

    def test_prince_user_visible(self):
        user = _make_user(roles=["Prince"])
        result = compute_public(ObjectType.USER, user)
        assert result is not None
        assert result["roles"] == ["Prince"]

    def test_public_excludes_member_fields(self):
        user = _make_user(roles=["NC"])
        result = compute_public(ObjectType.USER, user)
        assert result is not None
        assert "vekn_id" not in result
        assert "city" not in result
        assert "nickname" not in result
        assert "avatar_path" not in result
        assert "constructed_online" not in result
        assert "wins" not in result
        assert "calendar_token" not in result

    def test_nc_includes_community_links(self):
        user = _make_user(roles=["NC"])
        result = compute_public(ObjectType.USER, user)
        assert result is not None
        assert result["community_links"] == [
            {"type": "discord", "url": "https://discord.gg/test", "label": "Test"}
        ]

    def test_ic_user_visible_with_community_links_only(self):
        user = _make_user(roles=["IC"])
        result = compute_public(ObjectType.USER, user)
        assert result is not None
        assert result["roles"] == ["IC"]
        assert result["community_links"] == [
            {"type": "discord", "url": "https://discord.gg/test", "label": "Test"}
        ]
        assert "contact_email" not in result
        assert "contact_discord" not in result
        assert "contact_phone" not in result

    def test_deleted_user_preserves_deleted_at(self):
        user = _make_user(roles=["NC"], deleted_at="2026-02-01T00:00:00")
        result = compute_public(ObjectType.USER, user)
        assert result is not None
        assert result["deleted_at"] == "2026-02-01T00:00:00"


class TestUserMember:
    def test_all_users_visible(self):
        user = _make_user(roles=[])
        result = compute_member(ObjectType.USER, user)
        assert result is not None
        assert result["uid"] == "u-001"

    def test_includes_identity_fields(self):
        user = _make_user()
        result = compute_member(ObjectType.USER, user)
        assert result is not None
        assert result["name"] == "Alice"
        assert result["country"] == "FR"
        assert result["vekn_id"] == "1000001"
        assert result["city"] == "Paris"
        assert result["nickname"] == "alice_v"
        assert result["avatar_path"] == "/avatars/alice.webp"

    def test_includes_rating_fields(self):
        user = _make_user()
        result = compute_member(ObjectType.USER, user)
        assert result is not None
        assert result["constructed_online"] == {"total": 100, "tournaments": []}
        assert result["wins"] == ["t-001"]

    def test_excludes_contact_for_regular_users(self):
        user = _make_user(roles=[], community_links=[])
        result = compute_member(ObjectType.USER, user)
        assert result is not None
        assert "contact_email" not in result
        assert "contact_discord" not in result
        assert "contact_phone" not in result
        assert "community_links" not in result

    def test_includes_community_links_for_regular_users_who_have_them(self):
        user = _make_user(roles=[])
        result = compute_member(ObjectType.USER, user)
        assert result is not None
        assert result["community_links"] == [
            {"type": "discord", "url": "https://discord.gg/test", "label": "Test"}
        ]
        assert "contact_email" not in result

    def test_nc_includes_contact_and_community_links(self):
        user = _make_user(roles=["NC"])
        result = compute_member(ObjectType.USER, user)
        assert result is not None
        assert result["contact_email"] == "alice@example.com"
        assert result["contact_discord"] == "alice#1234"
        assert result["contact_phone"] == "+33612345678"
        assert result["community_links"] == [
            {"type": "discord", "url": "https://discord.gg/test", "label": "Test"}
        ]

    def test_prince_includes_contact_and_community_links(self):
        user = _make_user(roles=["Prince"])
        result = compute_member(ObjectType.USER, user)
        assert result is not None
        assert result["contact_email"] == "alice@example.com"
        assert result["community_links"] == [
            {"type": "discord", "url": "https://discord.gg/test", "label": "Test"}
        ]

    def test_ic_includes_community_links_no_contact(self):
        user = _make_user(roles=["IC"])
        result = compute_member(ObjectType.USER, user)
        assert result is not None
        assert result["community_links"] == [
            {"type": "discord", "url": "https://discord.gg/test", "label": "Test"}
        ]
        assert "contact_email" not in result
        assert "contact_discord" not in result
        assert "contact_phone" not in result

    def test_excludes_internal_fields(self):
        user = _make_user()
        result = compute_member(ObjectType.USER, user)
        assert result is not None
        assert "coopted_by" not in result
        assert "coopted_at" not in result
        assert "vekn_synced" not in result
        assert "local_modifications" not in result
        assert "calendar_token" not in result


class TestUserFull:
    def test_includes_everything_except_calendar_token(self):
        user = _make_user()
        result = compute_full(ObjectType.USER, user)
        assert result["contact_email"] == "alice@example.com"
        assert result["coopted_by"] == "u-prince"
        assert "calendar_token" not in result

    def test_calendar_token_stripped(self):
        user = _make_user(calendar_token="secret123")
        result = compute_full(ObjectType.USER, user)
        assert "calendar_token" not in result


class TestUserDeceasedPrivacyBoundary:
    """deceased_at is member-visible; deceased_by_uid (admin attribution) is full-only.
    Asserted on a no-role user so neither field rides in on a role-specific field set.
    """

    def test_member_sees_date_not_actor(self):
        user = _make_user(roles=[], community_links=[])
        result = compute_member(ObjectType.USER, user)
        assert result["deceased_at"] == "2026-05-01T00:00:00"
        assert "deceased_by_uid" not in result

    def test_full_sees_both(self):
        user = _make_user(roles=[], community_links=[])
        result = compute_full(ObjectType.USER, user)
        assert result["deceased_at"] == "2026-05-01T00:00:00"
        assert result["deceased_by_uid"] == "u-nc-fr"


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
    }
    base.update(overrides)
    return base


class TestTournamentPublic:
    def test_minimal_fields_only(self):
        t = _make_tournament()
        result = compute_public(ObjectType.TOURNAMENT, t)
        assert result is not None
        assert result["uid"] == "t-001"
        assert result["name"] == "Paris Open"
        assert result["state"] == "Playing"
        assert result["country"] == "FR"

    def test_excludes_sensitive_fields(self):
        t = _make_tournament()
        result = compute_public(ObjectType.TOURNAMENT, t)
        assert result is not None
        assert "organizers_uids" not in result
        assert "checkin_code" not in result
        assert "players" not in result
        assert "rounds" not in result
        assert "decks" not in result
        assert "vekn_pushed_at" not in result

    def test_includes_attend_decision_fields(self):
        # Booleans are always present: omitting one would make the UI assert its
        # negative rather than withhold it.
        t = _make_tournament(proxies=True, multideck=True, decklist_required=True)
        result = compute_public(ObjectType.TOURNAMENT, t)
        assert result is not None
        assert result["proxies"] is True
        assert result["multideck"] is True
        assert result["decklist_required"] is True
        assert result["venue"] == t["venue"]
        assert result["address"] == t["address"]
        assert result["description"] == t["description"]

    def test_online_event_withholds_venue_url(self):
        # On an online event venue_url is the join link, not a venue website.
        offline = compute_public(ObjectType.TOURNAMENT, _make_tournament(online=False))
        online = compute_public(
            ObjectType.TOURNAMENT,
            _make_tournament(online=True, venue_url="https://discord.gg/private"),
        )
        assert offline is not None and online is not None
        assert offline["venue_url"] == "https://example.com"
        assert "venue_url" not in online
        assert online["venue"] == "Le Dernier Bar"


class TestTournamentMember:
    def test_includes_most_fields(self):
        t = _make_tournament()
        result = compute_member(ObjectType.TOURNAMENT, t)
        assert result is not None
        assert result["organizers_uids"] == ["u-org1"]
        assert result["description"] == "A fun tournament"
        assert result["players"] == []
        assert result["external_ids"] == {"vekn": "12345"}

    def test_excludes_checkin_code(self):
        t = _make_tournament(checkin_code="secret123")
        result = compute_member(ObjectType.TOURNAMENT, t)
        assert result is not None
        assert "checkin_code" not in result

    def test_excludes_vekn_pushed_at(self):
        t = _make_tournament(vekn_pushed_at="2026-02-01T00:00:00")
        result = compute_member(ObjectType.TOURNAMENT, t)
        assert result is not None
        assert "vekn_pushed_at" not in result


class TestTournamentFull:
    def test_includes_everything(self):
        t = _make_tournament()
        result = compute_full(ObjectType.TOURNAMENT, t)
        assert result["checkin_code"] == "secret_checkin"
        assert result["vekn_pushed_at"] == "2026-02-01T00:00:00"
        assert result["organizers_uids"] == ["u-org1"]


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
        s = _make_sanction()
        assert compute_public(ObjectType.SANCTION, s) is None

    def test_member_sees_full(self):
        s = _make_sanction()
        result = compute_member(ObjectType.SANCTION, s)
        assert result is not None
        assert result["uid"] == "s-001"
        assert result["level"] == "warning"
        assert result["description"] == "Minor rules violation"

    def test_full_same_as_member(self):
        s = _make_sanction()
        assert compute_member(ObjectType.SANCTION, s) == compute_full(
            ObjectType.SANCTION, s
        )


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
        d = _make_deck()
        assert compute_public(ObjectType.DECK, d) is None

    def test_member_hidden_when_not_public(self):
        d = _make_deck()
        assert compute_member(ObjectType.DECK, d) is None

    def test_member_visible_when_public(self):
        d = _make_deck(public=True)
        result = compute_member(ObjectType.DECK, d)
        assert result is not None
        assert result["uid"] == "d-001"
        assert result["name"] == "Ventrue Lawfirm"
        assert result["public"] is True

    def test_member_hidden_when_public_false(self):
        d = _make_deck(public=False)
        assert compute_member(ObjectType.DECK, d) is None

    def test_full_visible(self):
        d = _make_deck()
        result = compute_full(ObjectType.DECK, d)
        assert result["uid"] == "d-001"
        assert result["name"] == "Ventrue Lawfirm"
        assert result["cards"] == {"100001": 4, "100002": 2}


def _make_league(**overrides) -> dict:
    base = {
        "uid": "l-001",
        "modified": "2026-01-01T00:00:00",
        "deleted_at": None,
        "name": "French National League",
        "kind": "League",
        "standings_mode": "RTP",
        "format": "Standard",
        "country": "FR",
        "start": "2026-01-01T00:00:00",
        "finish": "2026-12-31T23:59:59",
        "description": "Year-long league",
        "organizers_uids": ["u-nc-fr"],
        "parent_uid": None,
    }
    base.update(overrides)
    return base


class TestLeague:
    def test_public_omits_organizers(self):
        # Members have no public projection, so the uids would not resolve.
        lg = _make_league()
        result = compute_public(ObjectType.LEAGUE, lg)
        assert result is not None
        assert result["name"] == "French National League"
        assert result["description"] == "Year-long league"
        assert "organizers_uids" not in result

    def test_member_and_full_identical(self):
        lg = _make_league()
        mem = compute_member(ObjectType.LEAGUE, lg)
        full = compute_full(ObjectType.LEAGUE, lg)
        assert mem == full
        assert mem["organizers_uids"] == ["u-nc-fr"]


class TestUserApi:
    def test_hidden_without_a_vekn_id(self):
        assert compute_api(ObjectType.USER, _make_user(vekn_id=None)) is None
        assert compute_api(ObjectType.USER, _make_user(vekn_id="")) is None

    def test_vekn_id_and_ratings_only(self):
        result = compute_api(ObjectType.USER, _make_user())
        assert result["vekn_id"] == "1000001"
        assert result["country"] == "FR"
        assert result["wins"] == ["t-001"]
        assert result["constructed_online"] == {"total": 100, "tournaments": []}
        assert result["community_links"][0]["type"] == "discord"
        assert set(result) <= _USER_API_FIELDS

    def test_officials_keep_no_contact(self):
        result = compute_api(ObjectType.USER, _make_user(roles=["NC"]))
        assert result["roles"] == ["NC"]
        assert "contact_email" not in result
        assert "name" not in result


class TestTournamentApi:
    def test_strips_the_member_secrets_and_the_api_four(self):
        t = _make_tournament(
            announcements=[{"text": "hi"}],
            promos_distributed=[{"promo_uid": "p-1", "qty": 2}],
            promo_stock_source_uid="u-org1",
        )
        result = compute_api(ObjectType.TOURNAMENT, t)
        assert result["name"] == "Paris Open"
        assert result["external_ids"] == {"vekn": "12345"}
        assert result["organizers_uids"] == ["u-org1"]
        assert not (set(result) & _TOURNAMENT_API_EXCLUDE)

    def test_player_names_and_payment_stripped(self):
        t = _make_tournament(
            players=[
                {
                    "user_uid": "u-001",
                    "state": "Registered",
                    "payment_status": "Paid",
                    "toss": 0,
                    "result": {"gw": 1, "vp": 3.0, "tp": 60},
                    "finalist": True,
                    "display_name": "Alice",
                    "non_competing": False,
                }
            ]
        )
        result = compute_api(ObjectType.TOURNAMENT, t)
        player = result["players"][0]
        assert player["user_uid"] == "u-001"
        assert player["finalist"] is True
        assert player["result"] == {"gw": 1, "vp": 3.0, "tp": 60}
        assert "display_name" not in player
        assert "payment_status" not in player

    def test_full_projection_keeps_the_player_fields_api_drops(self):
        t = _make_tournament(players=[{"user_uid": "u-001", "display_name": "Alice"}])
        compute_api(ObjectType.TOURNAMENT, t)
        assert (
            compute_full(ObjectType.TOURNAMENT, t)["players"][0]["display_name"]
            == "Alice"
        )


class TestDeckLeagueSanctionPromoApi:
    def test_public_deck_loses_its_author(self):
        result = compute_api(ObjectType.DECK, _make_deck(public=True))
        assert result["cards"] == {"100001": 4, "100002": 2}
        assert result["attribution"] == "1000001"
        assert "author" not in result

    def test_private_deck_hidden(self):
        assert compute_api(ObjectType.DECK, _make_deck(public=False)) is None

    def test_league_keeps_its_organizers(self):
        result = compute_api(ObjectType.LEAGUE, _make_league())
        assert result["name"] == "French National League"
        assert result["organizers_uids"] == ["u-nc-fr"]

    def test_sanctions_and_promos_never_surface(self):
        assert compute_api(ObjectType.SANCTION, _make_sanction()) is None
        assert compute_api(ObjectType.PROMO, {"uid": "p-1", "name": "Promo"}) is None


class TestApiCarriesNoSyncBookkeeping:
    def test_no_type_carries_them(self):
        payloads = [
            compute_api(ObjectType.USER, _make_user()),
            compute_api(ObjectType.TOURNAMENT, _make_tournament()),
            compute_api(ObjectType.DECK, _make_deck(public=True)),
            compute_api(ObjectType.LEAGUE, _make_league()),
        ]
        for payload in payloads:
            assert not (set(payload) & _API_SYNC_FIELDS)
        assert all("uid" in payload for payload in payloads)


class TestDispatch:
    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown object type"):
            compute_public("foobar", {})
        with pytest.raises(ValueError, match="Unknown object type"):
            compute_member("foobar", {})
        with pytest.raises(ValueError, match="Unknown object type"):
            compute_full("foobar", {})
        with pytest.raises(ValueError, match="Unknown object type"):
            compute_api("foobar", {})


# The member-visible half of the tournament projection, which the code expresses
# only as the denylist's complement.
_TOURNAMENT_MEMBER_VISIBLE = {
    "uid",
    "modified",
    "deleted_at",
    "name",
    "format",
    "rank",
    "online",
    "start",
    "finish",
    "timezone",
    "country",
    "league_uid",
    "state",
    "organizers_uids",
    "venue",
    "venue_url",
    "address",
    "map_url",
    "proxies",
    "multideck",
    "decklist_required",
    "description",
    "standings_mode",
    "decklists_mode",
    "max_rounds",
    "max_players",
    "open_rounds",
    "self_organized_rounds",
    "table_rooms",
    "round_time",
    "finals_time",
    "banner_path",
    "external_ids",
    "event_code",
    "players",
    "rounds",
    "finals",
    "winner",
    "standings",
    "reported_player_count",
    "raffles",
    "promos_distributed",
    "promo_stock_source_uid",
    "offline_mode",
    "offline_device_id",
    "offline_user_uid",
    "offline_since",
    "timer",
    "table_extra_time",
    "announcements",
}


# The api-visible half of the tournament projection, the same complement the
# member classification carries: the code states only the denylist.
_TOURNAMENT_API_VISIBLE = _TOURNAMENT_MEMBER_VISIBLE - {
    "modified",
    "deleted_at",
    "announcements",
    "raffles",
    "promos_distributed",
    "promo_stock_source_uid",
    "offline_device_id",
}

# User api is an allowlist, so its complement is what the public API withholds.
_USER_API_WITHHELD = {
    "modified",
    "deleted_at",
    "name",
    "nickname",
    "city",
    "city_geoname_id",
    "state",
    "avatar_path",
    "promo_stock",
    "contact_email",
    "contact_discord",
    "discord_id",
    "contact_phone",
    "phone_is_whatsapp",
    "github_login",
    "github_id",
    "coopted_by",
    "coopted_at",
    "deceased_at",
    "deceased_by_uid",
    "vekn_synced",
    "vekn_synced_at",
    "local_modifications",
    "vekn_prefix",
    "calendar_token",
}

_PLAYER_API_VISIBLE = {
    "user_uid",
    "state",
    "toss",
    "result",
    "finalist",
    "non_competing",
}


class TestProjectionCompleteness:
    def test_every_tournament_field_is_member_classified(self):
        assert not (_TOURNAMENT_MEMBER_VISIBLE & _TOURNAMENT_MEMBER_EXCLUDE)
        assert _TOURNAMENT_MEMBER_VISIBLE | _TOURNAMENT_MEMBER_EXCLUDE == {
            f.name for f in msgspec.structs.fields(Tournament)
        }

    def test_every_tournament_field_is_api_classified(self):
        assert not (_TOURNAMENT_API_VISIBLE & _TOURNAMENT_API_EXCLUDE)
        assert _TOURNAMENT_API_VISIBLE | _TOURNAMENT_API_EXCLUDE == {
            f.name for f in msgspec.structs.fields(Tournament)
        }

    def test_every_user_field_is_api_classified(self):
        assert not (_USER_API_FIELDS & _USER_API_WITHHELD)
        assert _USER_API_FIELDS | _USER_API_WITHHELD == {
            f.name for f in msgspec.structs.fields(User)
        }

    def test_every_player_field_is_api_classified(self):
        assert not (_PLAYER_API_VISIBLE & _PLAYER_API_EXCLUDE)
        assert _PLAYER_API_VISIBLE | _PLAYER_API_EXCLUDE == {
            f.name for f in msgspec.structs.fields(Player)
        }

    def test_user_full_withholds_only_calendar_token(self):
        every = {f.name: None for f in msgspec.structs.fields(User)}
        result = compute_full(ObjectType.USER, every)
        assert set(every) - set(result) == {"calendar_token"}
