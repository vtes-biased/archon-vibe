"""ETL + daily merge: legacy **archon** DB → **archon-vibe** unified `objects` table.

Two modes against the same mapping code: insert-only ETL (default;
`--truncate` wipes first) for beta rebuilds and disaster fallback, and
idempotent `--merge`, run daily during the parallel-run period against old
archon as a read-only second upstream.

Reads the OLD archon Postgres (members / leagues / tournaments / clients /
member_deletions) and writes the NEW archon-vibe schema, REUSING the backend's
own `save_*` helpers so the public/member/full access projections are computed
byte-identically to runtime. Writes from this script are NOT broadcast live
over SSE; clients pick them up through the catch-up sync on their next SSE
reconnect.

Dry-run against the sandbox (from the repo root):
    OLD_DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_old \\
    NEW_DATABASE_URL=postgresql://etl:etl@localhost:5544/archon_new \\
    uv run python backend/scripts/migrate_from_archon.py --truncate

On the prod box the deployed venv already has `backend.src` installed, so run
it directly (no checkout needed) — this is what the archon-legacy-sync unit does:
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/migrate_from_archon.py --merge

`--limit N` caps each type for quick smoke runs; `--truncate` wipes the new
objects/auth_methods first so ETL reruns are idempotent.
"""

import argparse
import asyncio
import importlib.util
import os
import secrets
import subprocess
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Skip on the deployed box (already installed in the venv) — inserting the repo
# root there could let a stray src/ shadow the wheel package.
try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from uuid import uuid7

import msgspec
import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from backend.src import db
from backend.src.models import (
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
from backend.src.vekn_sync import OFFICIALS_EMAILS

# Wider than db.batch_read_connection's 120s: this is a whole daily job with a
# 24h window, not a pooled read inside a live server. Still capped, not disabled.
BATCH_STATEMENT_TIMEOUT_MS = 600_000


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

# This sync's field set in merge mode — identity is the VEKN sync's, roles are
# app-managed, local_modifications fields are never overwritten either way.
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


def _raw_dt(v) -> datetime | None:
    """Parse an old timestamp (ISO string from JSONB, or psycopg datetime),
    preserving whether it carried an offset."""
    if not v:
        return None
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def parse_dt(v) -> datetime | None:
    """Parse an instant (modified, deleted_at, …) — a naive value reads as UTC."""
    d = _raw_dt(v)
    return None if d is None else (d if d.tzinfo else d.replace(tzinfo=UTC))


def parse_wall_dt(v, tz_name: str | None) -> datetime | None:
    """Parse a tournament start/finish: NAIVE wall clock paired with `timezone`.
    Reading it as an instant stamps UTC onto that wall clock, then every reader
    that anchors it in the tournament timezone shifts it a second time."""
    d = _raw_dt(v)
    if d is None or d.tzinfo is None:
        return d
    try:
        return d.astimezone(ZoneInfo(tz_name or "UTC")).replace(tzinfo=None)
    except (ZoneInfoNotFoundError, ValueError):
        return d.astimezone(UTC).replace(tzinfo=None)


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


# Soft-deleted rows must not match: tombstones from previous dedups would
# otherwise shadow the live holder.
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


async def live_tournament_by_vekn(ext_id: str) -> Tournament | None:
    # 'vekn' stays a literal: it's the only external_ids key schema.sql indexes
    # (idx_objects_tournament_vekn); a different key seq-scans + detoasts every row.
    async with db.get_connection() as conn:
        res = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'tournament' AND "full"->'external_ids'->>'vekn' = %s
              AND deleted_at IS NULL LIMIT 1""",
            (ext_id,),
        )
        row = await res.fetchone()
    return db.decode_json(row[0], Tournament) if row else None


async def live_same_event_tournament(d: dict, old_uid: str) -> Tournament | None:
    """The live copy of this vekn-id-less legacy event, matched on name + start day.

    Fires only as the last key. More than one candidate means the key doesn't
    discriminate; a separate copy is inserted rather than guessed.
    """
    start = parse_wall_dt(d.get("start"), d.get("timezone"))
    name = d.get("name") or ""
    if start is None or not name:
        return None
    candidates = await db.find_same_event_tournaments(
        name, start, exclude_uid=old_uid, country=nz(d.get("country"))
    )
    if len(candidates) != 1:
        if candidates:
            loud(
                f"ambiguous name match for old archon {old_uid} '{name}' {start}: "
                f"{[c.uid for c in candidates]} — inserting a separate copy"
            )
        return None
    match = candidates[0]
    if match.external_ids.get("archon", old_uid) != old_uid:
        return None
    return match


async def archon_uid_index() -> dict[str, str]:
    """`external_ids['archon']` → live uid, in ONE scan (merge mode).

    Strings only, not decoded Tournaments — decoding every row here would be
    ~70 MB; hits re-fetch by uid and are rare.
    """
    async with db.get_connection() as conn:
        res = await conn.execute(
            """SELECT "full"->'external_ids'->>'archon', uid FROM objects
            WHERE type = 'tournament' AND deleted_at IS NULL
              AND "full"->'external_ids'->>'archon' IS NOT NULL"""
        )
        return {row[0]: row[1] for row in await res.fetchall()}


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


# #216: VEKN-less legacy participants. A player with no round seating is a
# registration artifact (drop); one who actually played must resolve to a real
# account (remap below, or allocate). Keyed by opaque old-archon uid only.

# old-archon member uid → the real VEKN id its tournament refs remap onto,
# resolved to the live account by resolve_known_remaps after the member pass.
KNOWN_REMAP: dict[str, str] = {
    "06194fea-a366-4d28-a89c-eb2ead795d65": "3390002",
}

# VEKN-less member uids dropped wholesale: 0-seating registration artifacts.
KNOWN_DROP: frozenset[str] = frozenset(
    {
        "021937b2-a40a-415d-a021-6ff3fe7da4a3",  # Neonate Revolution registrant, 0 rounds
        "19656201-a2fb-4925-93d6-c9e47eba1c28",  # funeral-wake phantom (organiser-entered dup)
    }
)

# (tournament_uid, member_uid) dropped from ONE tournament's players dict only:
# a real account's redundant no-show entry that KNOWN_REMAP would otherwise
# duplicate there — that member plays elsewhere, so the drop can't be wholesale.
KNOWN_DROP_IN_TOURNAMENT: frozenset[tuple[str, str]] = frozenset(
    {
        (
            "51aa6745-d409-42e8-8a8b-a8a214530bf6",
            "d9ca427b-c31a-4b22-a649-d32a6e622dd3",
        ),
    }
)


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
        # Imported members owe no VEKN push: they already exist on vekn.net or
        # predate it. Default False would make batch_push re-register ~19k members.
        vekn_synced=True,
    )
    return user, discord


async def ensure_discord_auth(user_uid: str, discord: dict, stats: Stats) -> None:
    """Insert the Discord auth method if that Discord account isn't linked yet.

    No email/password auth is created — legacy hashes aren't argon2 and can't be
    verified; email users re-establish access via magic-link or Discord instead.
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


async def seed_vekn_less_shell(user: db.User, stats: Stats) -> None:
    """Seed a soft-deleted shell under the old uid so historical refs resolve
    without creating a live identity. Never resurrects or modifies an existing row."""
    if await db.get_user_by_uid(user.uid) is not None:
        return
    now = datetime.now(UTC)
    await db.save_user(msgspec.structs.replace(user, deleted_at=now, modified=now))
    stats.bump("members.vekn_less_shell")


async def collect_tournament_participant_uids(old: psycopg.AsyncConnection) -> set[str]:
    """Member uids referenced as tournament participants, used by #216 to tell a
    VEKN-less member who actually played from a non-participant."""
    async with old.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT DISTINCT key AS uid FROM tournaments,
                 jsonb_each(COALESCE(data->'players', '{}'::jsonb))
            UNION
            SELECT DISTINCT s->>'player_uid' FROM tournaments,
                 jsonb_array_elements(COALESCE(data->'rounds', '[]'::jsonb)) rd,
                 jsonb_array_elements(COALESCE(rd->'tables', '[]'::jsonb)) tb,
                 jsonb_array_elements(COALESCE(tb->'seating', '[]'::jsonb)) s
              WHERE s->>'player_uid' IS NOT NULL
            """
        )
        return {str(r["uid"]) for r in await cur.fetchall()}


async def allocate_veknless_participant(
    user: db.User, discord: dict, stats: Stats
) -> None:
    """A genuinely VEKN-less participant (#216): allocate a real VEKN id and mark it
    push-eligible so batch_push claims it before a future vekn.net assignment can
    collide (#184-class). Must run after the full member pass."""
    existing = await db.get_user_by_uid(user.uid)
    if existing is not None and not existing.deleted_at and existing.vekn_id:
        return
    vekn_id = await db.allocate_next_vekn_id()
    live = msgspec.structs.replace(user, vekn_id=vekn_id, vekn_synced=False)
    await db.save_user(live)
    await ensure_discord_auth(user.uid, discord, stats)
    stats.bump("members.veknless_allocated")


async def resolve_known_remaps(member_uid_map: dict[str, str], stats: Stats) -> None:
    """Point each #216 KNOWN_REMAP source uid at the live account carrying its
    target VEKN id. Run after the full member pass so the lookup is
    order-independent; the source member is never seeded."""
    for old_uid, target_vekn in KNOWN_REMAP.items():
        if old_uid not in member_uid_map:
            continue  # not in this import (e.g. --limit subset)
        live = await live_user_by_vekn_id(target_vekn)
        if live is not None and not live.deleted_at:
            member_uid_map[old_uid] = live.uid
            stats.bump("members.veknless_remapped")
        else:
            loud(
                f"#216 remap target vekn {target_vekn} not live; refs from "
                f"{old_uid} will orphan — verify that account exists"
            )
            stats.bump("warn.remap_target_missing")


async def merge_member(user: db.User, discord: dict, stats: Stats) -> str:
    """Idempotent member upsert keyed on VEKN id. Returns the live uid the caller
    records in `member_uid_map` to remap play-data references.

    Matches on vekn_id, not old-archon uid — matching on uid used to tombstone a
    VEKN-sync-created account that was later claimed, nulling its vekn_id.
    """
    if not user.vekn_id:
        await seed_vekn_less_shell(user, stats)
        return user.uid

    live = await live_user_by_vekn_id(user.vekn_id)
    if live is None:
        # vekn.net hasn't produced this account yet: seed under the old-archon
        # uid. A previous run's seed already holds the vekn_id, so it is found
        # above on the next run — idempotent.
        existing = await db.get_user_by_uid(user.uid)
        if existing is not None:
            if existing.deleted_at:
                stats.bump("members.skipped_deleted")
                return user.uid
            live = existing  # pre-existing under this uid — merge into it
        else:
            await db.save_user(user)
            await ensure_discord_auth(user.uid, discord, stats)
            stats.bump("members.inserted")
            return user.uid

    if live.deleted_at:
        # Deleted on the new stack — never resurrect from upstream.
        stats.bump("members.skipped_deleted")
        return live.uid

    changed = False
    for field in ARCHON_USER_FIELDS:
        if field in live.local_modifications:
            continue
        # coopted_by is written EXCLUSIVELY by remap_coopted_by, once the full
        # member_uid_map is known: an un-remapped old-archon sponsor uid here
        # flip-flops daily against that remap.
        if field == "coopted_by":
            continue
        value = getattr(user, field)
        # Officials' contact_email is injected by the VEKN member sync from the
        # scraped vekn.net lists — writing old archon's address here would
        # flip-flop daily with that injection.
        if field == "contact_email" and live.vekn_id in OFFICIALS_EMAILS:
            continue
        if getattr(live, field) != value:
            setattr(live, field, value)
            changed = True
    if changed:
        live.modified = datetime.now(UTC)
        await db.save_user(live)
        stats.bump("members.updated")
    else:
        stats.bump("members.unchanged")
    if "discord_id" not in live.local_modifications:
        await ensure_discord_auth(live.uid, discord, stats)
    return live.uid


async def migrate_members(
    old: psycopg.AsyncConnection,
    stats: Stats,
    limit: int | None,
    merge: bool,
    coopted_pending: list[tuple[str, str]],
    participant_uids: set[str],
) -> dict[str, str]:
    """members → User (+ AuthMethod rows). Returns `member_uid_map`: old-archon
    member uid → the live uid every downstream reference remaps through. Also
    collects (live_uid, old_sponsor_uid) pairs for the deferred coopted_by remap.
    """
    member_uid_map: dict[str, str] = {}
    veknless_participants: list[tuple[db.User, dict]] = []
    q = "SELECT uid, vekn, data, last_updated FROM members"
    if limit:
        q += f" LIMIT {limit}"
    async with old.cursor(name="members_cur", row_factory=dict_row) as cur:
        cur.itersize = 500
        await cur.execute(q)
        async for row in cur:
            user, discord = build_user(row, stats)
            # #216: allocation deferred to the post-loop pass for a stable id
            # space. A non-participant falls through to the normal path.
            if not user.vekn_id:
                if user.uid in KNOWN_DROP:
                    # unseeded; the lone players-dict ref is stripped at build
                    member_uid_map[user.uid] = user.uid
                    stats.bump("members.veknless_dropped")
                    continue
                if user.uid in KNOWN_REMAP:
                    # placeholder; resolve_known_remaps rewrites it post-loop
                    member_uid_map[user.uid] = user.uid
                    stats.bump("members.veknless_remap_pending")
                    continue
                if user.uid in participant_uids:
                    # allocated under this uid in the post-loop pass
                    member_uid_map[user.uid] = user.uid
                    veknless_participants.append((user, discord))
                    continue
            if merge:
                live_uid = await merge_member(user, discord, stats)
            else:
                await db.save_user(user)
                await ensure_discord_auth(user.uid, discord, stats)
                live_uid = user.uid
            member_uid_map[user.uid] = live_uid
            if user.coopted_by:
                coopted_pending.append((live_uid, user.coopted_by))
            stats.bump("users")
            if stats["users"] % 2000 == 0:
                print(f"  …{stats['users']} users")
    # Post-loop, with the full member set written: the vekn-id space is now stable
    # for allocation, and remap targets are resolvable regardless of import order.
    for puser, pdiscord in veknless_participants:
        await allocate_veknless_participant(puser, pdiscord, stats)
    await resolve_known_remaps(member_uid_map, stats)
    return member_uid_map


async def remap_coopted_by(
    coopted_pending: list[tuple[str, str]],
    member_uid_map: dict[str, str],
    stats: Stats,
) -> None:
    """Set coopted_by to the sponsor's live uid, once member_uid_map is complete.
    Sole writer of coopted_by in this sync — idempotent daily re-runs. An
    unresolved sponsor is never written: legacy refs dangle and rotate uid
    nightly, and chasing them rewrote ~10k users every night."""
    for live_uid, old_sponsor in coopted_pending:
        desired = member_uid_map.get(old_sponsor)
        if desired is None:
            stats.bump("members.coopted_sponsor_unresolved")
            continue
        u = await db.get_user_by_uid(live_uid)
        if u is None or u.deleted_at or "coopted_by" in u.local_modifications:
            continue
        if u.coopted_by == desired:
            continue
        u.coopted_by = desired
        u.modified = datetime.now(UTC)
        await db.save_user(u)
        stats.bump("members.coopted_remapped")


async def migrate_member_deletions(
    old: psycopg.AsyncConnection, live: set[str], stats: Stats, merge: bool
) -> None:
    """member_deletions → soft-deleted User shells. Merge mode also propagates
    deletions of members that exist live on the new stack."""
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


async def migrate_leagues(
    old: psycopg.AsyncConnection,
    stats: Stats,
    merge: bool,
    member_uid_map: dict[str, str],
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
                member_uid_map.get(str(o["uid"]), str(o["uid"]))
                for o in d.get("organizers", [])
                if o.get("uid")
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
    """Build Seats from old seating (scores preserved from source), accumulating
    prelim-only and prelim+finals score sums per player."""
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
    Accumulates tournament-embedded sanctions into `sanctions`."""
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

    # Seat scores are preserved verbatim from old archon. VP/GW/TP are kept
    # split prelim-only (`standings`) vs prelim+finals (`Player.result`) —
    # folding finals into prelim was the old vekn-push bug.
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

    description = d.get("description") or ""
    if d.get("format") == "Draft":
        description = ("[Originally Draft format] " + description).strip()

    league_ref = d.get("league") or {}
    # extra.vekn_id maps onto external_ids["vekn"] so the VEKN tournament sync
    # matches instead of duplicating; the "archon" marker keeps a later run from
    # mistaking its own merge into a vekn-created copy for a both-rich conflict.
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
        start=parse_wall_dt(d.get("start"), d.get("timezone")),
        finish=parse_wall_dt(d.get("finish"), d.get("timezone")),
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
        # Existing new-app code (may be printed as a QR) wins over legacy (never
        # set) over a fresh generate; an empty existing code self-backfills.
        checkin_code=(
            (existing.checkin_code if existing else None)
            or d.get("checkin_code")
            or secrets.token_urlsafe(16)
        ),
        event_code=existing.event_code if existing else "",
        players=players,
        rounds=new_rounds,
        finals=finals,
        winner=winner_uid,
        standings=standings,
        # Migrated events owe new archon no VEKN push — legacy owns and pushes
        # each event until finished there. Stamped on every non-Planned import,
        # the inverse of batch_push's calendar/results gates, so both skip them.
        vekn_pushed_at=(existing.vekn_pushed_at if existing else None)
        or (datetime.now(UTC) if state != TournamentState.PLANNED else None),
    )

    for member_uid, slist in (d.get("sanctions") or {}).items():
        for s in slist:
            if s.get("uid"):
                sanctions[str(s["uid"])] = build_sanction(
                    s, str(member_uid), target_uid, stats
                )

    return t, decks


def _remap_member_refs(
    t: Tournament, decks: list[DeckObject], member_uid_map: dict[str, str]
) -> tuple[Tournament, list[DeckObject]]:
    """Rewrite every member-uid reference the importer builds through
    `member_uid_map`, centralised so none is missed — a missed one silently
    splits a tournament across the old and live uid spaces. The deck *uid*
    (uuid5 of the old player uid) stays stable; only deck.user_uid is remapped."""
    if not member_uid_map:
        return t, decks

    def g(u: str | None) -> str | None:
        return member_uid_map.get(u, u) if u else u

    def remap_seats(seats: list[Seat]) -> list[Seat]:
        return [
            msgspec.structs.replace(
                s, player_uid=g(s.player_uid), judge_uid=g(s.judge_uid)
            )
            for s in seats
        ]

    rounds = [
        [msgspec.structs.replace(tbl, seating=remap_seats(tbl.seating)) for tbl in rd]
        for rd in t.rounds
    ]
    finals = t.finals
    if finals is not None:
        finals = msgspec.structs.replace(
            finals,
            seating=remap_seats(finals.seating),
            seed_order=[g(u) for u in finals.seed_order],
        )
    t = msgspec.structs.replace(
        t,
        winner=g(t.winner),
        organizers_uids=[g(u) for u in t.organizers_uids],
        offline_user_uid=g(t.offline_user_uid),
        players=[msgspec.structs.replace(p, user_uid=g(p.user_uid)) for p in t.players],
        standings=[
            msgspec.structs.replace(s, user_uid=g(s.user_uid)) for s in t.standings
        ],
        rounds=rounds,
        finals=finals,
    )
    decks = [msgspec.structs.replace(d, user_uid=g(d.user_uid)) for d in decks]
    return t, decks


async def carry_league_onto_echo(existing: Tournament, d: dict, stats: Stats) -> None:
    """League membership is archon-only knowledge, so an echo-skip must still
    carry the legacy league ref onto the surviving copy, or it stays
    league-less forever. Idempotent: writes only on an actual change."""
    league_uid = nz((d.get("league") or {}).get("uid"))
    if not league_uid or existing.league_uid == league_uid:
        return
    league = await db.get_league_by_uid(league_uid)
    if league is None or league.deleted_at:
        return
    existing.league_uid = league_uid
    existing.modified = datetime.now(UTC)
    async with db.get_connection() as conn:
        await db.save_tournament(existing, conn=conn)
    stats.bump("tournaments.league_carried_on_echo")


async def process_tournament_row(
    row: dict,
    sanctions: dict[str, Sanction],
    stats: Stats,
    merge: bool,
    uid_map: dict[str, str],
    member_uid_map: dict[str, str] | None = None,
    *,
    archon_ix: dict[str, str],
) -> None:
    """Migrate/merge one old tournament row. Records old_uid → surviving uid in
    `uid_map`, used to remap sanction tournament refs."""
    member_uid_map = member_uid_map or {}
    d = dict(row["data"] or {})
    old_uid = str(row["uid"])
    d["uid"] = old_uid  # build_tournament reads it for the external_ids marker
    # #216: strip VEKN-less orphan participants and the redundant no-show
    # registration a remap would duplicate. Every dropped uid is verified
    # 0-seating, so rounds and standings carry no ref to them.
    players_in = d.get("players") or {}
    drop = {
        k
        for k in players_in
        if k in KNOWN_DROP or (old_uid, k) in KNOWN_DROP_IN_TOURNAMENT
    }
    if drop:
        d["players"] = {k: v for k, v in players_in.items() if k not in drop}
        stats.bump("tournaments.veknless_player_dropped", len(drop))
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
            live_uid = archon_ix.get(old_uid)
            existing = await db.get_tournament_by_uid(live_uid) if live_uid else None
            if existing is not None:
                target_uid = existing.uid
        if (
            existing is not None
            and not d.get("rounds")
            and (existing.rounds or existing.finals)
        ):
            # Echo guard: without this, every nightly merge reverts the rich
            # row's play data + state to legacy's stale round-less copy (wiped
            # 'Open de Coya 2026', vekn 13412, on 2026-08-03).
            uid_map[old_uid] = target_uid
            stats.bump("tournaments.echo_skipped_by_uid")
            await carry_league_onto_echo(existing, d, stats)
            return
        if existing is None and vekn_eid:
            x = await live_tournament_by_vekn(vekn_eid)
            if x is not None:
                incoming_rich = bool(d.get("rounds"))
                if not incoming_rich:
                    # Echo guard: never import old archon's round-less copy
                    # over the vekn.net-synced original.
                    uid_map[old_uid] = x.uid
                    stats.bump("tournaments.echo_skipped")
                    await carry_league_onto_echo(x, d, stats)
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
                # survives (deep links stay valid, no client tombstone).
                target_uid, existing = x.uid, x
        if existing is None and not vekn_eid:
            # No vekn id recorded, so neither key above sees the VEKN-sync copy —
            # source of the #520 duplicate pairs. Fall back to name + start-day.
            x = await live_same_event_tournament(d, old_uid)
            if x is not None:
                incoming_rich = bool(d.get("rounds"))
                if not incoming_rich:
                    uid_map[old_uid] = x.uid
                    stats.bump("tournaments.echo_skipped_by_name")
                    await carry_league_onto_echo(x, d, stats)
                    return
                if x.rounds:
                    loud(
                        f"BOTH-RICH conflict on '{d.get('name')}' {d.get('start')}: "
                        f"ours {x.uid} and old archon {old_uid} both have rounds — "
                        f"one-app-per-event violation, skipped; resolve manually"
                    )
                    uid_map[old_uid] = x.uid
                    stats.bump("tournaments.both_rich_conflict")
                    return
                target_uid, existing = x.uid, x
                stats.bump("tournaments.matched_by_name")

    t, decks = build_tournament(d, target_uid, existing, sanctions, stats)
    # Remap member refs to live uids BEFORE the merge-into-vekn-copy below, so the
    # rich payload and the vekn copy's existing players share one uid space.
    t, decks = _remap_member_refs(t, decks, member_uid_map)
    uid_map[old_uid] = target_uid

    # vekn-linked events: the VEKN sync owns descriptive metadata (writing old
    # archon's values would flip-flop daily against its refresh) — keep it, write
    # play data + archon-only config, and union organizers the same way it does.
    if merge and existing is not None and "vekn" in t.external_ids:
        t = msgspec.structs.replace(
            existing,
            state=t.state,
            league_uid=t.league_uid,
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
    # ETL seed/merge — save_tournament requires a conn; a plain pooled connection
    # (no FOR UPDATE lock) suffices for the offline batch import.
    if merge and existing is not None:
        if same_but_modified(t, existing):
            stats.bump("tournaments.unchanged")
        else:
            t.modified = datetime.now(UTC)
            async with db.get_connection() as conn:
                await db.save_tournament(t, conn=conn)
            stats.bump("tournaments.updated")
    else:
        async with db.get_connection() as conn:
            await db.save_tournament(t, conn=conn)
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
    # interleave creates a second holder — the rich copy wins, the round-less
    # one is tombstoned.
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
    member_uid_map: dict[str, str],
) -> None:
    q = "SELECT uid, data FROM tournaments"
    if limit:
        q += f" LIMIT {limit}"
    archon_ix = await archon_uid_index() if merge else {}
    async with old.cursor(name="tournaments_cur", row_factory=dict_row) as cur:
        cur.itersize = 200
        await cur.execute(q)
        async for row in cur:
            await process_tournament_row(
                row,
                sanctions,
                stats,
                merge,
                uid_map,
                member_uid_map,
                archon_ix=archon_ix,
            )
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
    member_uid_map: dict[str, str],
) -> None:
    for s in sanctions.values():
        # Remap to surviving/live uids: tournament (rich-merge target),
        # sanctioned member, issuing judge.
        if s.tournament_uid:
            s.tournament_uid = uid_map.get(s.tournament_uid, s.tournament_uid)
        s.user_uid = member_uid_map.get(s.user_uid, s.user_uid)
        if s.issued_by_uid:
            s.issued_by_uid = member_uid_map.get(s.issued_by_uid, s.issued_by_uid)
        if merge:
            prev = await db.get_sanction_by_uid(s.uid)
            if prev is not None and same_but_modified(s, prev):
                stats.bump("sanctions.unchanged")
                continue
            if prev is not None:
                s.modified = datetime.now(UTC)
        await db.save_sanction(s)
        stats.bump("sanctions")


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
    # nice/ionice: yield CPU/I/O to the live stacks on the shared VPS.
    subprocess.run(
        ["nice", "-n10", "ionice", "-c3", "pg_dump", "-Fc", "-f", str(path), dsn],
        check=True,
    )
    for stale in sorted(backup_dir.glob("archon_vibe_premerge_*.dump"))[:-7]:
        stale.unlink()
    return path


async def run(args: argparse.Namespace) -> None:
    # Both DSNs get the relaxed guard — without it the #216 participant pre-pass
    # blew the 30s statement_timeout nightly on prod and the merge never ran.
    # make_conninfo, not string concat: --old-dsn/--new-dsn take URI or keyword form.
    relaxed = {"options": f"-c statement_timeout={BATCH_STATEMENT_TIMEOUT_MS}"}
    db.DB_URL = make_conninfo(args.new_dsn, **relaxed)
    os.environ["DATABASE_URL"] = db.DB_URL
    if args.merge and not args.skip_backup:
        path = backup_new_db(args.new_dsn, Path(args.backup_dir))
        print(f"Pre-merge backup: {path}")
    await db.init_db()
    if args.truncate:
        print("Truncating new objects/auth_methods…")
        await truncate_new()

    # read-only source; autocommit=False keeps a transaction open so server-side
    # (named) cursors can DECLARE — we only read, never commit.
    old = await psycopg.AsyncConnection.connect(
        make_conninfo(args.old_dsn, **relaxed), autocommit=False
    )
    stats = Stats()
    sanctions: dict[str, Sanction] = {}
    uid_map: dict[str, str] = {}
    coopted_pending: list[tuple[str, str]] = []
    try:
        print("→ members")
        # #216 pre-pass, unaffected by --limit — a smoke-test classification.
        participant_uids = await collect_tournament_participant_uids(old)
        member_uid_map = await migrate_members(
            old, stats, args.limit, args.merge, coopted_pending, participant_uids
        )
        await remap_coopted_by(coopted_pending, member_uid_map, stats)
        print("→ member_deletions")
        await migrate_member_deletions(old, set(member_uid_map), stats, args.merge)
        print("→ leagues")
        await migrate_leagues(old, stats, args.merge, member_uid_map)
        print("→ tournaments (+ decks, + tournament sanctions)")
        await migrate_tournaments(
            old, sanctions, stats, args.limit, args.merge, uid_map, member_uid_map
        )
        print("→ member sanctions (union by uid)")
        await migrate_member_sanctions(old, sanctions, stats)
        print(f"→ sanctions ({len(sanctions)} distinct)")
        await save_sanctions(sanctions, stats, args.merge, uid_map, member_uid_map)
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
