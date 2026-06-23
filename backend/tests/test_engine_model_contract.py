"""Regression guard: every table state the Rust engine emits must decode into
the Python ``Tournament`` model.

The action route builds the model straight from the engine's output with a strict
``msgspec.convert(t_data, Tournament)`` (``routes/tournaments.py``). If the engine
starts emitting a ``TableState`` the Python ``models.TableState`` enum doesn't
list, that convert raises ``ValidationError`` -> the action 500s for *every*
tournament once any table reaches that state. This is not hypothetical: the
self-organized-rounds feature introduced the ``Cancelled`` table state, which had
to be mirrored into ``models.py`` for soft-cancel to convert instead of 500.

This drives a real ``CancelRound`` soft-cancel through the shipped PyO3 engine and
runs the route's exact convert, so engine/model drift fails here instead of in
production. No DB, no mock — real engine binding + real model.
"""

import json

import msgspec
from archon_engine import PyEngine
from src.models import Table, TableState, Tournament


def _soft_cancel_result() -> dict:
    """Run a real ``CancelRound`` on the engine that soft-cancels a non-last
    round, returning the engine's tournament dict (the shape the route converts).

    Two parallel rounds: round 0 finished (its pod capped at max_rounds=1),
    round 1 still in progress. Cancelling round 0 must soft-cancel it (state
    ``Cancelled``, slot preserved) rather than hard-remove. VP vectors are
    engine-valid finished tables (ceil-sum == table size, single oust).
    """
    tournament = {
        "uid": "contract-test",
        "modified": "2025-01-01T00:00:00Z",
        "name": "Contract Test",
        "state": "Playing",
        "format": "Standard",
        "rank": "",
        "online": True,
        "max_rounds": 1,
        "organizers_uids": ["organizer-1"],
        "players": [
            {"user_uid": u, "state": s, "payment_status": "Pending", "toss": 0}
            for u, s in [
                ("p1", "Completed"),
                ("p2", "Completed"),
                ("p3", "Completed"),
                ("p4", "Completed"),
                ("q1", "Playing"),
                ("q2", "Playing"),
                ("q3", "Playing"),
                ("q4", "Playing"),
            ]
        ],
        "rounds": [
            [
                {
                    "seating": [
                        {"player_uid": "p1", "result": {"gw": 1, "vp": 2.0, "tp": 0}},
                        {"player_uid": "p2", "result": {"gw": 0, "vp": 1.0, "tp": 0}},
                        {"player_uid": "p3", "result": {"gw": 0, "vp": 1.0, "tp": 0}},
                        {"player_uid": "p4", "result": {"gw": 0, "vp": 0.0, "tp": 0}},
                    ],
                    "state": "Finished",
                }
            ],
            [
                {
                    "seating": [
                        {"player_uid": "q1", "result": {"gw": 0, "vp": 0.0, "tp": 0}},
                        {"player_uid": "q2", "result": {"gw": 0, "vp": 0.0, "tp": 0}},
                        {"player_uid": "q3", "result": {"gw": 0, "vp": 0.0, "tp": 0}},
                        {"player_uid": "q4", "result": {"gw": 0, "vp": 0.0, "tp": 0}},
                    ],
                    "state": "In Progress",
                }
            ],
        ],
    }
    actor = {"uid": "organizer-1", "roles": ["Prince"], "is_organizer": True}
    event = {"type": "CancelRound", "round": 0}
    result_json = PyEngine().process_tournament_event(
        json.dumps(tournament), json.dumps(event), json.dumps(actor), "[]", "[]"
    )
    return json.loads(result_json)["tournament"]


def test_engine_cancelled_table_state_decodes_into_model():
    """A soft-cancelled round from the engine must convert into the Tournament
    model exactly as the action route does it."""
    t_data = _soft_cancel_result()

    # The route's strict convert — this is the line that 500s on enum drift.
    updated = msgspec.convert(t_data, Tournament)

    cancelled = updated.rounds[0][0]
    assert isinstance(cancelled, Table)
    assert cancelled.state is TableState.CANCELLED
    # The other round is untouched, and the slot was preserved (not removed).
    assert len(updated.rounds) == 2
    assert updated.rounds[1][0].state is TableState.IN_PROGRESS
