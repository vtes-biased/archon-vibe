"""ETL: legacy **archon** DB → **archon-vibe** unified `objects` table.

Phase 0 of the production migration. Reads the OLD archon Postgres
(members / leagues / tournaments / clients / member_deletions) and writes the NEW
archon-vibe schema, REUSING the backend's own `save_*` helpers so the
public/member/full access projections are computed byte-identically to runtime.

Mapping decisions are recorded in `.pst/details/35-archon-production-migration.md`.
Highlights:
  * roles    Admin→IC, Playtester→PT (others identical)
  * format   Draft→Limited (draft is a limited format)
  * rank     Grand Prix→BASIC (new model has no GP rank; GP lives in league mode)
  * state    Finals→Playing (new model has no FINALS tournament state)
  * sanctions old free-ish category/level → new JG-v2 category(+subcategory)
  * OAuth    clients table is empty in prod → nothing to migrate (re-register)
  * ratings  skipped — recomputed from tournaments post-import (Phase 2)

Dry-run against the sandbox:
    cd backend
    OLD_DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_old \\
    NEW_DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_new \\
    uv run python scripts/migrate_from_archon.py --truncate

`--limit N` caps each type for quick smoke runs; `--truncate` wipes the new
objects/auth_methods first so reruns are idempotent.
"""

import argparse
import asyncio
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

# Make backend/src importable when run as a standalone script.
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import psycopg
from psycopg.rows import dict_row
from src import db
from src.models import (
    AuthMethod,
    AuthMethodType,
    DeckListsMode,
    DeckObject,
    FinalsTable,
    League,
    LeagueKind,
    LeagueStandingsMode,
    Player,
    PlayerState,
    Role,
    Sanction,
    SanctionCategory,
    SanctionLevel,
    SanctionSubcategory,
    Score,
    Seat,
    Standing,
    StandingsMode,
    Table,
    TableState,
    Tournament,
    TournamentFormat,
    TournamentRank,
    TournamentState,
)
from uuid6 import uuid7

# --------------------------------------------------------------------------- #
# Mapping tables                                                               #
# --------------------------------------------------------------------------- #

ROLE_MAP: dict[str, Role] = {
    "Admin": Role.IC,
    "Playtester": Role.PT,
    "PTC": Role.PTC,
    "Prince": Role.PRINCE,
    "Rulemonger": Role.RULEMONGER,
    "Judge": Role.JUDGE,
    "Judgekin": Role.JUDGEKIN,
    "NC": Role.NC,
    "Ethics": Role.ETHICS,
}

FORMAT_MAP: dict[str, TournamentFormat] = {
    "Standard": TournamentFormat.Standard,
    "V5": TournamentFormat.V5,
    "Limited": TournamentFormat.Limited,
    "Draft": TournamentFormat.Limited,  # draft is a limited format
}

RANK_MAP: dict[str, TournamentRank] = {
    "": TournamentRank.BASIC,
    "National Championship": TournamentRank.NC,
    "Continental Championship": TournamentRank.CC,
    "Grand Prix": TournamentRank.BASIC,  # no GP rank in new model
}

STATE_MAP: dict[str, TournamentState] = {
    "Planned": TournamentState.PLANNED,
    "Registration": TournamentState.REGISTRATION,
    "Waiting": TournamentState.WAITING,
    "Playing": TournamentState.PLAYING,
    "Finals": TournamentState.PLAYING,  # no FINALS state in new model
    "Finished": TournamentState.FINISHED,
}

PLAYER_STATE_MAP: dict[str, PlayerState] = {
    "Registered": PlayerState.REGISTERED,
    "Checked-in": PlayerState.CHECKED_IN,
    "Playing": PlayerState.PLAYING,
    "Finished": PlayerState.FINISHED,
}

TABLE_STATE_MAP: dict[str, TableState] = {
    "Finished": TableState.FINISHED,
    "In Progress": TableState.IN_PROGRESS,
    "Invalid": TableState.INVALID,
}

SANCTION_LEVEL_MAP: dict[str, SanctionLevel] = {
    "Caution": SanctionLevel.CAUTION,
    "Warning": SanctionLevel.WARNING,
    "Disqualification": SanctionLevel.DISQUALIFICATION,
    "Ban": SanctionLevel.SUSPENSION,  # closest long-term removal
}

# old category → (new category, new subcategory | None)
SANCTION_CATEGORY_MAP: dict[
    str, tuple[SanctionCategory, SanctionSubcategory | None]
] = {
    "": (SanctionCategory.PROCEDURAL_ERROR, None),
    "Deck Problem": (
        SanctionCategory.TOURNAMENT_ERROR,
        SanctionSubcategory.ILLEGAL_DECKLIST,
    ),
    "Procedural Error": (
        SanctionCategory.PROCEDURAL_ERROR,
        SanctionSubcategory.GAME_RULE_VIOLATION,
    ),
    "Card drawing": (
        SanctionCategory.PROCEDURAL_ERROR,
        SanctionSubcategory.CARD_ACCESS_ERROR,
    ),
    "Marked Cards": (
        SanctionCategory.TOURNAMENT_ERROR,
        SanctionSubcategory.MARKED_CARDS,
    ),
    "Slow Play": (SanctionCategory.TOURNAMENT_ERROR, SanctionSubcategory.SLOW_PLAY),
    "Unsportsmanlike Conduct": (
        SanctionCategory.UNSPORTSMANLIKE_CONDUCT,
        SanctionSubcategory.MINOR,
    ),
    "Cheating": (
        SanctionCategory.UNSPORTSMANLIKE_CONDUCT,
        SanctionSubcategory.CHEATING,
    ),
    "Ethics": (SanctionCategory.UNSPORTSMANLIKE_CONDUCT, None),
}

LEAGUE_RANKING_MAP: dict[str, LeagueStandingsMode] = {
    "RTP": LeagueStandingsMode.RTP,
    "GP": LeagueStandingsMode.GP,
    "Score": LeagueStandingsMode.SCORE,
}

DECKLISTS_MODE_MAP: dict[str, DeckListsMode] = {
    "Winner": DeckListsMode.WINNER,
    "Finalists": DeckListsMode.FINALISTS,
    "All": DeckListsMode.ALL,
}

STANDINGS_MODE_MAP: dict[str, StandingsMode] = {
    "Private": StandingsMode.PRIVATE,
    "Cutoff": StandingsMode.CUTOFF,
    "Top 10": StandingsMode.TOP_10,
    "Public": StandingsMode.PUBLIC,
}

# --------------------------------------------------------------------------- #
# Small helpers                                                                #
# --------------------------------------------------------------------------- #


def parse_dt(v) -> datetime | None:
    """Parse old timestamps (ISO strings from JSONB, or psycopg datetimes)."""
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def nz(s) -> str | None:
    """Empty / whitespace string → None."""
    if s is None:
        return None
    s = str(s).strip()
    return s or None


def score_of(d) -> Score:
    d = d or {}
    return Score(
        gw=int(d.get("gw", 0) or 0),
        vp=float(d.get("vp", 0.0) or 0.0),
        tp=int(d.get("tp", 0) or 0),
    )


def flatten_deck(krcg: dict) -> dict[str, int]:
    """KrcgDeck {crypt:{cards:[{id,count}]}, library:{cards:[{cards:[{id,count}]}]}}
    → {str(card_id): count}, matching twda_import / providers card encoding."""
    cards: dict[str, int] = {}
    for c in (krcg.get("crypt") or {}).get("cards", []):
        if c.get("id") is not None:
            cards[str(c["id"])] = int(c.get("count", 0) or 0)
    for group in (krcg.get("library") or {}).get("cards", []):
        for c in group.get("cards", []):
            if c.get("id") is not None:
                cards[str(c["id"])] = int(c.get("count", 0) or 0)
    return cards


class Stats(Counter):
    def bump(self, key: str, n: int = 1) -> None:
        self[key] += n


# --------------------------------------------------------------------------- #
# Migrators                                                                    #
# --------------------------------------------------------------------------- #


async def migrate_members(
    old: psycopg.AsyncConnection, stats: Stats, limit: int | None
) -> set[str]:
    """members → User (+ AuthMethod rows). Returns the set of live user uids."""
    live: set[str] = set()
    q = "SELECT uid, vekn, data, last_updated FROM members"
    if limit:
        q += f" LIMIT {limit}"
    async with old.cursor(name="members_cur", row_factory=dict_row) as cur:
        cur.itersize = 500
        await cur.execute(q)
        async for row in cur:
            d = row["data"] or {}
            uid = str(row["uid"])
            discord = d.get("discord") or {}
            whatsapp = nz(d.get("whatsapp"))
            roles: list[Role] = []
            for r in d.get("roles", []):
                mapped = ROLE_MAP.get(r)
                if mapped:
                    roles.append(mapped)
                else:
                    stats.bump(f"warn.unknown_role:{r}")

            user = db.User(
                uid=uid,
                modified=parse_dt(row["last_updated"]) or datetime.now(UTC),
                name=d.get("name") or "(unknown)",
                country=nz(d.get("country")),
                vekn_id=nz(row.get("vekn")) or nz(d.get("vekn")),
                city=nz(d.get("city")),
                city_geoname_id=d.get("city_geoname_id"),
                nickname=nz(d.get("nickname")),
                roles=roles,
                contact_email=nz(d.get("email")),
                contact_discord=nz(discord.get("username"))
                or nz(discord.get("global_name")),
                discord_id=nz(discord.get("id")),
                contact_phone=whatsapp,
                phone_is_whatsapp=bool(whatsapp),
                coopted_by=nz(d.get("sponsor")),
                vekn_prefix=nz(d.get("prefix")),
                # Imported members owe no VEKN push: they either already exist in
                # the vekn.net registry or predate it. Without this, batch_push
                # would re-register ~19k members on its first run (model default
                # False), and the residue unmatched by the first member sync
                # would stay push-eligible forever.
                vekn_synced=True,
                # Protect existing role assignments from the later VEKN sync, which
                # only derives Prince/NC/IC/static-judges and would otherwise strip
                # archon-assigned Judge/Judgekin/Ethics/Rulemonger/PTC/PT. Role-less
                # users stay unprotected so VEKN can still grant Prince/NC. Identity
                # fields (name/country/city/state) are intentionally left for VEKN to
                # own (authoritative registry).
                local_modifications={"roles"} if roles else set(),
            )
            await db.save_user(user)
            live.add(uid)
            stats.bump("users")

            # auth methods: Discord only. Legacy password hashes are NOT argon2 and
            # can't be verified by the new stack, so no (broken) email/password auth is
            # created — email users re-establish access via magic-link (keyed on the
            # migrated contact_email) or Discord. Discord login keeps working via the
            # migrated discord_id.
            if nz(discord.get("id")):
                await db.insert_auth_method(
                    AuthMethod(
                        uid=str(uuid7()),
                        modified=datetime.now(UTC),
                        user_uid=uid,
                        method_type=AuthMethodType.DISCORD,
                        identifier=str(discord["id"]),
                        verified=bool(discord.get("verified", True)),
                    )
                )
                stats.bump("auth.discord")

            if stats["users"] % 2000 == 0:
                print(f"  …{stats['users']} users")
    return live


async def migrate_member_deletions(
    old: psycopg.AsyncConnection, live: set[str], stats: Stats
) -> None:
    """member_deletions → soft-deleted User shells (preserve referential integrity
    for any historical record pointing at a deleted member)."""
    async with old.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT uid, deleted_at FROM member_deletions")
        rows = await cur.fetchall()
    for row in rows:
        uid = str(row["uid"])
        if uid in live:
            continue  # a live member with the same uid wins
        del_at = parse_dt(row["deleted_at"]) or datetime.now(UTC)
        await db.save_user(
            db.User(
                uid=uid, modified=del_at, deleted_at=del_at, name="(deleted member)"
            )
        )
        stats.bump("deleted_user_shells")


async def migrate_leagues(old: psycopg.AsyncConnection, stats: Stats) -> None:
    async with old.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT uid, start, finish, data FROM leagues")
        rows = await cur.fetchall()
    for row in rows:
        d = row["data"] or {}
        parent = d.get("parent") or {}
        fmt = d.get("format")
        league = League(
            uid=str(row["uid"]),
            modified=parse_dt(row["finish"])
            or parse_dt(row["start"])
            or datetime.now(UTC),
            name=d.get("name") or "(unnamed league)",
            kind=LeagueKind.META
            if d.get("kind") == "Meta-League"
            else LeagueKind.LEAGUE,
            standings_mode=LEAGUE_RANKING_MAP.get(
                d.get("ranking"), LeagueStandingsMode.RTP
            ),
            format=(FORMAT_MAP[fmt].value if fmt in FORMAT_MAP else None),
            country=nz(d.get("country")),
            start=parse_dt(row["start"]),
            finish=parse_dt(row["finish"]),
            description=d.get("description") or "",
            organizers_uids=[
                str(o["uid"]) for o in d.get("organizers", []) if o.get("uid")
            ],
            parent_uid=nz(parent.get("uid")),
        )
        await db.save_league(league)
        stats.bump("leagues")


def build_sanction(
    s: dict, user_uid: str, fallback_tournament_uid: str | None, stats: Stats
) -> Sanction:
    cat, subcat = SANCTION_CATEGORY_MAP.get(
        s.get("category", ""), (SanctionCategory.PROCEDURAL_ERROR, None)
    )
    if s.get("category") and s["category"] not in SANCTION_CATEGORY_MAP:
        stats.bump(f"warn.unknown_sanction_category:{s['category']}")
    judge = s.get("judge") or {}
    tref = s.get("tournament") or {}
    issued_by = nz(judge.get("uid")) or user_uid
    if not nz(judge.get("uid")):
        stats.bump("warn.sanction_without_judge")
    issued_at = parse_dt(tref.get("start")) or datetime.now(UTC)
    return Sanction(
        uid=str(s["uid"]),
        modified=issued_at,
        user_uid=user_uid,
        issued_by_uid=issued_by,
        tournament_uid=nz(tref.get("uid")) or fallback_tournament_uid,
        level=SANCTION_LEVEL_MAP.get(s.get("level"), SanctionLevel.WARNING),
        category=cat,
        subcategory=subcat,
        description=s.get("comment") or "",
        issued_at=issued_at,
    )


class _DeckCtx(NamedTuple):
    """Per-tournament inputs for deck visibility (engine's compute_deck_public)."""

    finished: bool
    mode: DeckListsMode
    finals_set: frozenset[str]
    winner_uid: str


def _deck_public(owner_uid: str, ctx: _DeckCtx) -> bool:
    """Replicate the engine's decklists_mode visibility policy (raffle.rs) for
    migrated decks: visible only on a finished tournament, per Winner/Finalists/All."""
    if not ctx.finished:
        return False
    if ctx.mode == DeckListsMode.ALL:
        return True
    if ctx.mode == DeckListsMode.FINALISTS:
        return owner_uid in ctx.finals_set
    return owner_uid == ctx.winner_uid  # WINNER


def _build_seats(
    seating_raw: list,
    round_idx: int | None,
    is_finals: bool,
    *,
    tuid: str,
    multideck: bool,
    deck_ctx: _DeckCtx,
    prelim: dict[str, list[float]],
    total: dict[str, list[float]],
    decks: list[DeckObject],
) -> list[Seat]:
    """Build Seats from old seating (scores PRESERVED from source), accumulating
    prelim-only (non-finals) and prelim+finals score sums per player, and
    extracting per-round decks for multideck tournaments."""
    seats: list[Seat] = []
    for s in seating_raw:
        puid = str(s.get("player_uid"))
        pj = s.get("judge") or {}
        r = score_of(s.get("result"))
        seats.append(Seat(player_uid=puid, result=r, judge_uid=nz(pj.get("uid")) or ""))
        total.setdefault(puid, [0.0, 0.0, 0.0])
        total[puid][0] += r.gw
        total[puid][1] += r.vp
        total[puid][2] += r.tp
        if not is_finals:
            prelim.setdefault(puid, [0.0, 0.0, 0.0])
            prelim[puid][0] += r.gw
            prelim[puid][1] += r.vp
            prelim[puid][2] += r.tp
        if multideck and s.get("deck"):
            decks.append(
                _deck_obj(
                    tuid, puid, round_idx, s["deck"], _deck_public(puid, deck_ctx)
                )
            )
    return seats


async def migrate_tournaments(
    old: psycopg.AsyncConnection,
    sanctions: dict[str, Sanction],
    stats: Stats,
    limit: int | None,
) -> None:
    q = "SELECT uid, data FROM tournaments"
    if limit:
        q += f" LIMIT {limit}"
    async with old.cursor(name="tournaments_cur", row_factory=dict_row) as cur:
        cur.itersize = 200
        await cur.execute(q)
        async for row in cur:
            d = row["data"] or {}
            tuid = str(row["uid"])
            players_dict: dict = d.get("players") or {}
            finals_seeds = [str(x) for x in (d.get("finals_seeds") or [])]
            finals_set = set(finals_seeds)
            multideck = bool(d.get("multideck"))
            state = STATE_MAP.get(d.get("state"), TournamentState.PLANNED)
            finished = state == TournamentState.FINISHED
            winner_uid = nz(d.get("winner")) or ""
            decklists_mode = DECKLISTS_MODE_MAP.get(
                d.get("decklists_mode"), DeckListsMode.WINNER
            )

            # rounds reshape: [Round{tables}] → [[Table]]; last round becomes the
            # FinalsTable when finals_seeds is set.
            old_rounds = d.get("rounds") or []
            has_rounds = len(old_rounds) > 0
            has_finals = bool(finals_seeds) and has_rounds
            prelim_src = old_rounds[:-1] if has_finals else old_rounds
            finals_src = old_rounds[-1] if has_finals else None
            decks: list[DeckObject] = []

            # Seat scores are PRESERVED from old archon (verified correct: 0 GW-rule
            # violations across prod prelim seats, finals GW matches the engine's
            # finals rule). VP/GW/TP are summed per player into prelim-only (feeds
            # `standings`) and prelim+finals (feeds Player.result). Keeping the two
            # separated is the actual fix: league scoring (league.rs) adds finals on
            # top of prelim standings, and the old vekn-push bug came from folding
            # finals into prelim. The new standings model is "prelim-only".
            prelim: dict[str, list[float]] = {
                str(u): [0.0, 0.0, 0.0] for u in players_dict
            }
            total: dict[str, list[float]] = {
                str(u): [0.0, 0.0, 0.0] for u in players_dict
            }
            deck_ctx = _DeckCtx(
                finished=finished,
                mode=decklists_mode,
                finals_set=frozenset(finals_set),
                winner_uid=winner_uid,
            )
            seat_kw = {
                "tuid": tuid,
                "multideck": multideck,
                "deck_ctx": deck_ctx,
                "prelim": prelim,
                "total": total,
                "decks": decks,
            }

            new_rounds: list[list[Table]] = []
            for ri, rd in enumerate(prelim_src):
                new_rounds.append(
                    [
                        Table(
                            seating=_build_seats(
                                tbl.get("seating", []), ri, False, **seat_kw
                            ),
                            state=TABLE_STATE_MAP.get(
                                tbl.get("state"), TableState.FINISHED
                            ),
                        )
                        for tbl in rd.get("tables", [])
                    ]
                )

            finals: FinalsTable | None = None
            if finals_src and finals_src.get("tables"):
                ftbl = finals_src["tables"][0]
                finals = FinalsTable(
                    seating=_build_seats(
                        ftbl.get("seating", []), len(prelim_src), True, **seat_kw
                    ),
                    seed_order=finals_seeds,
                    state=TABLE_STATE_MAP.get(ftbl.get("state"), TableState.FINISHED),
                )

            # players (result = prelim+finals for rich; old aggregate for round-less
            # imports) + standings (prelim-only)
            players: list[Player] = []
            standings: list[Standing] = []
            for puid, p in players_dict.items():
                puid = str(puid)
                toss = int(p.get("toss", 0) or 0)
                finalist = puid in finals_set
                if has_rounds:
                    tg, tv, tt = total[puid]
                    pg, pv, pt = prelim[puid]
                    result = Score(gw=int(tg), vp=tv, tp=int(tt))
                    standings.append(
                        Standing(
                            user_uid=puid,
                            gw=float(int(pg)),
                            vp=pv,
                            tp=int(pt),
                            toss=toss,
                            finalist=finalist,
                        )
                    )
                else:
                    result = score_of(p.get("result"))
                    standings.append(
                        Standing(
                            user_uid=puid,
                            gw=float(result.gw),
                            vp=result.vp,
                            tp=result.tp,
                            toss=toss,
                            finalist=finalist,
                        )
                    )
                players.append(
                    Player(
                        user_uid=puid,
                        state=PLAYER_STATE_MAP.get(
                            p.get("state"), PlayerState.REGISTERED
                        ),
                        toss=toss,
                        result=result,
                        finalist=finalist,
                    )
                )

            # match engine sort: gw/vp/tp/toss desc, then uid asc (deterministic)
            standings.sort(key=lambda s: (-s.gw, -s.vp, -s.tp, -s.toss, s.user_uid))

            # monodeck default decks (round=None) from player.deck
            for puid, p in players_dict.items():
                if p.get("deck"):
                    decks.append(
                        _deck_obj(
                            tuid,
                            str(puid),
                            None,
                            p["deck"],
                            _deck_public(str(puid), deck_ctx),
                        )
                    )

            # description note for migrated Draft-format tournaments
            description = d.get("description") or ""
            if d.get("format") == "Draft":
                description = ("[Originally Draft format] " + description).strip()

            league_ref = d.get("league") or {}
            # old archon stored the vekn.net event id in extra.vekn_id; the new stack
            # keys vekn tournaments by external_ids["vekn"], so map it there — that lets
            # the later VEKN tournament sync MATCH these instead of creating duplicates.
            extra = d.get("extra") or {}
            external_ids: dict[str, str] = {}
            if extra.get("vekn_id") not in (None, "", 0):
                external_ids["vekn"] = str(extra["vekn_id"])

            t = Tournament(
                uid=tuid,
                modified=parse_dt(d.get("finish"))
                or parse_dt(d.get("start"))
                or datetime.now(UTC),
                name=d.get("name") or "(unnamed tournament)",
                format=FORMAT_MAP.get(d.get("format"), TournamentFormat.Standard),
                rank=RANK_MAP.get(d.get("rank"), TournamentRank.BASIC),
                online=bool(d.get("online")),
                start=parse_dt(d.get("start")),
                finish=parse_dt(d.get("finish")),
                timezone=d.get("timezone") or "UTC",
                country=nz(d.get("country")),
                league_uid=nz(league_ref.get("uid")),
                state=state,
                organizers_uids=[
                    str(j["uid"]) for j in d.get("judges", []) if j.get("uid")
                ],
                venue=d.get("venue") or "",
                venue_url=d.get("venue_url") or "",
                address=d.get("address") or "",
                map_url=d.get("map_url") or "",
                proxies=bool(d.get("proxies")),
                multideck=multideck,
                decklist_required=bool(d.get("decklist_required")),
                description=description,
                standings_mode=STANDINGS_MODE_MAP.get(
                    d.get("standings_mode"), StandingsMode.PRIVATE
                ),
                decklists_mode=decklists_mode,
                max_rounds=int(d.get("max_rounds", 0) or 0),
                external_ids=external_ids,
                checkin_code=d.get("checkin_code") or "",
                players=players,
                rounds=new_rounds,
                finals=finals,
                winner=winner_uid,
                standings=standings,
                # Imported finished tournaments owe no push: old archon already
                # pushed them (or they predate pushing). Rich imports have rounds,
                # so batch_push's rounds guard does NOT keep them out of the
                # results push — and their standings fold finals in, while
                # archondata assumes prelim-only (a re-push would send wrong
                # numbers). Stamped whether or not they carry a vekn id, so the
                # calendar-event query skips them too.
                vekn_pushed_at=datetime.now(UTC) if finished else None,
            )
            await db.save_tournament(t)
            stats.bump("tournaments")
            stats.bump(f"tournament_state:{t.state.value}")
            for deck in decks:
                await db.save_object_from_model(db.ObjectType.DECK, deck)
                stats.bump("decks")
                if deck.public:
                    stats.bump("decks_public")

            # accumulate tournament-embedded sanctions (dict[member_uid → [Sanction]])
            for member_uid, slist in (d.get("sanctions") or {}).items():
                for s in slist:
                    if s.get("uid"):
                        sanctions[str(s["uid"])] = build_sanction(
                            s, str(member_uid), tuid, stats
                        )

            if stats["tournaments"] % 1000 == 0:
                print(f"  …{stats['tournaments']} tournaments")


def _deck_obj(
    tuid: str, puid: str, round_idx: int | None, krcg: dict, public: bool
) -> DeckObject:
    return DeckObject(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        tournament_uid=tuid,
        user_uid=puid,
        round=round_idx,
        name=krcg.get("name") or "",
        author=krcg.get("author") or "",
        comments=krcg.get("comments") or "",
        cards=flatten_deck(krcg),
        # old archon never recorded designer-credit consent, so default to
        # anonymous rather than fabricating self-attribution (privacy-safe).
        attribution=None,
        public=public,
    )


async def migrate_member_sanctions(
    old: psycopg.AsyncConnection, sanctions: dict[str, Sanction], stats: Stats
) -> None:
    """member.sanctions (dict on the sanctioned member). Tournament-embedded copies
    (already in `sanctions`) win on uid — they carry the containing tournament."""
    async with old.cursor(name="member_san_cur", row_factory=dict_row) as cur:
        cur.itersize = 1000
        await cur.execute(
            "SELECT uid, data FROM members WHERE data->'sanctions' <> '[]'::jsonb"
        )
        async for row in cur:
            for s in (row["data"] or {}).get("sanctions", []):
                if s.get("uid") and str(s["uid"]) not in sanctions:
                    sanctions[str(s["uid"])] = build_sanction(
                        s, str(row["uid"]), None, stats
                    )


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


async def truncate_new() -> None:
    async with db.get_connection() as conn:
        await conn.execute("TRUNCATE objects")
        await conn.execute("TRUNCATE auth_methods")


async def run(args: argparse.Namespace) -> None:
    db.DB_URL = args.new_dsn
    os.environ["DATABASE_URL"] = args.new_dsn
    await db.init_db()
    if args.truncate:
        print("Truncating new objects/auth_methods…")
        await truncate_new()

    # read-only source; autocommit=False keeps a transaction open so server-side
    # (named) cursors can DECLARE — we only read, never commit.
    old = await psycopg.AsyncConnection.connect(args.old_dsn, autocommit=False)
    stats = Stats()
    sanctions: dict[str, Sanction] = {}
    try:
        print("→ members")
        live = await migrate_members(old, stats, args.limit)
        print("→ member_deletions")
        await migrate_member_deletions(old, live, stats)
        print("→ leagues")
        await migrate_leagues(old, stats)
        print("→ tournaments (+ decks, + tournament sanctions)")
        await migrate_tournaments(old, sanctions, stats, args.limit)
        print("→ member sanctions (union by uid)")
        await migrate_member_sanctions(old, sanctions, stats)
        print(f"→ sanctions ({len(sanctions)} distinct)")
        for s in sanctions.values():
            await db.save_sanction(s)
            stats.bump("sanctions")
    finally:
        await old.close()
        await db.close_db()

    print("\n=== migration summary ===")
    for k in sorted(stats):
        print(f"  {k:40s} {stats[k]}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="archon → archon-vibe ETL (Phase 0)")
    p.add_argument(
        "--old-dsn", default=os.getenv("OLD_DATABASE_URL"), help="source archon DSN"
    )
    p.add_argument(
        "--new-dsn",
        default=os.getenv("NEW_DATABASE_URL") or os.getenv("DATABASE_URL"),
        help="target archon-vibe DSN",
    )
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument(
        "--limit", type=int, default=None, help="cap members & tournaments (smoke test)"
    )
    p.add_argument(
        "--truncate", action="store_true", help="wipe new objects/auth_methods first"
    )
    args = p.parse_args()
    if not args.old_dsn or not args.new_dsn:
        p.error(
            "both --old-dsn and --new-dsn (or env OLD_DATABASE_URL / NEW_DATABASE_URL) are required"
        )
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
