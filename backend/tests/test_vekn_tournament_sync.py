"""Tests for VEKN tournament import → prelim-only standings + finals + push guard.

The import honors the project contract: `standings` are **preliminary-only**, a
final lives in a reconstructed `finals` object, and rating/league scoring add it
on top. Imported VEKN-origin results must also never be re-uploaded by batch_push:
the importer stamps `vekn_pushed_at` on finished imports (here), and batch_push
also requires `rounds` non-empty (see test_vekn_push_batch.py). Either alone keeps
imports out of the push set; both together is belt-and-suspenders.

`_map_vekn_to_tournament` is a pure function — no DB, no mocks.
"""

from datetime import UTC, datetime

from src.models import User
from src.vekn_tournament_sync import _map_vekn_to_tournament


def _user(uid: str, vekn_id: str) -> User:
    return User(
        uid=uid,
        modified=datetime(2025, 1, 1, tzinfo=UTC),
        name=f"Player {uid}",
        vekn_id=vekn_id,
    )


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
    users = {"1000001": _user("u1", "1000001")}
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
    users = {"1000001": _user("u1", "1000001")}
    t = _map_vekn_to_tournament(_finished_event(), users)
    assert t is not None and t.max_rounds == 3


def test_import_stores_naive_wall_clock_paired_with_timezone():
    # start/finish are stored NAIVE, paired with `timezone` — readers anchor them
    # in that zone (calendar._as_utc, frontend utils.zonedDate). Converting VEKN's
    # venue wall clock to UTC here made those readers shift it a second time, so a
    # 09:00 Madrid event read back as 07:00.
    event = _planned_event() | {"venue_country": "ES", "event_starttime": "09:00:00"}
    t = _map_vekn_to_tournament(event, {})
    assert t is not None
    assert t.timezone == "Europe/Madrid"
    assert t.start == datetime(2099, 3, 1, 9, 0)
    assert t.start.tzinfo is None


def test_import_carries_proxies_allowed_unless_rank_forbids_it():
    # VEKN's 'proxies_allowed' flag drives deck legality in the UI — dropping it
    # showed every import as "proxies not allowed" (over half of vekn.net events
    # allow them). Championship ranks forbid proxies (engine legality), and a few
    # vekn.net championships do carry the flag set: rank wins there, otherwise the
    # imported row can't pass validate_rank_legality on any later config edit.
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
    # The #340 contract: standings carry PRELIM-only scores (winner's +1 finals GW
    # and everyone's vpf excluded); the final lives in a reconstructed finals object
    # with the winner's +1 GW and each seat's vp = their vpf.
    users = {str(i): _user(f"u{i}", str(i)) for i in range(1, 7)}
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
    users = {"1000001": _user("u1", "1000001")}
    t = _map_vekn_to_tournament(_finished_event(), users)
    assert t is not None
    assert t.finals is None
    assert t.winner == "u1"
    winner = next(s for s in t.standings if s.user_uid == "u1")
    assert (winner.gw, winner.vp) == (1.0, 4.0)  # prelim only (gw not +1)
