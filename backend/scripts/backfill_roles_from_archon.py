"""Restore app roles the legacy-archon migration dropped (report, then `--apply`).

The ETL seeds `roles` only on the INSERT path (`migrate_from_archon.build_user`);
merge mode deliberately never writes them ("roles are app-managed post-seed"). So
for every member the VEKN member sync had ALREADY created before the ETL ran, the
legacy role list was silently discarded and the account kept only what
`vekn_sync._derive_role_seeds` could reconstruct: Prince from `princeid`, NC from
`coordinatorid`, IC from the hardcoded ADMINS set, and at most one judge rank from
the ~44-entry JUDGES dict in `backend/src/data/vekn_roster.py` (that dict has since
been removed — the app is the system of record for judge ranks). Everything else
legacy recorded was lost — which is how Portuguese judges came to be missing their
rank in the new app.

UNION ONLY. Roles have been app-managed since the migration, so a replace would
drop grants made in the new app. This script only ever ADDS.

Scope — why only judge ranks by default (measured on prod 2026-08-09):

    role         legacy  new   only-legacy  only-new
    Prince          465  472            27        34
    NC               42   42             2         2
    Judge            35   20            15         0
    Judgekin         70   21            49         0
    Rulemonger        5    5             0         0
    Ethics            1    7             0         6
    IC                6    6             0         0

Two rules decide the scope, and NEITHER is "the sync will fix it" — no sync ever
updates roles (`vekn_sync.py`:578-582), so the new DB's Prince/NC state is itself
just a per-account creation-time snapshot.

  * DIRECTIONALITY. `only-new = 0` for Judge/Judgekin: the new DB is a strict
    SUBSET of legacy, the signature of pure migration loss — nobody has gained a
    judge rank in the new app, so every gap is something we dropped. Prince, NC
    and Ethics diverge in BOTH directions, the signature of two snapshots of a
    moving target plus real in-app management (Ethics 1→7 is entirely
    post-cutover grants). A union can only ADD, so backfilling a bidirectionally
    divergent role monotonically inflates the officials list with people VEKN has
    since replaced.
  * ACCESS. Restore only roles that confer no data-access projection. Judge and
    Judgekin appear in no branch of `access_levels.py` and are absent from
    `routes/users.py`'s `access_roles = {NC, IC}` — a stale judge rank leaks
    nothing. Prince and NC both hit `access_levels.py`:102, which puts them in
    the PUBLIC officials directory with their contact fields (obfuscated to
    anonymous viewers, plain to members): restoring 27 stale Princes would
    publish 27 people's contact details on the strength of an office they no
    longer hold. NC additionally carries FULL country-scoped access and implicit
    organizer rights over every tournament in-country — and the two candidates
    are in Canada and the US, which already have a different, current NC.
    Widening `--roles` to NC manufactures duplicate national coordinators; don't.

Legacy archon was never authoritative for these: Princes are appointed by their NC
(or IC) and NCs by the IC (wiki/access.md), vekn.net's `princeid`/`coordinatorid`
IS the register of those appointments, and legacy held a mirror of it. A mirror
never outranks the register.

Rulemonger and IC match exactly, so no other role has anything to restore.

Judge rank decays on an activity requirement (`reference/judges-guide.md`:579-580
— Judges yearly, Judgekins six-monthly), so some restored ranks will be stale.
Pruning those is a Rulemonger exercise afterwards, not a reason to withhold a
member's rank now.

A user whose `local_modifications` carries "roles" has had their roles edited in
the app since the cutover (`routes/users.py` stamps the marker on every role
write), so a union could resurrect a role someone deliberately revoked. Those
users are reported and SKIPPED, never written. The backfill does
NOT stamp the marker itself: no sync writes roles, so it would have no protective
effect, and keeping it to mean "a human changed this in the app" is what makes it
a trustworthy exclusion signal for any future re-run.

Idempotent: a second run finds no gaps. Writes go through `db.save_user`, so the
public/member/full projections are recomputed byte-identically to runtime. Like
the ETL, writes here are NOT broadcast over SSE (broadcast is in-process in the
backend); clients pick them up on their next catch-up sync — and since the SSE
stream has no lifetime cap, "next" for an always-connected client means the next
backend restart, so prefer running this adjacent to a deploy. No access-version
nudge is owed: that fingerprint covers only `db._OVERLAY_ROLES` (IC/NC), which a
judge rank does not touch.

Two side effects worth knowing. `db.init_db()` executes `schema.sql` against the
target — idempotent DDL, but it takes locks and WILL fail with `LockNotAvailable`
if the backend is mid-write; just re-run. And `--apply` re-pushes Discord Linked
Roles metadata for everyone it writes (see `push_discord`).

    # report only (default)
    OLD_DATABASE_URL=... NEW_DATABASE_URL=... \\
      /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/backfill_roles_from_archon.py

On prod both DSNs are already rendered for the legacy-sync unit. That file is in
systemd's EnvironmentFile format — values are unquoted and CONTAIN SPACES, so
neither `env $(cat …)` nor `source` parses it (both split the DSN and silently
leave you connected to the wrong database). Extract each var whole:

    sudo -u archon bash -c 'E=/etc/archon/archon-legacy-sync.env
      export OLD_DATABASE_URL="$(sed -n "s/^OLD_DATABASE_URL=//p" $E)"
      export NEW_DATABASE_URL="$(sed -n "s/^NEW_DATABASE_URL=//p" $E)"
      exec /opt/archon/backend/.venv/bin/python \\
        /opt/archon/backend/scripts/backfill_roles_from_archon.py --apply'

The Discord push additionally needs DISCORD_CLIENTID / DISCORD_SECRET, which live
in the BACKEND env file — add them the same way when using `--apply` or
`--push-discord`, or the metadata push silently no-ops:

      B=/etc/archon/archon-backend.env
      export DISCORD_CLIENTID="$(sed -n "s/^DISCORD_CLIENTID=//p" $B)"
      export DISCORD_SECRET="$(sed -n "s/^DISCORD_SECRET=//p" $B)"
"""

import argparse
import asyncio
import importlib.util
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import msgspec
import psycopg
from psycopg.conninfo import make_conninfo

try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.src import db  # noqa: E402
from backend.src.models import Role  # noqa: E402

# Must match migrate_from_archon.ROLE_MAP. Inlined rather than imported: legacy
# archon is read-only and being decommissioned, so this mapping is frozen and
# cannot drift — not worth importing a 1700-line module (and its whole vekn_sync
# graph) for nine constant pairs.
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

# Off-request batch job: don't inherit the cluster's 30s USER-REQUEST guard for a
# full-corpus JSONB scan of legacy `members`. Same escape hatch the ETL takes.
BATCH_STATEMENT_TIMEOUT_MS = 600_000

# See the module docstring: judge ranks are the only roles the migration actually
# lost. Overridable with --roles for a deliberate, reviewed widening.
DEFAULT_BACKFILL_ROLES = (Role.JUDGE, Role.JUDGEKIN)

# Stable output/storage order for roles (declaration order of the enum).
ROLE_ORDER = {r: i for i, r in enumerate(Role)}
_ROLE_VALUES = {r.value for r in Role}


async def load_legacy(
    dsn: str,
) -> tuple[dict[str, set[Role]], dict[str, str], set[str]]:
    """VEKN id → mapped legacy roles, plus id → legacy name, plus unmapped role names."""
    conn = await psycopg.AsyncConnection.connect(
        make_conninfo(
            dsn, options=f"-c statement_timeout={BATCH_STATEMENT_TIMEOUT_MS}"
        ),
        autocommit=True,
    )
    try:
        result = await conn.execute(
            """SELECT COALESCE(NULLIF(vekn, ''), data->>'vekn'),
                      COALESCE(data->>'name', ''),
                      COALESCE(data->'roles', '[]'::jsonb)
               FROM members
               WHERE jsonb_array_length(COALESCE(data->'roles', '[]'::jsonb)) > 0"""
        )
        rows = await result.fetchall()
    finally:
        await conn.close()

    roles: dict[str, set[Role]] = {}
    names: dict[str, str] = {}
    unmapped: set[str] = set()
    for vekn, name, raw in rows:
        # Members with no VEKN id were seeded as soft-deleted shells (historical
        # tournaments reference them); they are not live identities to restore.
        if not vekn or not vekn.strip():
            continue
        vekn = vekn.strip()
        mapped = set()
        for r in raw:
            if r in ROLE_MAP:
                mapped.add(ROLE_MAP[r])
            else:
                unmapped.add(r)
        if mapped:
            # Legacy `members` has no unique index on vekn (the new DB does), so
            # union rather than assign — a second row for the same id must not
            # silently drop the first one's roles.
            roles.setdefault(vekn, set()).update(mapped)
            names.setdefault(vekn, name)
    return roles, names, unmapped


async def load_new() -> dict[str, dict]:
    """VEKN id → current state of the live account (one query, not 19k round-trips)."""
    async with db.get_connection() as conn:
        result = await conn.execute(
            """SELECT "full"->>'vekn_id', uid, COALESCE("full"->>'name', ''),
                      COALESCE("full"->'roles', '[]'::jsonb),
                      COALESCE("full"->'local_modifications', '[]'::jsonb),
                      deleted_at IS NOT NULL
               FROM objects
               WHERE type = 'user' AND NULLIF("full"->>'vekn_id', '') IS NOT NULL"""
        )
        rows = await result.fetchall()
    out: dict[str, dict] = {}
    for vekn, uid, name, roles, local_mods, deleted in rows:
        out[vekn] = {
            "uid": uid,
            "name": name,
            "roles": {Role(r) for r in roles if r in _ROLE_VALUES},
            "local_mods": set(local_mods),
            "deleted": deleted,
        }
    return out


def print_census(legacy: dict[str, set[Role]], new: dict[str, dict]) -> None:
    """Every role, both directions — the evidence the scope decision rests on."""
    print("\n=== role census (matched on VEKN id) ===")
    print(
        f"  {'role':<12} {'legacy':>7} {'new':>6} {'only-legacy':>12} {'only-new':>9}"
    )
    for role in Role:
        old = {v for v, rs in legacy.items() if role in rs}
        live = {v for v, u in new.items() if role in u["roles"] and not u["deleted"]}
        if not old and not live:
            continue
        print(
            f"  {role.value:<12} {len(old):>7} {len(live):>6} "
            f"{len(old - live):>12} {len(live - old):>9}"
        )


async def push_discord(uids: list[str]) -> None:
    """Re-push Discord Linked Roles metadata for users whose roles just changed.

    Judge/Judgekin are the only inputs to Discord's `judge` field
    (`roles_hook._JUDGE_LEVELS`), and `routes/users.py` is the only thing that
    normally pushes on a role change — nothing reconciles periodically. Without
    this, a restored judge reads `judge: 0` in Discord until they re-link or a
    Rulemonger re-edits them: the same gap this script exists to close, one
    system over. Sequential and awaited, not create_task — close_db() would kill
    in-flight work. Each call no-ops without a stored token and swallows its own
    errors, so most of these cost one lookup.
    """
    if not uids:
        return
    from backend.src.roles_hook import sync_user_discord_roles

    for uid in uids:
        await sync_user_discord_roles(uid)
    print(f"Discord Linked Roles metadata pushed for {len(uids)} users.")


async def run(args: argparse.Namespace) -> None:
    db.DB_URL = make_conninfo(
        args.new_dsn, options=f"-c statement_timeout={BATCH_STATEMENT_TIMEOUT_MS}"
    )
    await db.init_db()
    try:
        legacy, legacy_names, unmapped = await load_legacy(args.old_dsn)
        new = await load_new()
        print(f"legacy members carrying roles: {len(legacy)}")
        print(f"live accounts with a VEKN id:  {len(new)}")
        if unmapped:
            print(f"⚠ legacy role names with no mapping (ignored): {sorted(unmapped)}")

        print_census(legacy, new)

        in_scope = set(args.roles)
        plan: list[tuple[str, str, str, list[Role], list[Role]]] = []
        skipped_curated: list[tuple[str, str, list[Role]]] = []
        skipped_deleted: list[tuple[str, str, list[Role]]] = []
        unmatched: list[str] = []
        for vekn, want in sorted(legacy.items()):
            live = new.get(vekn)
            if live is None:
                if want & in_scope:
                    unmatched.append(vekn)
                continue
            missing = sorted((want & in_scope) - live["roles"], key=ROLE_ORDER.get)
            if not missing:
                continue
            if live["deleted"]:
                skipped_deleted.append((vekn, live["name"], missing))
                continue
            if "roles" in live["local_mods"]:
                skipped_curated.append((vekn, live["name"], missing))
                continue
            plan.append(
                (
                    vekn,
                    live["uid"],
                    live["name"],
                    sorted(live["roles"], key=ROLE_ORDER.get),
                    missing,
                )
            )

        scope = ", ".join(r.value for r in sorted(in_scope, key=ROLE_ORDER.get))
        print(f"\n=== backfill plan (roles in scope: {scope}) ===")
        for vekn, _uid, name, have, missing in plan:
            add = "+".join(r.value for r in missing)
            print(f"  {vekn:<9} {name:<34} has={[r.value for r in have]} +{add}")
        per_role = {
            r: sum(1 for p in plan if r in p[4])
            for r in sorted(in_scope, key=ROLE_ORDER.get)
        }
        for role, count in per_role.items():
            print(f"  +{role.value}: {count}")
        grants = sum(len(p[4]) for p in plan)
        print(f"  {len(plan)} users, {grants} role grants")

        if skipped_curated:
            print(
                f"\nSKIPPED — roles curated in the app since cutover "
                f"(local_modifications carries 'roles'): {len(skipped_curated)}"
            )
            for vekn, name, missing in skipped_curated:
                print(f"  {vekn:<9} {name:<34} would-add={[r.value for r in missing]}")
        if skipped_deleted:
            print(
                f"\nSKIPPED — account soft-deleted in the new app: {len(skipped_deleted)}"
            )
            for vekn, name, missing in skipped_deleted:
                print(f"  {vekn:<9} {name:<34} would-add={[r.value for r in missing]}")
        if unmatched:
            print(
                f"\nSKIPPED — no live account holds this VEKN id: {len(unmatched)}\n"
                f"  {sorted(unmatched)}"
            )

        if args.push_discord:
            holders = [
                (v, u["uid"])
                for v, u in sorted(new.items())
                if u["roles"] & in_scope and not u["deleted"]
            ]
            print(
                f"\nPushing Discord metadata for {len(holders)} in-scope role holders…"
            )
            await push_discord([uid for _v, uid in holders])
            return

        if not args.apply:
            print("\nDry run — re-run with --apply to write.")
            return
        if not plan:
            print("\nNothing to apply.")
            return

        print(f"\nApplying {grants} grants to {len(plan)} users…")
        written: list[str] = []
        for vekn, uid, name, _have, missing in plan:
            user = await db.get_user_by_uid(uid)
            if user is None:
                print(f"  ⚠ {vekn} {name}: vanished between plan and apply, skipped")
                continue
            merged = sorted(set(user.roles) | set(missing), key=ROLE_ORDER.get)
            await db.save_user(
                msgspec.structs.replace(user, roles=merged, modified=datetime.now(UTC))
            )
            written.append(uid)
        print(f"Applied to {len(written)} users.")
        await push_discord(written)
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Restore app roles dropped by the legacy-archon migration"
    )
    p.add_argument(
        "--old-dsn",
        default=os.getenv("OLD_DATABASE_URL"),
        help="legacy archon DSN (read-only)",
    )
    p.add_argument(
        "--new-dsn",
        default=os.getenv("NEW_DATABASE_URL") or os.getenv("DATABASE_URL"),
        help="archon-vibe DSN",
    )
    p.add_argument(
        "--roles",
        default=",".join(r.value for r in DEFAULT_BACKFILL_ROLES),
        help="comma-separated roles to restore (see the module docstring before widening)",
    )
    p.add_argument(
        "--apply", action="store_true", help="write the plan (default: report only)"
    )
    p.add_argument(
        "--push-discord",
        action="store_true",
        help="write nothing; re-push Discord Linked Roles metadata for every live "
        "holder of a role in --roles (heals grants written before this was wired in)",
    )
    args = p.parse_args()
    if not args.old_dsn or not args.new_dsn:
        p.error(
            "both --old-dsn and --new-dsn (or env OLD_DATABASE_URL / NEW_DATABASE_URL) are required"
        )
    try:
        args.roles = [Role(r.strip()) for r in args.roles.split(",") if r.strip()]
    except ValueError as err:
        p.error(f"{err} — valid roles: {[r.value for r in Role]}")
    if not args.roles:
        p.error("--roles is empty")
    # The docstring explains at length why widening to an access-bearing role is
    # a bad idea; say it again to whoever skipped the docstring.
    risky = {Role.PRINCE, Role.NC, Role.IC} & set(args.roles)
    if risky:
        print(
            f"⚠ {sorted(r.value for r in risky)} confer data access and are excluded by "
            "default — restoring them republishes superseded officials (and duplicate "
            "NCs). Read the module docstring before --apply.",
            file=sys.stderr,
        )
    return args


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
