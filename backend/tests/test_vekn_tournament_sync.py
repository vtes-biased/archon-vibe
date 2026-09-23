"""VEKN tournament import: standings are preliminary-only (a final lives in a
reconstructed `finals` object); imports are excluded from batch_push both by
the `vekn_pushed_at` stamp set here and by batch_push's own rounds-non-empty
guard — belt-and-suspenders. `_map_vekn_to_tournament` is pure, no DB/mocks.
"""

from datetime import datetime

import msgspec
from src.models import PlayerState
from src.vekn_tournament_sync import _map_vekn_to_tournament, _TwdaScore


# A 2-type (Standard Constructed) finished event with one known player.
def _finished_event() -> dict:
    return {
        "event_id": "555",
        "event_name": "Imported Cup",
        "eventtype_id": "2",
        "event_startdate": "2025-03-01",
        "event_enddate": "2025-03-01",
        "venue_country": "FR",
        "rounds": "3R+F",  # VEKN's real format: leading int = preliminary rounds
        "players": [
            {"pos": "1", "veknid": "1000001", "gw": "1", "vp": "4", "tp": "36"},
        ],
    }


def _planned_event() -> dict:
    return {
        "event_id": "556",
        "event_name": "Future Cup",
        "eventtype_id": "2",
        "event_startdate": "2099-03-01",
        "venue_country": "FR",
        "players": [],  # no results yet → planned
    }


def test_finished_import_stamps_vekn_pushed_at():
    users = {"1000001": "u1"}
    t = _map_vekn_to_tournament(_finished_event(), users)
    assert t is not None
    # Finished import: standings populated FROM vekn.net but no in-app rounds.
    assert t.standings and not t.rounds
    # Must be stamped so batch_push never re-uploads it.
    assert t.vekn_pushed_at is not None


def test_import_populates_round_count():
    # VEKN's calendar 'rounds' field is the preliminary round count; the sync
    # maps it onto max_rounds (the app's "number of rounds"), not just for
    # open-rounds events.
    users = {"1000001": "u1"}
    t = _map_vekn_to_tournament(_finished_event(), users)
    assert t is not None and t.max_rounds == 3


def test_import_stores_naive_wall_clock_paired_with_timezone():
    # start/finish are stored NAIVE, paired with `timezone`; converting VEKN's
    # venue wall clock to UTC here shifted it twice (09:00 Madrid read 07:00).
    event = _planned_event() | {"venue_country": "ES", "event_starttime": "09:00:00"}
    t = _map_vekn_to_tournament(event, {})
    assert t is not None
    assert t.timezone == "Europe/Madrid"
    assert t.start == datetime(2099, 3, 1, 9, 0)
    assert t.start.tzinfo is None


def test_import_carries_proxies_allowed_unless_rank_forbids_it():
    # VEKN's 'proxies_allowed' flag drives deck legality in the UI (over half
    # of vekn.net events allow them). Championship ranks forbid proxies
    # (engine legality); a few championships do carry the flag — rank wins.
    event = _planned_event() | {"proxies_allowed": "1"}
    assert _map_vekn_to_tournament(event, {}).proxies is True

    nc = event | {"eventtype_id": "8"}  # National Championship
    assert _map_vekn_to_tournament(nc, {}).proxies is False


def test_planned_import_leaves_vekn_pushed_at_null():
    # Blanket-stamping would be harmful the other way: a planned import later
    # run in-app would keep the stamp and never get its real results pushed.
    t = _map_vekn_to_tournament(_planned_event(), {})
    assert t is not None
    assert t.vekn_pushed_at is None


# A 5-player final: winner (pos 1) took 3 prelim VP + 2 finals VP (vpf).
def _final_event() -> dict:
    return {
        "event_id": "557",
        "event_name": "Final Cup",
        "eventtype_id": "2",
        "event_startdate": "2025-03-01",
        "venue_country": "FR",
        "rounds": "3R+F",
        "players": [
            {"pos": "1", "veknid": "1", "gw": "1", "vp": "3", "vpf": "2", "tp": "36"},
            {"pos": "2", "veknid": "2", "gw": "0", "vp": "2", "vpf": "1", "tp": "30"},
            {"pos": "3", "veknid": "3", "gw": "0", "vp": "2", "vpf": "1", "tp": "28"},
            {"pos": "4", "veknid": "4", "gw": "0", "vp": "1", "vpf": "0", "tp": "20"},
            {"pos": "5", "veknid": "5", "gw": "0", "vp": "1", "vpf": "0", "tp": "18"},
            {"pos": "9", "veknid": "6", "gw": "0", "vp": "0", "vpf": "0", "tp": "10"},
        ],
    }


def test_import_standings_prelim_only_and_reconstructs_finals():
    # The #340 contract: standings carry PRELIM-only scores (winner's +1 finals
    # GW and everyone's vpf excluded); the final lives in a reconstructed
    # finals object with winner +1 GW and each seat's vp = vpf.
    users = {str(i): f"u{i}" for i in range(1, 7)}
    t = _map_vekn_to_tournament(_final_event(), users)
    assert t is not None

    winner = next(s for s in t.standings if s.user_uid == "u1")
    assert (winner.gw, winner.vp) == (1.0, 3.0)  # prelim only: no +1, no vpf

    assert t.finals is not None
    seats = {s.player_uid: s.result for s in t.finals.seating}
    assert (seats["u1"].gw, seats["u1"].vp) == (1, 2.0)  # winner GW + vpf
    assert (seats["u2"].gw, seats["u2"].vp) == (0, 1.0)
    assert "u6" not in seats  # non-finalist not seated
    assert t.winner == "u1"


def test_no_final_import_omits_finals_but_keeps_winner():
    # No final played (all vpf=0) → no finals object, but the winner is still set
    # so the engine's tournament-win GW rule credits it. Standings stay prelim-only.
    users = {"1000001": "u1"}
    t = _map_vekn_to_tournament(_finished_event(), users)
    assert t is not None
    assert t.finals is None
    assert t.winner == "u1"
    winner = next(s for s in t.standings if s.user_uid == "u1")
    assert (winner.gw, winner.vp) == (1.0, 4.0)  # prelim only (gw not +1)


def _flagged_event() -> dict:
    return {
        "event_id": "558",
        "event_name": "Flagged Cup",
        "eventtype_id": "2",
        "event_startdate": "2025-03-01",
        "venue_country": "FR",
        "rounds": "3R+F",
        "players": [
            {"pos": "1", "veknid": "1", "gw": "1", "vp": "3", "vpf": "2", "tp": "36"},
            {"pos": "2", "veknid": "2", "gw": "0", "vp": "2", "vpf": "1", "tp": "30"},
            {"pos": "5", "veknid": "3", "gw": "1", "vp": "4", "tp": "40", "dq": "1"},
            {"pos": "5", "veknid": "4", "gw": "0", "vp": "2", "tp": "25", "wd": "1"},
            {"pos": "5", "veknid": "5", "gw": "0", "vp": "1", "tp": "18"},
        ],
    }


def test_flagged_row_never_reaches_the_finalist_or_winner_test():
    users = {str(i): f"u{i}" for i in range(1, 6)}
    t = _map_vekn_to_tournament(_flagged_event(), users)
    assert t is not None

    by_uid = {s.user_uid: s for s in t.standings}
    assert by_uid["u3"].disqualified and not by_uid["u3"].finalist
    assert (by_uid["u3"].gw, by_uid["u3"].vp, by_uid["u3"].tp) == (0.0, 0.0, 0)
    assert not by_uid["u4"].finalist and not by_uid["u4"].disqualified
    assert (by_uid["u4"].gw, by_uid["u4"].vp, by_uid["u4"].tp) == (0.0, 2.0, 25)

    states = {p.user_uid: p.state for p in t.players}
    assert states["u3"] == PlayerState.DISQUALIFIED
    assert "u3" not in {s.player_uid for s in t.finals.seating}
    assert "u4" not in {s.player_uid for s in t.finals.seating}
    assert [s.user_uid for s in t.standings][-1] == "u3"


def test_legacy_sheet_takes_the_final_gw_back_out_of_the_prelim():
    users = {str(i): f"u{i}" for i in range(1, 7)}
    legacy = _final_event() | {"event_startdate": "2009-03-01", "rounds": "0R"}
    legacy["players"] = [p | {"vpf": "0"} for p in legacy["players"]]
    t = _map_vekn_to_tournament(legacy, users)
    winner = next(s for s in t.standings if s.user_uid == "u1")
    assert winner.gw == 0.0
    assert next(p for p in t.players if p.user_uid == "u1").result.gw == 1

    new_format = _final_event() | {"event_startdate": "2009-03-01", "rounds": "0R"}
    t = _map_vekn_to_tournament(new_format, users)
    assert next(s for s in t.standings if s.user_uid == "u1").gw == 1.0


def test_member_listed_twice_keeps_the_placed_row():
    users = {str(i): f"u{i}" for i in range(1, 7)}
    event = _final_event()
    event["players"].append(
        {"pos": "6", "veknid": "1", "gw": "0", "vp": "0.5", "vpf": "0", "tp": "12"}
    )
    t = _map_vekn_to_tournament(event, users)
    assert [p.user_uid for p in t.players].count("u1") == 1
    assert [s.user_uid for s in t.standings].count("u1") == 1
    assert t.winner == "u1"
    assert next(s for s in t.standings if s.user_uid == "u1").vp == 3.0


def test_gw_above_the_round_count_is_the_final_or_a_wrong_count():
    users = {str(i): f"u{i}" for i in range(1, 7)}
    event = _final_event() | {"rounds": "2R+F"}
    event["players"][0] |= {"gw": "3"}
    t = _map_vekn_to_tournament(event, users)
    assert next(s for s in t.standings if s.user_uid == "u1").gw == 2.0

    event["players"][1] |= {"gw": "3"}
    t = _map_vekn_to_tournament(event, users)
    assert next(s for s in t.standings if s.user_uid == "u1").gw == 3.0
    assert t.max_rounds == 0


def test_legacy_sheet_takes_round_count_and_final_vp_from_its_archive_entry():
    users = {str(i): f"u{i}" for i in range(1, 7)}
    legacy = _final_event() | {"event_startdate": "2009-03-01", "rounds": "0R"}
    legacy["players"] = [p | {"vpf": "0"} for p in legacy["players"]]
    legacy["players"][0] |= {"gw": "3", "vp": "9"}
    entry = _TwdaScore(id="2009x", tournament_format="3R+F", score="2GW6+3")
    t = _map_vekn_to_tournament(legacy, users, twda=entry)
    assert t.max_rounds == 3
    winner = next(s for s in t.standings if s.user_uid == "u1")
    assert (winner.gw, winner.vp) == (2.0, 6.0)
    seats = {s.player_uid: s.result for s in t.finals.seating}
    assert (seats["u1"].gw, seats["u1"].vp) == (1, 3.0)
    assert seats["u2"].vp == 0.0

    t = _map_vekn_to_tournament(
        legacy, users, twda=msgspec.structs.replace(entry, score="+3")
    )
    winner = next(s for s in t.standings if s.user_uid == "u1")
    assert (winner.gw, winner.vp) == (2.0, 6.0)
