"""Rating aggregation: recomputes player ratings when tournaments finish, using
the Rust engine for per-tournament point calculation. Embedded into User objects,
no separate Rating table."""

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
    """user_uids of players who played at least 1 round. Gates on `rounds`, not
    `finals`: a VEKN import has no per-round detail but DOES carry a reconstructed
    finals object (a subset), so counting it would undercount the field."""
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


def _final_positions(t: Tournament) -> dict[str, int]:
    """{user_uid: final placement} for one finished tournament, from the engine's
    shared rule — computed once per tournament, never per (user, tournament)."""
    config = msgspec.json.encode(
        {"standings": t.standings, "winner": t.winner}
    ).decode()
    ranked = msgspec.json.decode(_engine.compute_final_standings(config))
    # Drops the DQ'd/proxy tail (ranks past the whole field) using the stored
    # standings flags, not the player-state signal callers use — absent = no placement.
    return {
        s["user_uid"]: s["rank"]
        for s in ranked
        if not s.get("disqualified") and not s.get("non_competing")
    }


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
    VP/GW come from the Rust engine, so the SA-penalty scoring rule lives once, not here."""
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
    """Compute a TournamentRatingEntry without DB access (uses pre-loaded sanctions);
    encodes + counts on the spot, delegating to _compute_entry."""
    t_json = msgspec.json.encode(t).decode()
    return _compute_entry(
        t,
        t_json,
        msgspec.json.encode(sanctions or []).decode(),
        user_uid,
        _engine.attested_player_count(t_json),
        _final_positions(t),
    )


async def recompute_ratings_for_players(
    player_uids: set[str], category: RatingCategory
) -> list[tuple[User, BroadcastData]]:
    """Recompute ratings for an explicit set of players in a category, embedding
    rating data directly into User objects. Returns (user, BroadcastData) tuples."""
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

    # Precomputed once per tournament, not per (user, tournament) — avoids
    # re-scanning rounds and re-encoding O(players) times.
    played_by_t: dict[str, set[str]] = {}
    json_by_t: dict[str, str] = {}
    count_by_t: dict[str, int] = {}
    positions_by_t: dict[str, dict[str, int]] = {}
    eligible: list[Tournament] = []
    for t in all_tournaments:
        t_json = msgspec.json.encode(t).decode()
        # Same single-sourced predicate the frontend ranked/unranked badge displays.
        if _engine.ranking_eligibility(t_json) != "eligible":
            continue
        eligible.append(t)
        played_by_t[t.uid] = _players_with_rounds(t)
        json_by_t[t.uid] = t_json
        # Who earns an entry vs how big the field was: two questions, two counts.
        count_by_t[t.uid] = _engine.attested_player_count(t_json)
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

        # No-change guard: skip the JSONB upsert + SSE delta when neither moved —
        # keeps `modified` meaningful and avoids churning the corpus daily.
        if cat_rating == getattr(user, category.value) and new_wins == user.wins:
            continue

        setattr(user, category.value, cat_rating)
        user.wins = new_wins
        user.modified = now

        bd = await save_user(user)
        updated_users.append((user, bd))

    logger.info(f"Recomputed {len(updated_users)} ratings for {category.value}")
    return updated_users


async def recompute_all_ratings() -> int:
    """Full recomputation of all ratings and wins, called daily. Broadcasts each
    category's deltas as produced and returns only the count: holding every
    (User, BroadcastData) until the end would spike memory on a full-corpus run."""
    from .broadcast import broadcast_precomputed

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
    updated = 0
    for category, player_uids in players_by_category.items():
        if not player_uids:
            continue
        for _user, bd in await recompute_ratings_for_players(player_uids, category):
            broadcast_precomputed(bd)
            updated += 1

    logger.info(f"Full rating recompute: {updated} users updated")
    return updated
