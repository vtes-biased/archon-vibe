"""The archival shape a TWDA reconstruction must keep. `reconstructed_tournament`
is pure — no DB, no mocks.

Each assertion below stands for something that breaks visibly if the shape drifts,
so a refactor that "tidies" one of them fails here rather than in the corpus.
"""

from datetime import UTC, datetime

import msgspec
from archon_engine import PyEngine
from src.twda_import import (
    TwdaEntry,
    _flatten_twda_cards,
    _TwdaEvent,
    reconstructed_tournament,
)

WINNER = "019f1a00-78c6-775b-9abe-ee9d668bd22e"


def _entry() -> TwdaEntry:
    return TwdaEntry(
        id="2007krakow",
        event=_TwdaEvent(
            date="2007-03-17",
            name="Polish National Championship",
            place="Kraków, Poland",
            players_count=42,
            rounds=3,
        ),
    )


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


def test_decode_twda_v2_object_format():
    raw = b"""{
        "10009": {
            "id": "10009",
            "name": "Example Deck",
            "comment": "Notes",
            "cards": [
                {"id": 100866, "count": 2, "kind": "Library"},
                {"id": 200001, "count": 4, "kind": "Crypt"}
            ],
            "event": {
                "name": "Barcelona Open",
                "date": "2021-12-19",
                "online": false,
                "format": "Standard",
                "players_count": 35,
                "rounds": 3,
                "place": "Barcelona, Spain",
                "url": "https://www.vekn.net/event-calendar/event/10009"
            }
        }
    }"""
    entries = msgspec.json.decode(raw, type=dict[str, TwdaEntry])
    entry = entries["10009"]
    assert entry.comment == "Notes"
    assert _flatten_twda_cards(entry) == {"100866": 2, "200001": 4}
    t = reconstructed_tournament(entry, WINNER, datetime.now(UTC))
    assert t.name == "Barcelona Open"
    assert t.country == "ES"
    assert t.max_rounds == 3
    assert t.reported_player_count == 35
