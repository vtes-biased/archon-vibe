"""Rating aggregation logic.

Recomputes player ratings when tournaments finish.
Uses the Rust engine for per-tournament point calculation.

New sync: ratings are embedded into User objects (no separate Rating table).
"""

import calendar
import logging
from datetime import UTC, datetime

import msgspec
from archon_engine import PyEngine

from .db import (
    BroadcastData,
    decode_json,
    get_finished_tournaments_for_category,
    get_sanctions_for_tournament,
    get_tournament_wins_for_users,
    get_users_by_uids,
    save_user,
    stream_objects_new,
)
from .models import (
    CategoryRating,
    PlayerState,
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
    """Count of players with ≥1 round played.

    Stays inclusive of disqualified players (tournament-rules A.2): a DQ'd player
    still inflates the head-count feeding everyone else's finalist coefficient.
    """
    return len(_players_with_rounds(t))


def _is_disqualified(t: Tournament, sanctions: list | None, user_uid: str) -> bool:
    """A DQ'd player earns no rating from this tournament — not even the
    participation base. Mirrors the engine's dual signal (player state set by the
    DQ-sanction route, or an active disqualification sanction)."""
    for p in t.players:
        if p.user_uid == user_uid and p.state == PlayerState.DISQUALIFIED:
            return True
    return any(
        s.user_uid == user_uid
        and s.level == SanctionLevel.DISQUALIFICATION
        and s.lifted_at is None
        and s.deleted_at is None
        for s in (sanctions or [])
    )


def _is_non_competing(t: Tournament, user_uid: str) -> bool:
    """A proxied (non-competing) player earns no rating from this tournament — a
    non-competing official stood in for them. Unlike DQ the score is not zeroed, so
    they must be skipped explicitly here (mirrors the engine's standings/finals
    exclusion)."""
    return any(p.user_uid == user_uid and p.non_competing for p in t.players)


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


def _compute_entry_sync(
    t: Tournament, user_uid: str, sanctions: list | None = None
) -> TournamentRatingEntry:
    """Compute a TournamentRatingEntry without DB access (uses pre-loaded sanctions).

    VP/GW (including finals and the SA penalty) come from the Rust engine so the
    standings-adjustment scoring rule lives in one place — not re-implemented here.
    """
    engine = _engine
    t_json = msgspec.json.encode(t).decode()
    sanctions_json = msgspec.json.encode(sanctions or []).decode()
    vp, gw = engine.compute_rating_vp_gw(t_json, sanctions_json, user_uid)
    gw = int(gw)
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
    # Open-rounds / self-organized events are the non-VEKN house format — they never
    # count toward ratings/RTP (mirrors their exclusion from VEKN push).
    all_tournaments = [
        t for t in all_tournaments if not (t.open_rounds or t.self_organized_rounds)
    ]

    # Fetch wins + the player User objects in batch (one query each, not N).
    wins_map = await get_tournament_wins_for_users(player_uids)
    users_by_uid = await get_users_by_uids(player_uids)

    updated_users: list[tuple[User, BroadcastData]] = []
    sanctions_cache: dict[str, list] = {}

    for user_uid in player_uids:
        user = users_by_uid.get(user_uid)
        if not user:
            continue

        entries: list[TournamentRatingEntry] = []
        for t in all_tournaments:
            played = _players_with_rounds(t)
            if user_uid in played:
                if t.uid not in sanctions_cache:
                    sanctions_cache[t.uid] = await get_sanctions_for_tournament(t.uid)
                if _is_disqualified(t, sanctions_cache[t.uid], user_uid):
                    continue  # DQ'd: no rating entry, no participation base
                if _is_non_competing(t, user_uid):
                    continue  # proxy: non-competing official stood in — no rating
                entries.append(_compute_entry_sync(t, user_uid, sanctions_cache[t.uid]))

        entries.sort(key=lambda e: e.points, reverse=True)
        top_entries = entries[:TOP_N]
        total = sum(e.points for e in top_entries)

        cat_rating = CategoryRating(total=total, tournaments=entries)

        # Embed rating into user
        setattr(user, category.value, cat_rating)
        user.wins = wins_map.get(user_uid, [])
        user.modified = now

        bd = await save_user(user)
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
            if t.open_rounds or t.self_organized_rounds:
                continue  # non-VEKN house format: excluded from ratings
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
