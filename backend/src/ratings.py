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

    Gates on `rounds`, not `finals`: a VEKN import has no per-round detail but DOES
    carry a reconstructed finals object (a subset — the final table). Counting it
    would undercount the field to ~5; the full field lives in standings instead.
    """
    if t.rounds:
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
    # VEKN-synced or rounds-less: use standings (finalists always carry prelim TP)
    return {s.user_uid for s in t.standings if s.gw or s.vp or s.tp}


def _player_count(t: Tournament) -> int:
    """Count of players with ≥1 round played.

    Stays inclusive of disqualified players (tournament-rules A.2): a DQ'd player
    still inflates the head-count feeding everyone else's finalist coefficient.
    """
    return len(_players_with_rounds(t))


def _final_positions(t: Tournament) -> dict[str, int]:
    """{user_uid: final placement} for one finished tournament.

    Placement comes from the engine's shared rule (winner 1, other finalists tied
    for 2, non-finalists ranked from finalist_count+1) so the displayed position
    matches the tournament page exactly. Computed once per tournament by the
    caller, never per (user, tournament) — the map is user-independent.
    """
    config = msgspec.json.encode(
        {"standings": t.standings, "winner": t.winner}
    ).decode()
    ranked = msgspec.json.decode(_engine.compute_final_standings(config))
    return {s["user_uid"]: s["rank"] for s in ranked}


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


def _compute_entry(
    t: Tournament,
    t_json: str,
    sanctions_json: str,
    user_uid: str,
    player_count: int,
    positions: dict[str, int],
) -> TournamentRatingEntry:
    """Core entry computation from pre-encoded JSON + precomputed player count.

    VP/GW (including finals and the SA penalty) come from the Rust engine so the
    standings-adjustment scoring rule lives in one place — not re-implemented here.
    The daily recompute hoists the encode/count out of its per-user loop and calls
    this directly; the single-tournament push path uses _compute_entry_sync below.
    """
    engine = _engine
    vp, gw = engine.compute_rating_vp_gw(t_json, sanctions_json, user_uid)
    gw = int(gw)
    fp = _finalist_position(t, user_uid)
    points = engine.compute_rating_points(vp, gw, fp, player_count, t.rank.value)
    return TournamentRatingEntry(
        tournament_uid=t.uid,
        tournament_name=t.name,
        date=(t.finish or t.start or t.modified).date().isoformat(),
        player_count=player_count,
        rank=t.rank.value,
        vp=vp,
        gw=gw,
        finalist_position=fp,
        points=points,
        position=positions.get(user_uid, 0),
    )


def _compute_entry_sync(
    t: Tournament, user_uid: str, sanctions: list | None = None
) -> TournamentRatingEntry:
    """Compute a TournamentRatingEntry without DB access (uses pre-loaded sanctions).

    Convenience wrapper that encodes + counts on the spot; delegates to _compute_entry.
    """
    return _compute_entry(
        t,
        msgspec.json.encode(t).decode(),
        msgspec.json.encode(sanctions or []).decode(),
        user_uid,
        _player_count(t),
        _final_positions(t),
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

    # Precompute per-tournament data once, not per (user, tournament): the played
    # set, encoded JSON, and player count are user-independent. Avoids re-scanning
    # rounds and re-encoding the full tournament O(players) times.
    # The engine's ranking_eligibility gate (rules 3.1/3.1.6) drops open-rounds/
    # self-organized house events AND events with < 8 players or no final — the
    # same single-sourced predicate the frontend ranked/unranked badge displays.
    played_by_t: dict[str, set[str]] = {}
    json_by_t: dict[str, str] = {}
    count_by_t: dict[str, int] = {}
    positions_by_t: dict[str, dict[str, int]] = {}
    eligible: list[Tournament] = []
    for t in all_tournaments:
        t_json = msgspec.json.encode(t).decode()
        if _engine.ranking_eligibility(t_json) != "eligible":
            continue
        eligible.append(t)
        played_by_t[t.uid] = _players_with_rounds(t)
        json_by_t[t.uid] = t_json
        count_by_t[t.uid] = len(played_by_t[t.uid])
        positions_by_t[t.uid] = _final_positions(t)
    all_tournaments = eligible

    # Fetch wins + the player User objects in batch (one query each, not N).
    wins_map = await get_tournament_wins_for_users(player_uids)
    users_by_uid = await get_users_by_uids(player_uids)

    updated_users: list[tuple[User, BroadcastData]] = []
    sanctions_cache: dict[str, list] = {}
    sanctions_json_cache: dict[str, str] = {}

    for user_uid in player_uids:
        user = users_by_uid.get(user_uid)
        if not user:
            continue

        entries: list[TournamentRatingEntry] = []
        for t in all_tournaments:
            if user_uid not in played_by_t[t.uid]:
                continue
            if t.uid not in sanctions_cache:
                sanc = await get_sanctions_for_tournament(t.uid)
                sanctions_cache[t.uid] = sanc
                sanctions_json_cache[t.uid] = msgspec.json.encode(sanc).decode()
            if _is_disqualified(t, sanctions_cache[t.uid], user_uid):
                continue  # DQ'd: no rating entry, no participation base
            if _is_non_competing(t, user_uid):
                continue  # proxy: non-competing official stood in — no rating
            entries.append(
                _compute_entry(
                    t,
                    json_by_t[t.uid],
                    sanctions_json_cache[t.uid],
                    user_uid,
                    count_by_t[t.uid],
                    positions_by_t[t.uid],
                )
            )

        # Explicit tie-break so the no-change comparison below isn't fooled by the
        # unordered tournament fetch varying row order between runs.
        entries.sort(key=lambda e: (-e.points, e.tournament_uid))
        top_entries = entries[:TOP_N]
        total = sum(e.points for e in top_entries)

        cat_rating = CategoryRating(total=total, tournaments=entries)
        new_wins = sorted(wins_map.get(user_uid, []))

        # No-change guard: skip the JSONB upsert + SSE delta when neither the
        # category rating nor the wins moved. Keeps `modified` meaningful and
        # avoids churning the whole rated corpus daily for unchanged data.
        if cat_rating == getattr(user, category.value) and new_wins == user.wins:
            continue

        # Embed rating into user
        setattr(user, category.value, cat_rating)
        user.wins = new_wins
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
            if _engine.ranking_eligibility(json_str) != "eligible":
                continue  # house format / < 8 players / no final: never rated
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
