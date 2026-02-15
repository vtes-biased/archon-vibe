"""Rating aggregation logic.

Recomputes player ratings when tournaments finish.
Uses the Rust engine for per-tournament point calculation.
"""

import logging
from datetime import UTC, datetime, timedelta

from uuid6 import uuid7

from .db import (
    get_finished_tournaments_for_category,
    get_rating_by_user_uid,
    get_sanctions_for_tournament,
    get_user_by_uid,
    upsert_rating,
)
from .models import (
    CategoryRating,
    PlayerState,
    Rating,
    RatingCategory,
    SanctionLevel,
    Tournament,
    TournamentRatingEntry,
)

logger = logging.getLogger(__name__)

# Rolling window for rating computation
RATING_WINDOW_MONTHS = 18
TOP_N = 8


def _get_engine():
    """Get Rust engine (lazy)."""
    from archon_engine import PyEngine

    global _engine
    if "_engine" not in globals():
        _engine = PyEngine()
    return _engine


def _rating_category_for_tournament(t: Tournament) -> RatingCategory:
    """Map tournament format + online to RatingCategory."""
    engine = _get_engine()
    cat_str = engine.rating_category(t.format.value, t.online)
    return RatingCategory(cat_str)


def _players_with_rounds(t: Tournament) -> set[str]:
    """Get user_uids of players who played at least 1 round.

    For VEKN-synced tournaments (no rounds/finals), uses standings instead.
    """
    if t.rounds or t.finals:
        played = set()
        for round_tables in t.rounds:
            for table in round_tables:
                for seat in table.seating:
                    if seat.player_uid:
                        played.add(seat.player_uid)
        if t.finals:
            for seat in t.finals.seating:
                if seat.player_uid:
                    played.add(seat.player_uid)
        return played
    # VEKN-synced or rounds-less: use standings
    return {s.user_uid for s in t.standings if s.gw or s.vp or s.tp}


def _player_count(t: Tournament) -> int:
    """Count of players with ≥1 round played."""
    return len(_players_with_rounds(t))


def _player_stats(t: Tournament, user_uid: str) -> tuple[float, int]:
    """Compute total VP and GW for a player across all rounds.

    For VEKN-synced tournaments (no rounds), reads from standings.
    """
    if t.rounds:
        total_vp = 0.0
        total_gw = 0
        for round_tables in t.rounds:
            for table in round_tables:
                for seat in table.seating:
                    if seat.player_uid == user_uid:
                        total_vp += seat.result.vp
                        total_gw += seat.result.gw
        return total_vp, total_gw
    # VEKN-synced or rounds-less: read from standings
    for s in t.standings:
        if s.user_uid == user_uid:
            return s.vp, int(s.gw)
    return 0.0, 0


def _finalist_position(t: Tournament, user_uid: str) -> int:
    """0=none, 1=winner, 2=runner-up."""
    if t.winner == user_uid:
        return 1
    if t.finals:
        # Runner-up: in finals but not winner
        for seat in t.finals.seating:
            if seat.player_uid == user_uid and user_uid != t.winner:
                return 2
    return 0


async def _sa_overflow_penalty(t: Tournament, user_uid: str) -> float:
    """Compute SA overflow VP penalty for a player.

    If an SA sanction targets a round where the player's raw VP < 1.0,
    the overflow (1.0 - raw_vp) is an additional VP penalty.
    """
    if not t.rounds:
        return 0.0
    sanctions = await get_sanctions_for_tournament(t.uid)
    sa_sanctions = [
        s for s in sanctions
        if s.level == SanctionLevel.STANDINGS_ADJUSTMENT
        and s.user_uid == user_uid
        and not s.lifted_at
        and not s.deleted_at
        and s.round_number is not None
    ]
    penalty = 0.0
    for s in sa_sanctions:
        rn = s.round_number
        if rn >= len(t.rounds):
            continue
        round_vp = 0.0
        for table in t.rounds[rn]:
            for seat in table.seating:
                if seat.player_uid == user_uid:
                    round_vp = seat.result.vp
        if round_vp < 1.0:
            penalty += 1.0 - round_vp
    return penalty


async def _compute_entry(t: Tournament, user_uid: str) -> TournamentRatingEntry:
    """Compute a TournamentRatingEntry for one player in one tournament."""
    engine = _get_engine()
    vp, gw = _player_stats(t, user_uid)
    # Apply SA overflow penalty to VP
    overflow = await _sa_overflow_penalty(t, user_uid)
    vp -= overflow
    fp = _finalist_position(t, user_uid)
    pc = _player_count(t)
    points = engine.compute_rating_points(vp, gw, fp, pc, t.rank.value)
    return TournamentRatingEntry(
        tournament_uid=t.uid,
        tournament_name=t.name,
        date=(t.finish or t.start or t.modified).date().isoformat(),
        player_count=pc,
        rank=t.rank.value,
        vp=vp,
        gw=gw,
        finalist_position=fp,
        points=points,
    )


async def recompute_ratings_for_players(
    player_uids: set[str], category: RatingCategory
) -> list[Rating]:
    """Recompute ratings for an explicit set of players in a category.

    Used when a tournament enters or leaves Finished state.
    """
    if not player_uids:
        return []

    cutoff = datetime.now(UTC) - timedelta(days=RATING_WINDOW_MONTHS * 30)
    cutoff_str = cutoff.isoformat()

    if category in (RatingCategory.CONSTRUCTED_ONLINE, RatingCategory.CONSTRUCTED_OFFLINE):
        formats = ["Standard", "V5"]
    else:
        formats = ["Limited"]
    online = category in (RatingCategory.CONSTRUCTED_ONLINE, RatingCategory.LIMITED_ONLINE)

    all_tournaments: list[Tournament] = []
    for fmt in formats:
        all_tournaments.extend(
            await get_finished_tournaments_for_category(fmt, online, cutoff_str)
        )

    updated_ratings: list[Rating] = []
    now = datetime.now(UTC)

    for user_uid in player_uids:
        entries: list[TournamentRatingEntry] = []
        for t in all_tournaments:
            played = _players_with_rounds(t)
            if user_uid in played:
                entries.append(await _compute_entry(t, user_uid))

        entries.sort(key=lambda e: e.points, reverse=True)
        top_entries = entries[:TOP_N]
        total = sum(e.points for e in top_entries)

        existing = await get_rating_by_user_uid(user_uid)
        rating_uid = existing.uid if existing else str(uuid7())

        user = await get_user_by_uid(user_uid)

        country = user.country if user else None

        cat_rating = CategoryRating(total=total, tournaments=entries)
        rating = Rating(
            uid=rating_uid,
            modified=now,
            user_uid=user_uid,

            country=country,
            constructed_online=existing.constructed_online if existing else None,
            constructed_offline=existing.constructed_offline if existing else None,
            limited_online=existing.limited_online if existing else None,
            limited_offline=existing.limited_offline if existing else None,
        )
        setattr(rating, category.value, cat_rating)
        await upsert_rating(rating)
        updated_ratings.append(rating)

    logger.info(
        f"Recomputed {len(updated_ratings)} ratings for {category.value}"
    )
    return updated_ratings


async def recompute_ratings_for_tournament(tournament: Tournament) -> list[Rating]:
    """Recompute ratings for all players in a finished tournament.

    Returns list of updated Rating objects (for broadcasting).
    """
    if tournament.state.value != "Finished":
        return []

    category = _rating_category_for_tournament(tournament)
    players = _players_with_rounds(tournament)
    if not players:
        return []

    # Date window: 18 months back from now
    cutoff = datetime.now(UTC) - timedelta(days=RATING_WINDOW_MONTHS * 30)
    cutoff_str = cutoff.isoformat()

    # Determine format values that map to this category
    # Standard/V5 → constructed, Limited → limited
    if category in (RatingCategory.CONSTRUCTED_ONLINE, RatingCategory.CONSTRUCTED_OFFLINE):
        formats = ["Standard", "V5"]
    else:
        formats = ["Limited"]

    online = category in (RatingCategory.CONSTRUCTED_ONLINE, RatingCategory.LIMITED_ONLINE)

    # Fetch all finished tournaments in this category within window
    all_tournaments: list[Tournament] = []
    for fmt in formats:
        all_tournaments.extend(
            await get_finished_tournaments_for_category(fmt, online, cutoff_str)
        )

    updated_ratings: list[Rating] = []
    now = datetime.now(UTC)

    for user_uid in players:
        # Compute entries for this player across all tournaments in window
        entries: list[TournamentRatingEntry] = []
        for t in all_tournaments:
            played = _players_with_rounds(t)
            if user_uid in played:
                entries.append(await _compute_entry(t, user_uid))

        # Sort by points descending, take top 8
        entries.sort(key=lambda e: e.points, reverse=True)
        top_entries = entries[:TOP_N]
        total = sum(e.points for e in top_entries)

        # Get or create Rating object
        existing = await get_rating_by_user_uid(user_uid)
        if existing:
            rating_uid = existing.uid
        else:
            rating_uid = str(uuid7())

        user = await get_user_by_uid(user_uid)

        country = user.country if user else None

        # Build category rating
        cat_rating = CategoryRating(total=total, tournaments=entries)

        # Build full Rating, preserving other categories from existing
        rating = Rating(
            uid=rating_uid,
            modified=now,
            user_uid=user_uid,

            country=country,
            constructed_online=existing.constructed_online if existing else None,
            constructed_offline=existing.constructed_offline if existing else None,
            limited_online=existing.limited_online if existing else None,
            limited_offline=existing.limited_offline if existing else None,
        )
        # Set the computed category
        setattr(rating, category.value, cat_rating)

        await upsert_rating(rating)
        updated_ratings.append(rating)

    logger.info(
        f"Recomputed {len(updated_ratings)} ratings for tournament "
        f"{tournament.uid} ({category.value})"
    )
    return updated_ratings
