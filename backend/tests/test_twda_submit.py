"""Tests for the TWDA submission designer credit.

When a sanctioned tournament finishes, the winner's deck is auto-submitted to
the TWDA. The generated entry must credit the deck *designer* via the deck's
`attribution` field — not blindly echo the free-text `author`. In particular,
an anonymous deck (attribution=None) must never leak a stored author name.

These tests pin the `Created by:` value handed to the engine exporter for each
attribution case. The DB/engine/network deps are mocked so no DB is needed.
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.models import (
    DeckObject,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
    User,
)
from src.routes.tournaments import _maybe_submit_twda


def _user(uid: str, name: str, vekn_id: str = "") -> User:
    return User(
        uid=uid,
        modified=datetime(2025, 1, 1, tzinfo=UTC),
        name=name,
        vekn_id=vekn_id,
    )


def _tournament(winner_uid: str) -> Tournament:
    return Tournament(
        uid="t-001",
        modified=datetime(2025, 6, 1, tzinfo=UTC),
        name="Test Tournament",
        format=TournamentFormat.Standard,
        rank=TournamentRank.NC,  # sanctioned
        state=TournamentState.FINISHED,
        start=datetime(2025, 6, 1, tzinfo=UTC),
        external_ids={"vekn": "12345"},
        winner=winner_uid,
    )


def _deck(*, author: str, attribution: str | None) -> DeckObject:
    return DeckObject(
        uid="d-001",
        modified=datetime(2025, 6, 1, tzinfo=UTC),
        tournament_uid="t-001",
        user_uid="w-001",
        name="My Deck",
        author=author,
        attribution=attribution,
        cards={"200001": 12, "100001": 10},
    )


async def _captured_credit(
    *, winner: User, deck: DeckObject, designer: User | None
) -> str:
    """Run _maybe_submit_twda with mocked deps; return the `author` (credit)
    that was serialized into the deck_json passed to engine.export_twda."""
    tournament = _tournament(winner.uid)
    engine = MagicMock()
    engine.export_twda.return_value = "TWDA TEXT"

    with (
        patch(
            "src.routes.tournaments.get_decks_for_tournament",
            AsyncMock(return_value=[deck]),
        ),
        patch(
            "src.routes.tournaments.get_user_by_uid",
            AsyncMock(return_value=winner),
        ),
        patch(
            "src.routes.tournaments.get_user_by_vekn_id",
            AsyncMock(return_value=designer),
        ),
        patch("src.routes.tournaments._load_cards_json", lambda: "{}"),
        patch("src.routes.tournaments._engine", engine),
        patch("src.twda.submit_twda_pr", AsyncMock(return_value="http://pr")),
    ):
        await _maybe_submit_twda(tournament)

    engine.export_twda.assert_called_once()
    deck_json = engine.export_twda.call_args.args[0]
    return json.loads(deck_json)["author"]


@pytest.mark.asyncio
async def test_anonymous_does_not_leak_author():
    # attribution=None means anonymous; a stale author must be suppressed.
    winner = _user("w-001", "Winner Wendy", "1000001")
    deck = _deck(author="Sneaky Real Name", attribution=None)
    assert await _captured_credit(winner=winner, deck=deck, designer=None) == ""


@pytest.mark.asyncio
async def test_self_attribution_by_vekn_omits_credit():
    # Designer == player (matched by vekn): redundant with header, omit.
    winner = _user("w-001", "Winner Wendy", "1000001")
    deck = _deck(author="Winner Wendy", attribution="1000001")
    assert await _captured_credit(winner=winner, deck=deck, designer=winner) == ""


@pytest.mark.asyncio
async def test_self_attribution_by_name_omits_credit():
    # Player has no vekn; self-attribution falls back to their name.
    winner = _user("w-001", "Winner Wendy", "")
    deck = _deck(author="Winner Wendy", attribution="Winner Wendy")
    assert await _captured_credit(winner=winner, deck=deck, designer=None) == ""


@pytest.mark.asyncio
async def test_other_designer_resolved_from_vekn():
    # Different designer: credit the resolved member name, not the player.
    winner = _user("w-001", "Winner Wendy", "1000001")
    designer = _user("u-002", "Designer Bob", "2000002")
    deck = _deck(author="stale", attribution="2000002")
    credit = await _captured_credit(winner=winner, deck=deck, designer=designer)
    assert credit == "Designer Bob"


@pytest.mark.asyncio
async def test_other_designer_unresolved_falls_back_to_author():
    # Attribution is a name/unknown vekn: fall back to the stored author text.
    winner = _user("w-001", "Winner Wendy", "1000001")
    deck = _deck(author="Typed Designer", attribution="9999999")
    credit = await _captured_credit(winner=winner, deck=deck, designer=None)
    assert credit == "Typed Designer"


@pytest.mark.asyncio
async def test_twda_sentinel_passes_author_through():
    # Historical TWDA import: author already holds the entry's player name.
    winner = _user("w-001", "Winner Wendy", "1000001")
    deck = _deck(author="Historical Player", attribution="twda")
    credit = await _captured_credit(winner=winner, deck=deck, designer=None)
    assert credit == "Historical Player"
