"""The archival shape a TWDA reconstruction must keep. `reconstructed_tournament`
is pure — no DB, no mocks.

Each assertion below stands for something that breaks visibly if the shape drifts,
so a refactor that "tidies" one of them fails here rather than in the corpus.
"""

from datetime import UTC, datetime

import msgspec
from archon_engine import PyEngine
from src.twda_import import reconstructed_tournament

WINNER = "019f1a00-78c6-775b-9abe-ee9d668bd22e"


def _entry() -> dict:
    return {
        "id": "2007krakow",
        "date": "2007-03-17",
        "event": "Polish National Championship",
        "place": "Kraków, Poland",
        "player": "Marcin Watras",
        "players_count": 42,
        "tournament_format": "3R+F",
    }


def test_reconstruction_shape():
    t = reconstructed_tournament(_entry(), WINNER, datetime.now(UTC))

    # The winner MUST have a Player row. Without it the tournament page renders
    # the winner as a raw uid, the organizer roster reads empty against a
    # populated member view, and the post-finish wins refresh never fires.
    assert [p.user_uid for p in t.players] == [WINNER]
    assert t.winner == WINNER
    assert [s.user_uid for s in t.standings] == [WINNER]

    # Scores stay zero: the archive's is a total including the final, while
    # standings are prelim-only by contract. The size comes from the count.
    assert (t.standings[0].gw, t.standings[0].vp, t.standings[0].tp) == (0.0, 0.0, 0)
    assert t.reported_player_count == 42

    # Never vekn_pushed_at — it would mean results were exchanged with vekn.net,
    # and it trips the delete guard, permanently blocking cleanup of a bad row.
    assert t.vekn_pushed_at is None
    assert t.external_ids == {"twda": "2007krakow"}
    # A one-row standings in a league would earn league points off a zero field.
    assert t.league_uid is None

    assert t.country == "PL"
    assert t.timezone == "Europe/Warsaw"
    assert t.max_rounds == 3
    assert t.start == datetime(2007, 3, 17)


def test_reconstruction_never_rates():
    """The zeros are harmless only because `no_results` blocks the row. If the
    eligibility gate ever lets this through, its winner enters the international
    ranking with vp=0/gw=0 and the row badges as Ranked."""
    t = reconstructed_tournament(_entry(), WINNER, datetime.now(UTC))
    engine = PyEngine()
    t_json = msgspec.json.encode(t).decode()
    assert engine.ranking_eligibility(t_json) == "no_results"
    # ...while still reporting the size the archive attested, for the win floor.
    assert engine.attested_player_count(t_json) == 42
