"""ETL + daily merge: legacy **archon** DB → **archon-vibe** unified `objects` table.

Two modes against the same mapping code:

* **Insert-only ETL** (default): Phase 0 of the production migration — initial
  population of an empty new DB (`--truncate` wipes first). Kept for beta
  rebuilds and as a disaster fallback.
* **Idempotent merge** (`--merge`): run daily on the new stack during the
  parallel run, old archon being a temporary second upstream (read-only) until
  decommission. Single writer per field: the VEKN sync owns identity
  (name/country/city/state), this sync owns archon-local fields (contact /
  nickname / discord / coopted_by, sanctions, leagues, rich play data), and
  ROLES are never UPDATED by either — seeded on a member's first import (by
  this ETL/merge, or VEKN-derived in the member sync's create path when it
  gets there first), app-managed thereafter. Fields recorded in
  `User.local_modifications` are never overwritten (same contract as the VEKN
  member sync). Merge mode takes a pre-run `pg_dump` of the NEW DB so a buggy
  merge is restore-fix-rerun.

Reads the OLD archon Postgres (members / leagues / tournaments / clients /
member_deletions) and writes the NEW archon-vibe schema, REUSING the backend's
own `save_*` helpers so the public/member/full access projections are computed
byte-identically to runtime. Note: writes from this script are NOT broadcast
live over SSE (broadcast is in-process in the backend); clients pick them up
through the catch-up sync on their next SSE reconnect.

Mapping decisions are recorded in `.pst/details/35-archon-production-migration.md`,
merge semantics in `.pst/details/115-legacy-archon-sync.md`. Highlights:
  * roles    Admin→IC, Playtester→PT (others identical) — seed only, see above
  * format   Draft→Limited (draft is a limited format)
  * rank     Grand Prix→BASIC (new model has no GP rank; GP lives in league mode)
  * state    Finals→Playing (new model has no FINALS tournament state)
  * sanctions old free-ish category/level → new JG-v2 category(+subcategory)
  * OAuth    clients table is empty in prod → nothing to migrate (re-register)
  * ratings  skipped — recomputed from tournaments post-import

Tournament matching in merge mode (at most one LIVE tournament per vekn event
id): match by uid, else by `external_ids.archon` (set when a previous run
merged the rich payload into a vekn-created copy), else by `external_ids.vekn`
— rich data merges INTO the vekn-created copy (its uid survives, deep links
stay valid); a round-less incoming copy never overwrites a rich original (echo
guard); both rich is a one-app-per-event violation: logged loudly, skipped.

Dry-run against the sandbox:
    cd backend
    OLD_DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_old \\
    NEW_DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_new \\
    uv run python scripts/migrate_from_archon.py --truncate

`--limit N` caps each type for quick smoke runs; `--truncate` wipes the new
objects/auth_methods first so ETL reruns are idempotent.
"""

import argparse
import asyncio
import os
import subprocess
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

# Make backend/src importable when run as a standalone script.
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import msgspec
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
from src.vekn_sync import OFFICIALS_EMAILS
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

# Archon-local member fields this sync owns in merge mode. Identity
# (name/country/city/state) is the VEKN sync's (old-archon identity edits reach
# us through vekn.net), roles are app-managed post-seed, and anything listed in
# the user's local_modifications is never overwritten.
ARCHON_USER_FIELDS = (
    "nickname",
    "contact_email",
    "contact_discord",
    "discord_id",
    "contact_phone",
    "phone_is_whatsapp",
    "coopted_by",
)

# Deterministic deck identity: one deck per (tournament, user, round) — reruns
# replace-by-key instead of inserting duplicates.
DECK_NS = uuid.uuid5(uuid.NAMESPACE_URL, "archon-vibe/legacy-deck")


def deck_uid(tuid: str, puid: str, round_idx: int | None) -> str:
    return str(uuid.uuid5(DECK_NS, f"{tuid}:{puid}:{round_idx}"))


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


def same_but_modified(built: msgspec.Struct, existing: msgspec.Struct) -> bool:
    """True when `built` equals `existing` apart from the `modified` timestamp —
    the merge's skip-if-unchanged test (avoids daily rewrite + SSE churn for
    every object)."""
    return msgspec.structs.replace(built, modified=existing.modified) == existing


class Stats(Counter):
    def bump(self, key: str, n: int = 1) -> None:
        self[key] += n


def loud(msg: str) -> None:
    """Conflicts and dedups must stand out in the (journald) logs."""
    print(f"!! {msg}", flush=True)


# --------------------------------------------------------------------------- #
# Live-object lookups (merge mode)                                             #
#                                                                              #
# Soft-deleted rows must not match: tombstones from previous dedups would      #
# otherwise shadow the live holder.                                            #
# --------------------------------------------------------------------------- #


async def live_user_by_vekn_id(vekn_id: str) -> db.User | None:
    async with db.get_connection() as conn:
        res = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND "full"->>'vekn_id' = %s
              AND deleted_at IS NULL LIMIT 1""",
            (vekn_id,),
        )
        row = await res.fetchone()
    return db.decode_json(row[0], db.User) if row else None


async def live_tournament_by_ext(platform: str, ext_id: str) -> Tournament | None:
    async with db.get_connection() as conn:
        res = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'tournament' AND "full"->'external_ids'->>%s = %s
              AND deleted_at IS NULL LIMIT 1""",
            (platform, ext_id),
        )
        row = await res.fetchone()
    return db.decode_json(row[0], Tournament) if row else None


async def other_live_vekn_holders(ext_id: str, but_uid: str) -> list[Tournament]:
    async with db.get_connection() as conn:
        res = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'tournament' AND "full"->'external_ids'->>'vekn' = %s
              AND uid != %s AND deleted_at IS NULL""",
            (ext_id, but_uid),
        )
        rows = await res.fetchall()
    return [db.decode_json(row[0], Tournament) for row in rows]


# --------------------------------------------------------------------------- #
# Members                                                                      #
# --------------------------------------------------------------------------- #


def build_user(row: dict, stats: Stats) -> tuple[db.User, dict]:
    """Old member row → (User, discord blob). Pure mapping, no I/O."""
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
        # Roles are SEEDED here (first appearance of the member) and app-managed
        # from then on: no sync — VEKN or this one — ever writes roles again.
        roles=roles,
        contact_email=nz(d.get("email")),
        contact_discord=nz(discord.get("username")) or nz(discord.get("global_name")),
        discord_id=nz(discord.get("id")),
        contact_phone=whatsapp,
        phone_is_whatsapp=bool(whatsapp),
        coopted_by=nz(d.get("sponsor")),
        vekn_prefix=nz(d.get("prefix")),
        # Imported members owe no VEKN push: they either already exist in the
        # vekn.net registry or predate it. Without this, batch_push would
        # re-register ~19k members on its first run (model default False), and
        # the residue unmatched by the first member sync would stay
        # push-eligible forever.
        vekn_synced=True,
    )
    return user, discord


async def ensure_discord_auth(user_uid: str, discord: dict, stats: Stats) -> None:
    """Insert the Discord auth method if that Discord account isn't linked yet.

    Legacy password hashes are NOT argon2 and can't be verified by the new
    stack, so no (broken) email/password auth is created — email users
    re-establish access via magic-link (keyed on the migrated contact_email) or
    Discord.
    """
    discord_id = nz(discord.get("id"))
    if not discord_id:
        return
    existing = await db.get_auth_method_by_identifier("discord", discord_id)
    if existing:
        if existing.user_uid != user_uid:
            loud(
                f"discord auth conflict: account {discord_id} linked to user "
                f"{existing.user_uid}, old archon says {user_uid} — left alone"
            )
            stats.bump("warn.discord_auth_conflict")
        return
    await db.insert_auth_method(
        AuthMethod(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            user_uid=user_uid,
            method_type=AuthMethodType.DISCORD,
            identifier=discord_id,
            verified=bool(discord.get("verified", True)),
        )
    )
    stats.bump("auth.discord")


async def merge_member(user: db.User, discord: dict, stats: Stats) -> None:
    """Idempotent member upsert: insert new members wholesale (the seed), merge
    only archon-owned fields into existing ones."""
    existing = await db.get_user_by_uid(user.uid)

    if existing is None:
        if user.vekn_id:
            # vekn-first echo: a member created on old archon reached us through
            # the vekn.net member sync first, under a fresh uid. The old-archon
            # copy carries the history (contacts, auth, references from its
            # tournaments) — it wins; tombstone the identity-only vekn copy.
            holder = await live_user_by_vekn_id(user.vekn_id)
            if holder is not None:
                now = datetime.now(UTC)
                holder.deleted_at = now
                holder.modified = now
                # The unique index on vekn_id spans tombstones (one user per
                # vekn id, ever): release the number to the surviving user.
                holder.vekn_id = None
                await db.save_user(holder)
                loud(
                    f"member dedup: soft-deleted vekn-created user {holder.uid} "
                    f"(vekn {user.vekn_id}); old-archon user {user.uid} takes over"
                )
                stats.bump("members.vekn_copy_tombstoned")
        await db.save_user(user)
        await ensure_discord_auth(user.uid, discord, stats)
        stats.bump("members.inserted")
        return

    if existing.deleted_at:
        # Deleted on the new stack — never resurrect from upstream.
        stats.bump("members.skipped_deleted")
        return

    changed = False
    for field in ARCHON_USER_FIELDS:
        if field in existing.local_modifications:
            continue
        value = getattr(user, field)
        # coopted_by: the VEKN sync infers sponsors for members old archon has
        # none recorded for — an old-archon None must not wipe that inference
        # (it would flip-flop daily with the inference re-filling it).
        if field == "coopted_by" and value is None:
            continue
        # Officials' contact_email is injected by the VEKN member sync from the
        # scraped vekn.net lists — writing old archon's address here would
        # flip-flop daily with that injection.
        if field == "contact_email" and existing.vekn_id in OFFICIALS_EMAILS:
            continue
        if getattr(existing, field) != value:
            setattr(existing, field, value)
            changed = True
    if changed:
        existing.modified = datetime.now(UTC)
        await db.save_user(existing)
        stats.bump("members.updated")
    else:
        stats.bump("members.unchanged")
    if "discord_id" not in existing.local_modifications:
        await ensure_discord_auth(existing.uid, discord, stats)


async def migrate_members(
    old: psycopg.AsyncConnection, stats: Stats, limit: int | None, merge: bool
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
            user, discord = build_user(row, stats)
            if merge:
                await merge_member(user, discord, stats)
            else:
                await db.save_user(user)
                await ensure_discord_auth(user.uid, discord, stats)
            live.add(user.uid)
            stats.bump("users")
            if stats["users"] % 2000 == 0:
                print(f"  …{stats['users']} users")
    return live


async def migrate_member_deletions(
    old: psycopg.AsyncConnection, live: set[str], stats: Stats, merge: bool
) -> None:
    """member_deletions → soft-deleted User shells (ETL: preserve referential
    integrity for historical records pointing at a deleted member; merge: also
    propagate deletions of members that exist live on the new stack)."""
    async with old.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT uid, deleted_at FROM member_deletions")
        rows = await cur.fetchall()
    for row in rows:
        uid = str(row["uid"])
        if uid in live:
            continue  # a live member with the same uid wins
        del_at = parse_dt(row["deleted_at"]) or datetime.now(UTC)
        if merge:
            existing = await db.get_user_by_uid(uid)
            if existing is not None:
                if existing.deleted_at:
                    continue  # already propagated
                existing.deleted_at = del_at
                existing.modified = datetime.now(UTC)
                await db.save_user(existing)
                loud(f"member deletion propagated from old archon: {uid}")
                stats.bump("members.deletion_propagated")
                continue
        await db.save_user(
            db.User(
                uid=uid, modified=del_at, deleted_at=del_at, name="(deleted member)"
            )
        )
        stats.bump("deleted_user_shells")


# --------------------------------------------------------------------------- #
# Leagues                                                                      #
# --------------------------------------------------------------------------- #


async def migrate_leagues(
    old: psycopg.AsyncConnection, stats: Stats, merge: bool
) -> None:
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
        if merge:
            prev = await db.get_league_by_uid(league.uid)
            if prev is not None:
                if prev.deleted_at:
                    stats.bump("leagues.skipped_deleted")
                    continue
                if same_but_modified(league, prev):
                    stats.bump("leagues.unchanged")
                    continue
                league.modified = datetime.now(UTC)
        await db.save_league(league)
        stats.bump("leagues")


# --------------------------------------------------------------------------- #
# Sanctions                                                                    #
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Tournaments                                                                  #
# --------------------------------------------------------------------------- #


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


def _deck_obj(
    tuid: str, puid: str, round_idx: int | None, krcg: dict, public: bool
) -> DeckObject:
    return DeckObject(
        uid=deck_uid(tuid, puid, round_idx),
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


def build_tournament(
    d: dict,
    target_uid: str,
    existing: Tournament | None,
    sanctions: dict[str, Sanction],
    stats: Stats,
) -> tuple[Tournament, list[DeckObject]]:
    """Old tournament JSON → (Tournament under target_uid, extracted decks).

    Accumulates tournament-embedded sanctions into `sanctions` (keyed to
    target_uid; tref-sourced tournament refs are remapped by the caller)."""
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
    prelim: dict[str, list[float]] = {str(u): [0.0, 0.0, 0.0] for u in players_dict}
    total: dict[str, list[float]] = {str(u): [0.0, 0.0, 0.0] for u in players_dict}
    deck_ctx = _DeckCtx(
        finished=finished,
        mode=decklists_mode,
        finals_set=frozenset(finals_set),
        winner_uid=winner_uid,
    )
    seat_kw = {
        "tuid": target_uid,
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
                    seating=_build_seats(tbl.get("seating", []), ri, False, **seat_kw),
                    state=TABLE_STATE_MAP.get(tbl.get("state"), TableState.FINISHED),
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
                state=PLAYER_STATE_MAP.get(p.get("state"), PlayerState.REGISTERED),
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
                    target_uid,
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
    # In merge mode, entries the new stack already carries are preserved, and
    # the old-archon uid is recorded under "archon" when the rich payload
    # merged into a vekn-created copy (so later runs find it again by marker
    # instead of mistaking their own merge for a both-rich conflict).
    old_uid = str(d.get("uid") or target_uid)
    extra = d.get("extra") or {}
    external_ids: dict[str, str] = dict(existing.external_ids) if existing else {}
    if extra.get("vekn_id") not in (None, "", 0):
        vekn_eid = str(extra["vekn_id"])
        if external_ids.get("vekn") not in (None, vekn_eid):
            loud(
                f"vekn event id conflict on {target_uid}: ours "
                f"{external_ids['vekn']} vs old archon {vekn_eid} — old archon wins"
            )
            stats.bump("warn.vekn_event_id_conflict")
        external_ids["vekn"] = vekn_eid
    if target_uid != old_uid:
        external_ids["archon"] = old_uid

    t = Tournament(
        uid=target_uid,
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
        organizers_uids=[str(j["uid"]) for j in d.get("judges", []) if j.get("uid")],
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
        # Migrated events owe new archon no VEKN push. Under one-app-per-event
        # (#39) legacy owns each event until it's finished there; legacy pushes it
        # and the daily #115 --merge then carries the vekn id + results + this
        # stamp back, so new archon must never (re)create a calendar event or
        # (re)upload results for a migrated event. Stamp every NON-PLANNED import
        # — finished AND in-flight — the exact inverse of batch_push's
        # `state != 'Planned'` calendar-event gate (and a superset of the
        # finished+rounds results guard), so queries 2 and 3 both skip them.
        # Planned drafts aren't push-eligible anyway. Genuinely-new events created
        # in-app aren't ETL-stamped, so they still push normally. An existing
        # stamp is preserved (idempotent across daily merges).
        vekn_pushed_at=(existing.vekn_pushed_at if existing else None)
        or (datetime.now(UTC) if state != TournamentState.PLANNED else None),
    )

    # accumulate tournament-embedded sanctions (dict[member_uid → [Sanction]])
    for member_uid, slist in (d.get("sanctions") or {}).items():
        for s in slist:
            if s.get("uid"):
                sanctions[str(s["uid"])] = build_sanction(
                    s, str(member_uid), target_uid, stats
                )

    return t, decks


async def process_tournament_row(
    row: dict,
    sanctions: dict[str, Sanction],
    stats: Stats,
    merge: bool,
    uid_map: dict[str, str],
) -> None:
    """Migrate/merge one old tournament row. Records old_uid → surviving uid in
    `uid_map` (used to remap sanction tournament refs)."""
    d = dict(row["data"] or {})
    old_uid = str(row["uid"])
    d["uid"] = old_uid  # build_tournament reads it for the external_ids marker
    extra = d.get("extra") or {}
    vekn_eid = (
        str(extra["vekn_id"]) if extra.get("vekn_id") not in (None, "", 0) else None
    )

    target_uid = old_uid
    existing: Tournament | None = None
    if merge:
        existing = await db.get_tournament_by_uid(old_uid)
        if existing is not None and existing.deleted_at:
            # Deleted on the new stack — never resurrect from upstream.
            uid_map[old_uid] = old_uid
            stats.bump("tournaments.skipped_deleted")
            return
        if existing is None:
            # A previous run merged this event's rich payload into a
            # vekn-created copy: find it again by the marker.
            existing = await live_tournament_by_ext("archon", old_uid)
            if existing is not None:
                target_uid = existing.uid
        if existing is None and vekn_eid:
            x = await live_tournament_by_ext("vekn", vekn_eid)
            if x is not None:
                incoming_rich = bool(d.get("rounds"))
                if not incoming_rich:
                    # Echo guard: old archon's round-less copy of an event whose
                    # results live elsewhere (it synced them from vekn.net).
                    # Never import the pale copy over the original.
                    uid_map[old_uid] = x.uid
                    stats.bump("tournaments.echo_skipped")
                    return
                if x.rounds:
                    loud(
                        f"BOTH-RICH conflict on vekn event {vekn_eid}: ours {x.uid} "
                        f"and old archon {old_uid} both have rounds — one-app-per-"
                        f"event violation, skipped; resolve manually"
                    )
                    uid_map[old_uid] = x.uid
                    stats.bump("tournaments.both_rich_conflict")
                    return
                # Merge the rich payload INTO the vekn-created copy: its uid
                # survives (deep links stay valid, no client tombstone); the
                # next VEKN sync run hits the rich-guard and refreshes metadata
                # only.
                target_uid, existing = x.uid, x

    t, decks = build_tournament(d, target_uid, existing, sanctions, stats)
    uid_map[old_uid] = target_uid

    # vekn-linked events: the VEKN tournament sync owns descriptive metadata —
    # its rich-guard path refreshes name/format/rank/online/dates/timezone/
    # country/venue fields from vekn.net and unions organizers. Writing old
    # archon's values for those would flip-flop daily with that refresh. Keep
    # the existing metadata, write play data + archon-only config, and union
    # organizers the same way the VEKN sync does.
    if merge and existing is not None and "vekn" in t.external_ids:
        t = msgspec.structs.replace(
            existing,
            state=t.state,
            league_uid=t.league_uid,
            proxies=t.proxies,
            multideck=t.multideck,
            decklist_required=t.decklist_required,
            description=t.description,
            standings_mode=t.standings_mode,
            decklists_mode=t.decklists_mode,
            max_rounds=t.max_rounds,
            external_ids=t.external_ids,
            organizers_uids=list(
                dict.fromkeys(existing.organizers_uids + t.organizers_uids)
            ),
            players=t.players,
            rounds=t.rounds,
            finals=t.finals,
            winner=t.winner,
            standings=t.standings,
            vekn_pushed_at=t.vekn_pushed_at,
            modified=t.modified,
        )

    stats.bump("tournaments")
    if merge and existing is not None:
        if same_but_modified(t, existing):
            stats.bump("tournaments.unchanged")
        else:
            t.modified = datetime.now(UTC)
            await db.save_tournament(t)
            stats.bump("tournaments.updated")
    else:
        await db.save_tournament(t)
        if merge:
            stats.bump("tournaments.inserted")
        stats.bump(f"tournament_state:{t.state.value}")

    if merge and decks:
        prev_decks = {
            deck.uid: deck for deck in await db.get_decks_for_tournament(target_uid)
        }
        for deck in decks:
            prev = prev_decks.get(deck.uid)
            if prev is not None and same_but_modified(deck, prev):
                continue
            await db.save_object_from_model(db.ObjectType.DECK, deck)
            stats.bump("decks.upserted")
    else:
        for deck in decks:
            await db.save_object_from_model(db.ObjectType.DECK, deck)
            stats.bump("decks")
            if deck.public:
                stats.bump("decks_public")

    # Invariant: at most one live tournament per vekn event id. The archon-first
    # interleave creates a second holder (this sync inserts rich pre-push, the
    # VEKN sync creates a round-less copy before the rich one gains the id):
    # the rich copy wins, the round-less one is tombstoned.
    if merge and t.external_ids.get("vekn"):
        for other in await other_live_vekn_holders(t.external_ids["vekn"], target_uid):
            if other.rounds:
                loud(
                    f"BOTH-RICH conflict on vekn event {t.external_ids['vekn']}: "
                    f"{target_uid} and {other.uid} both live with rounds — "
                    f"resolve manually"
                )
                stats.bump("tournaments.both_rich_conflict")
            else:
                await db.soft_delete_tournament(other.uid)
                loud(
                    f"tournament dedup: soft-deleted round-less {other.uid} "
                    f"(vekn event {t.external_ids['vekn']}); rich {target_uid} wins"
                )
                stats.bump("tournaments.roundless_copy_tombstoned")


async def migrate_tournaments(
    old: psycopg.AsyncConnection,
    sanctions: dict[str, Sanction],
    stats: Stats,
    limit: int | None,
    merge: bool,
    uid_map: dict[str, str],
) -> None:
    q = "SELECT uid, data FROM tournaments"
    if limit:
        q += f" LIMIT {limit}"
    async with old.cursor(name="tournaments_cur", row_factory=dict_row) as cur:
        cur.itersize = 200
        await cur.execute(q)
        async for row in cur:
            await process_tournament_row(row, sanctions, stats, merge, uid_map)
            if stats["tournaments"] % 1000 == 0:
                print(f"  …{stats['tournaments']} tournaments")


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


async def save_sanctions(
    sanctions: dict[str, Sanction],
    stats: Stats,
    merge: bool,
    uid_map: dict[str, str],
) -> None:
    for s in sanctions.values():
        # Remap tournament refs to the surviving uid for events whose rich
        # payload merged into a vekn-created copy.
        if s.tournament_uid:
            s.tournament_uid = uid_map.get(s.tournament_uid, s.tournament_uid)
        if merge:
            prev = await db.get_sanction_by_uid(s.uid)
            if prev is not None and same_but_modified(s, prev):
                stats.bump("sanctions.unchanged")
                continue
            if prev is not None:
                s.modified = datetime.now(UTC)
        await db.save_sanction(s)
        stats.bump("sanctions")


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


async def truncate_new() -> None:
    async with db.get_connection() as conn:
        await conn.execute("TRUNCATE objects")
        await conn.execute("TRUNCATE auth_methods")


def backup_new_db(dsn: str, backup_dir: Path) -> Path:
    """Pre-merge pg_dump of the NEW DB — a buggy merge is restore-fix-rerun.
    Keeps the last 7 dumps."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = backup_dir / f"archon_vibe_premerge_{stamp}.dump"
    subprocess.run(["pg_dump", "-Fc", "-f", str(path), dsn], check=True)
    for stale in sorted(backup_dir.glob("archon_vibe_premerge_*.dump"))[:-7]:
        stale.unlink()
    return path


async def run(args: argparse.Namespace) -> None:
    db.DB_URL = args.new_dsn
    os.environ["DATABASE_URL"] = args.new_dsn
    if args.merge and not args.skip_backup:
        path = backup_new_db(args.new_dsn, Path(args.backup_dir))
        print(f"Pre-merge backup: {path}")
    await db.init_db()
    if args.truncate:
        print("Truncating new objects/auth_methods…")
        await truncate_new()

    # read-only source; autocommit=False keeps a transaction open so server-side
    # (named) cursors can DECLARE — we only read, never commit.
    old = await psycopg.AsyncConnection.connect(args.old_dsn, autocommit=False)
    stats = Stats()
    sanctions: dict[str, Sanction] = {}
    uid_map: dict[str, str] = {}
    try:
        print("→ members")
        live = await migrate_members(old, stats, args.limit, args.merge)
        print("→ member_deletions")
        await migrate_member_deletions(old, live, stats, args.merge)
        print("→ leagues")
        await migrate_leagues(old, stats, args.merge)
        print("→ tournaments (+ decks, + tournament sanctions)")
        await migrate_tournaments(
            old, sanctions, stats, args.limit, args.merge, uid_map
        )
        print("→ member sanctions (union by uid)")
        await migrate_member_sanctions(old, sanctions, stats)
        print(f"→ sanctions ({len(sanctions)} distinct)")
        await save_sanctions(sanctions, stats, args.merge, uid_map)
    finally:
        await old.close()
        await db.close_db()

    print(f"\n=== {'merge' if args.merge else 'migration'} summary ===")
    for k in sorted(stats):
        print(f"  {k:40s} {stats[k]}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="archon → archon-vibe ETL (initial population) / daily merge"
    )
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
    p.add_argument(
        "--merge",
        action="store_true",
        help="idempotent daily merge (parallel run) instead of insert-only ETL",
    )
    p.add_argument(
        "--backup-dir",
        default=os.getenv("MERGE_BACKUP_DIR", "."),
        help="where --merge writes the pre-run pg_dump (keeps last 7)",
    )
    p.add_argument(
        "--skip-backup",
        action="store_true",
        help="skip the pre-merge pg_dump (dev only)",
    )
    args = p.parse_args()
    if not args.old_dsn or not args.new_dsn:
        p.error(
            "both --old-dsn and --new-dsn (or env OLD_DATABASE_URL / NEW_DATABASE_URL) are required"
        )
    if args.merge and args.truncate:
        p.error("--merge and --truncate are mutually exclusive")
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
