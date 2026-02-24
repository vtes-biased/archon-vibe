"""Rating aggregation logic.

Recomputes player ratings when tournaments finish.
Uses the Rust engine for per-tournament point calculation.

New sync: ratings are embedded into User objects (no separate Rating table).
"""

import calendar
import logging
from datetime import UTC, datetime

from archon_engine import PyEngine

from .db import (
    BroadcastData,
    decode_json,
    get_finished_tournaments_for_category,
    get_sanctions_for_tournament,
    get_tournament_wins_for_users,
    get_user_by_uid,
    stream_objects_new,
    update_user,
)
from .models import (
    CategoryRating,
    RatingCategory,
    SanctionLevel,
    Tournament,
    TournamentRatingEntry,
    User,
)

logger = logging.getLogger(__name__)

# Rolling window for rating computation
RATING_WINDOW_MONTHS = 18
TOP_N = 8

_engine = PyEngine()


def rating_category_for_tournament(t: Tournament) -> RatingCategory:
    """Map tournament format + online to RatingCategory."""
    engine = _engine
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
    """Compute total VP and GW for a player across all rounds and finals.

    For VEKN-synced tournaments (no rounds/finals), reads from standings.
    """
    if t.rounds or t.finals:
        total_vp = 0.0
        total_gw = 0
        for round_tables in t.rounds:
            for table in round_tables:
                for seat in table.seating:
                    if seat.player_uid == user_uid:
                        total_vp += seat.result.vp
                        total_gw += seat.result.gw
        if t.finals:
            for seat in t.finals.seating:
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
    else:
        # VEKN-synced tournaments: no finals object, use standings/players
        for s in t.standings:
            if s.user_uid == user_uid and s.finalist:
                return 2
    return 0


def _sa_overflow_penalty(
    t: Tournament, user_uid: str, sanctions: list | None = None
) -> float:
    """Compute SA overflow VP penalty for a player.

    If an SA sanction targets a round where the player's raw VP < 1.0,
    the overflow (1.0 - raw_vp) is an additional VP penalty.
    sanctions: pre-loaded sanctions for this tournament (avoids DB query).
    """
    if not t.rounds:
        return 0.0
    sa_sanctions = [
        s
        for s in (sanctions or [])
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


def _compute_entry_sync(
    t: Tournament, user_uid: str, sanctions: list | None = None
) -> TournamentRatingEntry:
    """Compute a TournamentRatingEntry without DB access (uses pre-loaded sanctions)."""
    engine = _engine
    vp, gw = _player_stats(t, user_uid)
    overflow = _sa_overflow_penalty(t, user_uid, sanctions)
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


async def _compute_entry(t: Tournament, user_uid: str) -> TournamentRatingEntry:
    """Compute a TournamentRatingEntry for one player in one tournament."""
    sanctions = await get_sanctions_for_tournament(t.uid)
    return _compute_entry_sync(t, user_uid, sanctions)


async def recompute_ratings_for_players(
    player_uids: set[str], category: RatingCategory
) -> list[tuple[User, BroadcastData]]:
    """Recompute ratings for an explicit set of players in a category.

    Embeds rating data directly into User objects.
    Returns (user, BroadcastData) tuples for broadcasting.
    """
    if not player_uids:
        return []

    now = datetime.now(UTC)
    # Exact calendar months (not 30-day approximation) to match VEKN.net
    y, m = now.year, now.month - RATING_WINDOW_MONTHS
    while m <= 0:
        y -= 1
        m += 12
    max_day = calendar.monthrange(y, m)[1]
    cutoff = now.replace(year=y, month=m, day=min(now.day, max_day))
    cutoff_str = cutoff.isoformat()

    if category in (
        RatingCategory.CONSTRUCTED_ONLINE,
        RatingCategory.CONSTRUCTED_OFFLINE,
    ):
        formats = ["Standard", "V5"]
    else:
        formats = ["Limited"]
    online = category in (
        RatingCategory.CONSTRUCTED_ONLINE,
        RatingCategory.LIMITED_ONLINE,
    )

    all_tournaments: list[Tournament] = []
    for fmt in formats:
        all_tournaments.extend(
            await get_finished_tournaments_for_category(fmt, online, cutoff_str)
        )

    # Fetch wins for all players in batch
    wins_map = await get_tournament_wins_for_users(player_uids)

    updated_users: list[tuple[User, BroadcastData]] = []

    for user_uid in player_uids:
        user = await get_user_by_uid(user_uid)
        if not user:
            continue

        entries: list[TournamentRatingEntry] = []
        for t in all_tournaments:
            played = _players_with_rounds(t)
            if user_uid in played:
                entries.append(await _compute_entry(t, user_uid))

        entries.sort(key=lambda e: e.points, reverse=True)
        top_entries = entries[:TOP_N]
        total = sum(e.points for e in top_entries)

        cat_rating = CategoryRating(total=total, tournaments=entries)

        # Embed rating into user
        setattr(user, category.value, cat_rating)
        user.wins = wins_map.get(user_uid, [])
        user.modified = now

        bd = await update_user(user)
        updated_users.append((user, bd))

    logger.info(f"Recomputed {len(updated_users)} ratings for {category.value}")
    return updated_users


async def recompute_all_ratings() -> list[tuple[User, BroadcastData]]:
    """Full recomputation of all ratings and wins. Called daily for consistency.

    Lightweight first pass collects player UIDs per category (streaming tournaments).
    Then reuses recompute_ratings_for_players() per category.
    Returns (User, BroadcastData) tuples.
    """
    # Pass 1: stream tournaments to collect player sets per category
    players_by_category: dict[RatingCategory, set[str]] = {
        cat: set() for cat in RatingCategory
    }

    async for json_batch, _ in stream_objects_new("tournament", "full"):
        for json_str in json_batch:
            t = decode_json(json_str, Tournament)
            if t.state != "Finished" or t.deleted_at:
                continue
            category = rating_category_for_tournament(t)
            players = _players_with_rounds(t)
            players_by_category[category].update(players)

    # Pass 2: recompute per category using the normal code path
    all_updated: list[tuple[User, BroadcastData]] = []
    for category, player_uids in players_by_category.items():
        if not player_uids:
            continue
        results = await recompute_ratings_for_players(player_uids, category)
        all_updated.extend(results)

    logger.info(f"Full rating recompute: {len(all_updated)} users updated")
    return all_updated
