"""Tests for VEKN tournament import → vekn_pushed_at stamping.

Imported VEKN-origin results must never be re-uploaded by batch_push: the
importer folds finals into `standings` (the "standings are prelim-only"
contract is violated on purpose for imports), so archondata — which assumes
prelim-only — would send wrong numbers on a re-push. The guard is two-sided:
the importer stamps `vekn_pushed_at` on finished imports (here), and batch_push
also requires `rounds` non-empty (see test_vekn_push_batch.py). Either alone
keeps imports out of the push set; both together is belt-and-suspenders.

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


def test_planned_import_leaves_vekn_pushed_at_null():
    # Blanket-stamping would be harmful the other way: a planned import later
    # run in-app would keep the stamp and never get its real results pushed.
    t = _map_vekn_to_tournament(_planned_event(), {})
    assert t is not None
    assert t.vekn_pushed_at is None
