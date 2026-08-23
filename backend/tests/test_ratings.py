"""Tests for rating computation helpers."""

import msgspec
import pytest
from archon_engine import PyEngine
from src import db
from src.models import (
    DeckObject,
    ObjectType,
    Sanction,
    Tournament,
)
from src.ratings import (
    _compute_entry_sync,
    _final_positions,
    _is_disqualified,
)

_engine = PyEngine()


def _rating_vp_gw(t: Tournament, user_uid: str, sanctions: list | None = None):
    """Exercise the single-source Rust rating stat (VP/GW incl. finals + SA)."""
    return _engine.compute_rating_vp_gw(
        msgspec.json.encode(t).decode(),
        msgspec.json.encode(sanctions or []).decode(),
        user_uid,
    )


def _make_tournament(**overrides) -> Tournament:
    defaults = {
        "uid": "t-001",
        "modified": "2026-01-01T00:00:00",
        "name": "Test Tournament",
        "format": "Standard",
        "rank": "",
        "state": "Finished",
        "country": "FR",
        "rounds": [],
        "finals": None,
        "standings": [],
        "winner": "",
    }
    defaults.update(overrides)
    return msgspec.convert(defaults, Tournament)


def _seat(uid: str, vp: float = 0.0, gw: int = 0) -> dict:
    return {"player_uid": uid, "result": {"vp": vp, "gw": gw, "tp": 0}}


def _table(*uids: str, vps: list[float], gws: list[int] | None = None) -> list[dict]:
    """Seats in predator-prey order, holding a result a real table reaches. The
    caller must mark the table Finished: nothing else is scored."""
    gws = gws or [0] * len(uids)
    return [_seat(u, v, g) for u, v, g in zip(uids, vps, gws, strict=True)]


class TestRatingVpGw:
    def test_prelim_only(self):
        """Player who only played prelims gets prelim VP/GW."""
        t = _make_tournament(
            rounds=[
                [
                    {
                        "seating": _table(
                            "p1", "p2", "p3", "p4", vps=[2.0, 1.0, 1.0, 0.0]
                        ),
                        "state": "Finished",
                    }
                ],
                [
                    {
                        "seating": _table(
                            "p1", "p2", "p3", "p4", vps=[0.5, 0.5, 0.5, 0.5]
                        ),
                        "state": "Finished",
                    }
                ],
            ],
        )
        vp, gw = _rating_vp_gw(t, "p1")
        assert vp == 2.5
        assert gw == 1

    def test_finalist_includes_finals(self):
        """Finalist gets prelim + finals VP/GW combined."""
        t = _make_tournament(
            rounds=[
                [
                    {
                        "seating": _table(
                            "p1", "p2", "p3", "p4", vps=[2.0, 1.0, 1.0, 0.0]
                        ),
                        "state": "Finished",
                    }
                ],
            ],
            finals={
                "seating": _table(
                    "p1",
                    "p2",
                    "p3",
                    "p4",
                    "p5",
                    vps=[3.0, 1.0, 1.0, 0.0, 0.0],
                    gws=[1, 0, 0, 0, 0],
                ),
                "seed_order": ["p1", "p2", "p3", "p4", "p5"],
                "state": "Finished",
            },
        )
        vp, gw = _rating_vp_gw(t, "p1")
        assert vp == 5.0
        assert gw == 2

    def test_non_finalist_unaffected(self):
        """Player not in finals only gets prelim stats."""
        t = _make_tournament(
            rounds=[
                [
                    {
                        "seating": _table(
                            "p1", "p2", "p3", "p4", vps=[2.0, 1.0, 1.0, 0.0]
                        ),
                        "state": "Finished",
                    }
                ],
            ],
            finals={
                "seating": _table(
                    "p1",
                    "p2",
                    "p4",
                    "p5",
                    "p6",
                    vps=[3.0, 1.0, 1.0, 0.0, 0.0],
                    gws=[1, 0, 0, 0, 0],
                ),
                "seed_order": ["p1", "p2", "p4", "p5", "p6"],
                "state": "Finished",
            },
        )
        vp, gw = _rating_vp_gw(t, "p3")
        assert vp == 1.0
        assert gw == 0

    def test_winner_gw(self):
        """Winner's GW includes the finals GW."""
        t = _make_tournament(
            rounds=[
                [
                    {
                        "seating": _table(
                            "p2", "p1", "p3", "p4", vps=[2.0, 1.0, 1.0, 0.0]
                        ),
                        "state": "Finished",
                    }
                ],
            ],
            finals={
                "seating": _table(
                    "p1",
                    "p2",
                    "p3",
                    "p4",
                    "p5",
                    vps=[2.0, 2.0, 1.0, 0.0, 0.0],
                    gws=[1, 0, 0, 0, 0],
                ),
                "seed_order": ["p1", "p2", "p3", "p4", "p5"],
                "state": "Finished",
            },
            winner="p1",
        )
        vp, gw = _rating_vp_gw(t, "p1")
        assert vp == 3.0
        assert gw == 1  # 0 prelim + 1 finals

    def test_sa_full_penalty(self):
        """SA on a played round subtracts a full 1.0 VP (not the old overflow)."""
        t = _make_tournament(
            rounds=[
                [
                    {
                        "seating": _table(
                            "p1", "p2", "p3", "p4", vps=[2.0, 0.0, 0.0, 2.0]
                        ),
                        "state": "Finished",
                    }
                ],
            ],
        )
        sanctions = [
            {
                "user_uid": "p1",
                "level": "standings_adjustment",
                "round_number": 0,
                "lifted_at": None,
                "deleted_at": None,
            }
        ]
        vp, gw = _rating_vp_gw(t, "p1", sanctions)
        assert vp == 1.0  # raw 2.0 - full 1.0 (old overflow would have been 0)

    def test_sa_goes_negative(self):
        """SA penalty can push the rating VP below zero."""
        t = _make_tournament(
            rounds=[
                [
                    {
                        "seating": _table(
                            "p1", "p2", "p3", "p4", vps=[0.0, 2.0, 1.0, 1.0]
                        ),
                        "state": "Finished",
                    }
                ],
            ],
        )
        sanctions = [
            {
                "user_uid": "p1",
                "level": "standings_adjustment",
                "round_number": 0,
                "lifted_at": None,
                "deleted_at": None,
            }
        ]
        vp, _ = _rating_vp_gw(t, "p1", sanctions)
        assert vp == -1.0

    def test_vekn_synced_fallback(self):
        """No rounds/finals: falls back to standings."""
        t = _make_tournament(
            standings=[
                {"user_uid": "p1", "vp": 7.5, "gw": 3.0, "tp": 36},
                {"user_uid": "p2", "vp": 4.0, "gw": 1.0, "tp": 24},
            ],
        )
        vp, gw = _rating_vp_gw(t, "p1")
        assert vp == 7.5
        assert gw == 3

    def test_vekn_synced_missing_player(self):
        """Standings fallback returns 0 for unknown player."""
        t = _make_tournament(
            standings=[{"user_uid": "p1", "vp": 5.0, "gw": 2.0, "tp": 24}],
        )
        vp, gw = _rating_vp_gw(t, "unknown")
        assert vp == 0.0
        assert gw == 0

    def test_finals_only_no_rounds(self):
        """Edge case: finals data but no rounds (guard: rounds or finals)."""
        t = _make_tournament(
            finals={
                "seating": [_seat("p1", 4.0, 1), _seat("p2", 1.0, 0)],
                "seed_order": ["p1", "p2"],
            },
        )
        vp, gw = _rating_vp_gw(t, "p1")
        assert vp == 4.0
        assert gw == 1


def _sanction(user_uid: str, **overrides) -> Sanction:
    d = {
        "uid": "s-001",
        "modified": "2026-01-01T00:00:00",
        "user_uid": user_uid,
        "issued_by_uid": "judge",
        "level": "disqualification",
        "category": "unsportsmanlike_conduct",
        "description": "",
        "issued_at": "2026-01-01T00:00:00",
    }
    d.update(overrides)
    return msgspec.convert(d, Sanction)


def test_ranking_eligibility_gate():
    """Rules 3.1/3.1.6: >=8 players AND a played final for international ranking;
    house formats never qualify. This PyO3 predicate gates ratings.py inclusion
    and the frontend badge."""

    def verdict(t: Tournament) -> str:
        return _engine.ranking_eligibility(msgspec.json.encode(t).decode())

    finals = {
        "seating": [
            _seat("p0", 3.0, 1),
            _seat("p1"),
            _seat("p2"),
            _seat("p3"),
            _seat("p4"),
        ],
        "seed_order": ["p0", "p1", "p2", "p3", "p4"],
    }
    eligible = _make_tournament(
        rounds=[
            [
                {"seating": [_seat(f"p{i}") for i in range(4)]},
                {"seating": [_seat(f"p{i}") for i in range(4, 8)]},
            ]
        ],
        finals=finals,
        winner="p0",
    )
    assert verdict(eligible) == "eligible"

    seven = _make_tournament(
        rounds=[
            [
                {"seating": [_seat(f"p{i}") for i in range(4)]},
                {"seating": [_seat(f"p{i}") for i in range(4, 7)]},
            ]
        ],
        finals=finals,
        winner="p0",
    )
    assert verdict(seven) == "few_players"

    no_final = _make_tournament(
        rounds=[
            [
                {"seating": [_seat(f"p{i}") for i in range(4)]},
                {"seating": [_seat(f"p{i}") for i in range(4, 8)]},
            ]
        ],
    )
    assert verdict(no_final) == "no_final"

    house = msgspec.structs.replace(eligible, open_rounds=True)
    assert verdict(house) == "open_rounds"

    # VEKN import: rounds-less, standings carry the field, winner but no finals
    # object — stays eligible (the reconstructed-history convention).
    imported = _make_tournament(
        standings=[
            {
                "user_uid": f"p{i}",
                "gw": 0,
                "vp": 1.5,
                "tp": 24,
                "toss": 0,
                "rank": i + 1,
            }
            for i in range(9)
        ],
        winner="p0",
    )
    assert verdict(imported) == "eligible"


def test_dq_player_earns_no_rating_entry_co_player_unaffected_count_inclusive():
    """DQ'd players earn NO rating points, not even the 5-pt participation base
    (spec #284) — the engine zeroes VP/GW, but `_is_disqualified` must block the
    entry entirely."""
    t = _make_tournament(
        players=[
            {"user_uid": "dq_state", "state": "Disqualified"},
            {"user_uid": "dq_sanction", "state": "Finished"},
            {"user_uid": "clean", "state": "Finished"},
            {"user_uid": "bystander", "state": "Finished"},
        ],
        rounds=[
            [
                {
                    "seating": _table(
                        "clean",
                        "dq_state",
                        "dq_sanction",
                        "bystander",
                        vps=[2.0, 1.0, 1.0, 0.0],
                        gws=[1, 0, 0, 0],
                    ),
                    "state": "Finished",
                }
            ],
        ],
    )
    sanctions = [_sanction("dq_sanction")]

    # Both DQ signals trip the guard; the clean co-player does not.
    assert _is_disqualified(t, sanctions, "dq_state")
    assert _is_disqualified(t, sanctions, "dq_sanction")
    assert not _is_disqualified(t, sanctions, "clean")

    dq_entry = _compute_entry_sync(t, "dq_state", sanctions)
    assert (dq_entry.vp, dq_entry.gw) == (0.0, 0)
    assert dq_entry.points == 5

    clean_entry = _compute_entry_sync(t, "clean", sanctions)
    assert clean_entry.vp == 2.0 and clean_entry.gw == 1

    # Head-count stays inclusive of DQ'd players (finalist-coefficient base).
    assert _engine.attested_player_count(msgspec.json.encode(t).decode()) == 4


def test_final_positions_excludes_dq_and_proxy_rows():
    """DQ'd/proxy players must be absent from the placement map (absent →
    position 0 → no placement rendered). Standings flags here can outlive the
    sanction, so a stale flag could otherwise place them behind the whole field.
    """
    t = _make_tournament(
        winner="w",
        standings=[
            {"user_uid": "w", "gw": 1.0, "vp": 5.0, "tp": 60, "finalist": True},
            {"user_uid": "f", "gw": 0.0, "vp": 3.0, "tp": 50, "finalist": True},
            {"user_uid": "p", "gw": 0.0, "vp": 2.0, "tp": 40},
            {"user_uid": "dq", "gw": 0.0, "vp": 0.0, "tp": 0, "disqualified": True},
            {
                "user_uid": "proxy",
                "gw": 0.0,
                "vp": 1.0,
                "tp": 10,
                "non_competing": True,
            },
        ],
    )
    assert _final_positions(t) == {"w": (1, 1), "f": (2, 2), "p": (3, 0)}


def _standings(n: int) -> list[dict]:
    """A rounds-less result sheet of n players — the VEKN-import shape, which is
    what `attested_player_count` falls back to counting."""
    return [{"user_uid": f"p{i}"} for i in range(n)]


@pytest.mark.asyncio
async def test_hall_of_fame_win_rule(test_db):
    """Every clause of the Hall of Fame rule, which is deliberately NOT
    `ranking_eligibility`: a win counts when it would have made the TWDA and the
    winner's deck is on record."""
    cases = [
        ("w-irl", {"standings": _standings(10)}, True, True),
        ("w-online", {"standings": _standings(10), "online": True}, True, False),
        ("w-open", {"standings": _standings(10), "open_rounds": True}, True, False),
        (
            "w-self",
            {"standings": _standings(10), "self_organized_rounds": True},
            True,
            False,
        ),
        ("w-running", {"standings": _standings(10), "state": "Playing"}, True, False),
        # Draft and sealed decks are not archived, so they cannot be on record.
        ("w-limited", {"standings": _standings(10), "format": "Limited"}, True, False),
        ("w-small", {"standings": _standings(9)}, True, False),
        # The whole point of the rule: won, but never submitted the deck.
        ("w-no-deck", {"standings": _standings(10)}, False, False),
        # An archive entry that never carried `players_count` grandfathers past
        # the floor — its acceptance upstream is the attestation.
        (
            "w-archival",
            {"standings": _standings(1), "external_ids": {"twda": "1998xyz"}},
            True,
            True,
        ),
        # ...but only where the row played nothing. A result sheet of our own
        # answers the question, so the archive's silence cannot override it.
        (
            "w-archival-scored",
            {
                "standings": [{"user_uid": f"p{i}", "vp": 1.0} for i in range(5)],
                "external_ids": {"twda": "1999abc"},
            },
            True,
            False,
        ),
    ]
    for uid, overrides, has_deck, _ in cases:
        t = _make_tournament(uid=uid, winner="champ", **overrides)
        await db.save_object_from_model(ObjectType.TOURNAMENT, t)
        if has_deck:
            await db.save_object_from_model(
                ObjectType.DECK,
                msgspec.convert(
                    {
                        "uid": f"d-{uid}",
                        "modified": "2026-01-01T00:00:00",
                        "tournament_uid": uid,
                        "user_uid": "champ",
                    },
                    DeckObject,
                ),
            )

    expected = {uid for uid, _, _, counts in cases if counts}
    assert set((await db.get_all_tournament_wins()).get("champ", [])) == expected
    # The winner filter narrows the rewrite, never the rule.
    assert (
        set((await db.get_all_tournament_wins({"champ"})).get("champ", [])) == expected
    )
    assert await db.get_all_tournament_wins({"nobody"}) == {}
