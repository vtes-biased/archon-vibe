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

  Members are matched on **VEKN id** (the stable cross-system key), NOT on the
  old-archon uid — which diverges whenever the live account was VEKN-sync-created
  (fresh uuid7) and then claimed. The merge merges archon-owned fields into that
  live account and NEVER tombstones it (matching on uid used to detach claimed
  accounts); every play-data reference to an old-archon member uid is
  remapped to the live uid via `member_uid_map`. Members with no VEKN id are
  seeded as soft-deleted shells (historical tournaments reference them; they
  aren't live identities). This is what makes the prod migration **sync-first**
  (VEKN sync creates the accounts, the merge layers history on) instead of
  ETL-first — see `.pst/details/35` / `169`.

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

# Make `backend.src` importable from a source checkout (local `uv run`). On the
# deployed box it's already installed in the venv, so skip the insert there —
# adding the repo root could otherwise let a stray src/ shadow the wheel package.
try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from uuid import uuid7

import msgspec
import psycopg
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
# #216 — VEKN-less legacy tournament-participant fixups                         #
#                                                                              #
# Old archon's Register never enforced vekn_id, so a handful of players landed #
# in finished tournaments with no VEKN id; the new engine's VeknIdRequired     #
# blocks new ones, so this set is fully bounded by the prod dump. The rule: a   #
# VEKN-less player with NO round seating is a registration artifact → drop; one #
# who actually played must be resolved (match a real account → remap, else      #
# allocate a real id + push). Keyed by opaque old-archon uid only (no           #
# names/emails — the per-case detail lives in                                   #
# .pst/details/216-veknless-tournament-participants.md).                        #
# --------------------------------------------------------------------------- #

# old-archon member uid → the real VEKN id its tournament refs remap onto (the
# played throwaway of a member who already holds that VEKN account; resolved to
# the live account by resolve_known_remaps after the full member pass).
KNOWN_REMAP: dict[str, str] = {
    "06194fea-a366-4d28-a89c-eb2ead795d65": "3390002",
}

# VEKN-less member uids dropped wholesale: registration artifacts with 0 seating,
# each in a single tournament. Never seeded; their lone players-dict entry is
# stripped from the tournament at build time (no seating/standings ref to fix).
KNOWN_DROP: frozenset[str] = frozenset(
    {
        "021937b2-a40a-415d-a021-6ff3fe7da4a3",  # Neonate Revolution registrant, 0 rounds
        "19656201-a2fb-4925-93d6-c9e47eba1c28",  # funeral-wake phantom (organiser-entered dup)
    }
)

# (tournament_uid, member_uid) entries dropped from ONE tournament's players dict
# only. Here: the real account's redundant 0-round no-show registration in the
# funeral wake — the person actually played under the VEKN-less throwaway that
# KNOWN_REMAP folds onto this same account, so keeping it would duplicate the
# remapped entry. That member is a real, active player in OTHER events, so the
# drop must be tournament-scoped, never a wholesale KNOWN_DROP.
KNOWN_DROP_IN_TOURNAMENT: frozenset[tuple[str, str]] = frozenset(
    {
        (
            "51aa6745-d409-42e8-8a8b-a8a214530bf6",
            "d9ca427b-c31a-4b22-a649-d32a6e622dd3",
        ),
    }
)


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


async def seed_vekn_less_shell(user: db.User, stats: Stats) -> None:
    """A legacy member with no VEKN id: seed a soft-deleted shell under its old
    uid so historical tournament/sanction references to it resolve, WITHOUT
    creating a live identity (it isn't on vekn.net and can't be claimed). Mirrors
    the member_deletions shells. Never resurrects or modifies an existing row."""
    if await db.get_user_by_uid(user.uid) is not None:
        return
    now = datetime.now(UTC)
    await db.save_user(msgspec.structs.replace(user, deleted_at=now, modified=now))
    stats.bump("members.vekn_less_shell")


async def collect_tournament_participant_uids(old: psycopg.AsyncConnection) -> set[str]:
    """Member uids referenced as tournament participants (players-dict keys ∪
    round-seating player_uid). #216 uses it to tell a VEKN-less member that
    ACTUALLY played (→ allocate a real id + push) from a non-participant
    (→ soft-deleted shell). One server-side DISTINCT scan; ~11k uids for prod
    (a few hundred KB — within the VPS budget)."""
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
    """A genuinely VEKN-less legacy tournament participant (#216): allocate a real
    VEKN id, create a LIVE member under the old-archon uid, and mark it
    push-eligible (vekn_synced=False) so batch_push registers the id on vekn.net —
    claiming the gap-filled id so a future vekn.net assignment of it can't collide
    (#184-class). Called AFTER the full member pass so allocate_next_vekn_id sees
    the complete vekn-id space (mid-pass the first gap may be a not-yet-imported
    member). Idempotent: a live VEKN-bearing row from a prior run is reused; a
    leftover #169 soft-deleted shell under this uid is resurrected into it."""
    existing = await db.get_user_by_uid(user.uid)
    if existing is not None and not existing.deleted_at and existing.vekn_id:
        return
    vekn_id = await db.allocate_next_vekn_id()
    live = msgspec.structs.replace(user, vekn_id=vekn_id, vekn_synced=False)
    await db.save_user(live)
    await ensure_discord_auth(user.uid, discord, stats)
    stats.bump("members.veknless_allocated")


async def resolve_known_remaps(member_uid_map: dict[str, str], stats: Stats) -> None:
    """Point each #216 KNOWN_REMAP source uid at the LIVE account carrying its
    target VEKN id. Run after the full member pass so the lookup is
    order-independent (the real account may be imported/VEKN-synced in the same
    run). The source member is never seeded; its tournament refs flow through this
    remap instead."""
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
    """Idempotent member upsert keyed on VEKN id. Returns the LIVE uid this
    old-archon member maps to (the caller records old_uid → live_uid in
    `member_uid_map` and remaps every play-data reference through it).

    The VEKN id is the stable cross-system identity key, so we match on it rather
    than on the old-archon uid — which diverges whenever the live account was
    created by the VEKN sync (fresh uuid7) and then claimed. Matching on uid here
    used to tombstone such a claimed account and null its vekn_id (silent data
    loss); this never tombstones a live account.

    - no vekn_id        → soft-deleted shell (refs resolve; not a live identity)
    - vekn_id matches a live account → merge archon-owned fields into it
      (respecting local_modifications); identity / vekn_id / roles untouched
    - vekn_id unknown here → seed-insert under the old-archon uid
    """
    if not user.vekn_id:
        await seed_vekn_less_shell(user, stats)
        return user.uid

    live = await live_user_by_vekn_id(user.vekn_id)
    if live is None:
        # vekn.net hasn't produced this account yet (VEKN sync didn't create it,
        # or this is a vekn-sync-less env): seed under the old-archon uid. A
        # previous run's seed already holds the vekn_id, so it is found above on
        # the next run — idempotent.
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
        # coopted_by is a member→member reference written EXCLUSIVELY by
        # remap_coopted_by, once the full member_uid_map is known: writing the
        # un-remapped old-archon sponsor uid here would flip-flop daily against
        # that remap (the live account already holds the remapped uid).
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
    member uid → the LIVE uid it maps to (identity in ETL mode where uids are
    preserved; the vekn-matched live account in merge mode). Every downstream
    member-uid reference is remapped through this map. Also collects
    (live_uid, old_sponsor_uid) pairs for the deferred coopted_by remap.

    `participant_uids` is the set of member uids any tournament references (#216):
    a VEKN-less member in it that actually played is allocated a real id, a
    VEKN-less non-participant stays a shell."""
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
            # #216 VEKN-less legacy tournament-participant fixups (both modes;
            # allocation deferred to the post-loop pass below for a stable id
            # space). A non-participant VEKN-less member falls through to the
            # normal path (merge: shell; ETL: live row, as before).
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
    """Set coopted_by to the sponsor's LIVE uid, once the full member_uid_map is
    known (coopted_by is a member→member reference, so the sponsor may be unseen
    when the member is written, and the merge loop deliberately skips the field).
    This is the SOLE writer of coopted_by in this sync: it writes the remapped
    value directly and idempotently, so daily re-runs are a no-op (writing the
    un-remapped old uid in the merge loop instead would flip-flop against this).
    A local edit wins; the ETL identity map writes the unchanged uid (no-op)."""
    for live_uid, old_sponsor in coopted_pending:
        desired = member_uid_map.get(old_sponsor, old_sponsor)
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
        # Carry forward the existing new-app code (organizers may have printed the
        # QR) → legacy code (never set — new-app concept) → generate. An empty
        # existing code (previously-migrated under the old `or ""`) is falsy, so
        # the next nightly run self-backfills it with a stable random code.
        checkin_code=(
            (existing.checkin_code if existing else None)
            or d.get("checkin_code")
            or secrets.token_urlsafe(16)
        ),
        players=players,
        rounds=new_rounds,
        finals=finals,
        winner=winner_uid,
        standings=standings,
        # Migrated events owe new archon no VEKN push. Under one-app-per-event
        # legacy owns each event until it's finished there; legacy pushes it
        # and the daily --merge then carries the vekn id + results + this
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


def _remap_member_refs(
    t: Tournament, decks: list[DeckObject], member_uid_map: dict[str, str]
) -> tuple[Tournament, list[DeckObject]]:
    """Rewrite every member-uid reference the importer BUILDS — players, winner,
    rounds+finals seating (player_uid + judge_uid), finals.seed_order, standings,
    organizers_uids, offline_user_uid, deck.user_uid — through `member_uid_map`
    (old-archon uid → live uid). Centralised so no ref field is missed: a missed
    one silently splits a tournament across the old and live uid spaces (the live
    account's players came from the VEKN sync as uuid7, the rich rounds carry old
    uids) — and the cross-object orphan scan can't catch it. (ScoreOverride.judge_uid
    and RaffleDraw.winners are also member refs but the importer never builds them,
    so they stay empty and need no remap.) Empty map (ETL identity) → no-op. The
    deck *uid* (uuid5 of the old player uid) is intentionally left stable across
    modes; only deck.user_uid is remapped."""
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


async def process_tournament_row(
    row: dict,
    sanctions: dict[str, Sanction],
    stats: Stats,
    merge: bool,
    uid_map: dict[str, str],
    member_uid_map: dict[str, str] | None = None,
) -> None:
    """Migrate/merge one old tournament row. Records old_uid → surviving uid in
    `uid_map` (used to remap sanction tournament refs); remaps every member-uid
    in the rich payload through `member_uid_map` (old member uid → live uid)."""
    member_uid_map = member_uid_map or {}
    d = dict(row["data"] or {})
    old_uid = str(row["uid"])
    d["uid"] = old_uid  # build_tournament reads it for the external_ids marker
    # #216: strip VEKN-less orphan participants (registration artifacts, no
    # seating) and a real account's redundant no-show registration that a remap
    # would otherwise duplicate. Every dropped uid is verified 0-seating, so only
    # the players dict needs editing — rounds/standings carry no ref to them.
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
    # Remap member refs to live uids BEFORE the merge-into-vekn-copy below, so the
    # rich payload and the vekn copy's existing players share one uid space.
    t, decks = _remap_member_refs(t, decks, member_uid_map)
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
    member_uid_map: dict[str, str],
) -> None:
    q = "SELECT uid, data FROM tournaments"
    if limit:
        q += f" LIMIT {limit}"
    async with old.cursor(name="tournaments_cur", row_factory=dict_row) as cur:
        cur.itersize = 200
        await cur.execute(q)
        async for row in cur:
            await process_tournament_row(
                row, sanctions, stats, merge, uid_map, member_uid_map
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
        # Remap tournament refs to the surviving uid for events whose rich
        # payload merged into a vekn-created copy, and the sanctioned member +
        # issuing judge to their live uids (old-archon uid → live).
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
    # nice/ionice: yield CPU/I/O to the live stacks on the shared VPS.
    subprocess.run(
        ["nice", "-n10", "ionice", "-c3", "pg_dump", "-Fc", "-f", str(path), dsn],
        check=True,
    )
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
    coopted_pending: list[tuple[str, str]] = []
    try:
        print("→ members")
        # #216 pre-pass: which member uids any tournament references, so a
        # VEKN-less member who actually played is allocated a real id rather than
        # shelled. Full scan, unaffected by --limit (a smoke-test classification).
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
