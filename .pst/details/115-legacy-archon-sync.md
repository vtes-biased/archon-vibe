# Legacy-archon daily sync (#115)

Rework `backend/scripts/migrate_from_archon.py` from insert-only ETL into an
**idempotent merge** run daily on the new stack during the parallel run (#39).
Old archon becomes a temporary second upstream, peer of the VEKN sync, until
decommission (#42). There is **no Phase-2 wipe**: cutover (#40) is just a freeze +
final sync + vhost swap. Keep the clean-insert mode for beta rebuilds (#91) and
as a disaster fallback.

Decided with owner 2026-06-10. Supersedes the wipe+re-ETL design in `#35`
(decision 8 there covers the *initial* population only).

> **Amendment 2026-06-14 (#169, principal-engineer-reviewed) — member matching
> by VEKN ID + sync-first prod.** Two coupled changes supersede parts of the
> design below:
> 1. **Match members by `vekn_id`, not by uid.** The uid-match (`get_user_by_uid`,
>    `merge_member`) + its "vekn-first echo" tombstone branch caused **silent
>    data loss**: a user who CLAIMED a VEKN-sync identity copy holds a uuid7 ≠ the
>    old-archon uid, so the lookup missed and the branch tombstoned the live
>    claimed account + nulled its `vekn_id` (losing auth, community_links, local
>    edits). Replaced by: match on `vekn_id`; merge archon-owned fields into the
>    live account; **never tombstone**; build `member_uid_map[old_uid]→live_uid`
>    and remap *every* member-uid reference through it. Vekn-less legacy members
>    are **seeded as soft-deleted shells** (NOT dropped — the dump has 9 tournament
>    refs to vekn-less members in 3 rich events; bare-drop orphans them). Full
>    spec + the complete reference-field enumeration: `.pst/details/169-*.md`.
> 2. **Prod is sync-first** (was ETL-first). The remap makes uid-preservation
>    moot, so prod runs the same path as the #91 beta. ETL `--truncate` → DR/
>    dev-seed. See the SYNC-FIRST paragraph in `.pst/details/35-*.md`. The two are
>    coupled: sync-first makes the remap load-bearing.
>
> The "single writer per field" and tournament-matching design below still holds;
> only the *member*-matching key (uid → vekn_id) and the vekn-less handling change.

## Why this is cheap here

- The ETL preserves uids → re-running is an upsert problem, not a re-keying one.
- The user-conflict contract already exists: profile/role edits on the new stack
  record fields in `local_modifications` (`routes/users.py:188-262`, roles at
  `:226`), and the VEKN sync merge already skips those field-by-field
  (`vekn_sync.py:662`). This sync becomes the second consumer of that contract.
- The rich-data guard already exists: `vekn_tournament_sync.py:332` refuses to
  touch rounds/finals/standings/players/winner/state when rounds are present.
- Same box: read `archondb` over the local unix socket.

## Single writer per field (prevents daily flip-flop between the two syncs)

| data | writer | notes |
|---|---|---|
| member identity (name/country/city/state) | VEKN sync | old-archon identity edits reach us *through* vekn.net (old pushes members there); this sync never writes identity |
| contact / nickname / discord_id / community links / coopted_by | archon sync | vekn doesn't manage these |
| **roles** | **nobody** | seeded once by the ETL; app-managed thereafter. Mechanics below. |
| sanctions, leagues | archon sync | upsert by source uid |
| rich play data (rounds/seatings/decks/finals) | archon sync | for events held on old archon |
| round-less ratified results, calendar metadata | VEKN sync | unchanged from today |
| `local_modifications` fields | nobody | local edits trump both syncs, permanently |

## Roles (owner-confirmed model, 2026-06-10: seed once, then app-managed only)

- **Seed**: the initial population (ETL, old archon first) imports old-archon
  roles (mapped `Admin`→`IC`, `Playtester`→`PT`). With the prod DB ETL-populated,
  that is in practice the one time roles are written by anything other than the
  new app — but the seed clause extends to *whichever sync first imports a
  member* (see the amendment below).
- **From then on, no sync ever UPDATES roles.** The VEKN member sync's role
  overwrite on update (Prince/NC/IC inference + `JUDGES` map applied via
  `_update_user`) stops being applied — permanently, not behind an era flag, so
  beta and prod behave identically by construction. This (recurring archon)
  sync excludes roles from its field set.
- **Amendment (#134, 2026-06-10)**: the original cut removed the VEKN member
  sync's derivation *outright*, which left any environment populated without
  the legacy DB (dev after `dev-reset`, a post-decommission rebuild) with zero
  roles and a locked-out role-edit API (it needs an IC caller). Restored as a
  **create-path-only seed** (`_derive_role_seeds` + restored
  `data/vekn_roster.py`): when the member sync *creates* a user it seeds
  Prince/NC from `princeid`/`coordinatorid` and IC from the static roster
  (the judge-rank half of that roster was later removed — app-managed, nothing
  upstream to derive from) — symmetric with this merge sync's own "or on first
  merge insert"
  clause. `_update_user` remains role-free, so ETL-seeded and app-granted roles
  are never touched. In prod the ETL runs first, so the roster effectively only
  matters where this sync is the sole importer.
- Consequences (accepted): role changes made on old archon during the parallel
  run do NOT propagate — role management moves to the new app at Phase-1 start
  (mirror manually on old archon only if needed for its own authz during the
  window). Post-seed appointments on vekn.net's lists likewise need an in-app
  grant; archon is the authoritative point for archon behavior.
- The ETL needs no `local_modifications={"roles"}` trick (nothing to protect
  against anymore); in-app role edits still record it, harmlessly.

## Tournament matching (the vekn-first / archon-first question)

An event held on old archon typically reaches the new stack **twice**: first as a
round-less copy created by the VEKN sync (fresh uid, `external_ids.vekn=E`), later
as the rich version from this sync (old archon's uid, same `E` via `extra.vekn_id`).

Algorithm, per old-archon tournament:
1. Match by **uid** (already merged before, or ETL-imported) → idempotent update.
2. Else match by **`external_ids.vekn`** → merge the rich payload **INTO the
   existing (vekn-created) object**, keeping its uid: rounds/finals/players
   (user uids are ETL-preserved), extracted decks keyed on the surviving uid,
   sanctions re-keyed to it. Keeps deep links and avoids client tombstones; the
   next VEKN sync run hits the rich-guard and refreshes metadata only.
3. Else **insert** under old archon's uid (event vekn doesn't know yet).

Invariant: **at most one live tournament per vekn event id.** The archon-first
interleave can produce two holders (this sync inserts rich pre-push, VEKN sync
later creates a round-less copy before the rich one has gained `E`): on conflict
the rich copy survives, the round-less one is soft-deleted (tombstone flows to
clients via SSE). Both-rich = someone broke the one-app-per-event rule: log
loudly, skip, resolve manually.

Echo guard for the reverse direction: events held on **new** archon come back from
old archon as round-less copies (old synced them from vekn) — step 2 + rich-wins
means we never import the pale copy over the rich original.

## Idempotence details

- Decks: deterministic identity by (tournament, user, round) — replace-by-key,
  never blind insert.
- Sanctions: keyed by old archon's sanction uid.
- `member_deletions` → soft-delete propagation.
- Push stamping (#114) applied here too: events merged rich from old archon were
  pushed *by* old archon → stamp `vekn_pushed_at`; imported users get
  `vekn_synced=True`.
- Pre-run `pg_dump` of the **new** DB → recovery for a buggy merge is
  restore-fix-rerun.
- Ratings recompute stays a separate step (cheap enough post-run or at #40).

## Open implementation choices

- Runner: systemd timer invoking the script vs in-app scheduled job like the VEKN
  sync (env: legacy DB DSN + enable flag). Script + timer keeps the backend free
  of legacy-schema knowledge.
- Observability: owner explicitly wants **no automation/reporting** — officials
  are the live testers. Standard logs (journald) only; the both-rich conflict and
  soft-delete dedups must be loud in those logs.
- Needs principal-engineer review when implemented (sync semantics, SSE/IDB
  tombstone behavior).

## REOPENED 2026-06-30 — runner/deploy never built (blocks C-3 + E-1)
The merge *logic* shipped, but nothing runs it on prod. Found during the Phase-1
bring-up — new stack live + seeded (18,855 users) but the merge un-runnable:
- `backend/scripts/migrate_from_archon.py` is **not on the box** — the wheel deploy
  doesn't ship `backend/scripts/`.
- The script imports `from src import db` / `from src.models import …`, but the
  wheel installs the package as **`backend`** (entrypoint `backend.src.main:app`);
  `import src.db` → ModuleNotFoundError against the deployed venv. Imports must
  become `backend.src.…` (or run from a source checkout — but the box has none and
  a fresh uv build can't compile the Rust engine).
- No `OLD_DATABASE_URL` in the backend env; no systemd timer / in-app job (runner
  was left "timer vs in-app" — never decided/built).
To do: (1) make the script wheel-import-compatible; (2) ship it via ansible (run
with the deployed venv that already has the engine wheel); (3) wire `OLD_DATABASE_URL`
(legacy `archon` cred) + a runner — manual path for the C-3 seed, timer/in-app for
the E-1 daily. Cutover gate already met (18,855 ≥ ~18k; legacy archondb 19,034).

### DONE 2026-06-30 — runner built (script + `legacy_sync` ansible role)
(1) script imports `src.`→`backend.src.` + find_spec-guarded path hack (loads on
the wheel venv); (2) new `roles/legacy_sync` ships the script to
`/opt/archon/backend/scripts/`, renders `/etc/archon/archon-legacy-sync.env`
(keyword conninfo, escaped pw), installs a oneshot service + daily 04:00 timer
running it with the deployed venv, capped (OOMScoreAdjust/MemoryMax) so a runaway
merge dies instead of OOM-killing the shared postgres/legacy; (3) wired into
`deploy.yml` gated by `legacy_sync_enabled`; prod vars only — no legacy secret
needed: OLD (`archondb`) connects via **peer auth** (unit runs as OS `archon` →
PG role `archon`; verified reads 19,034 rows), NEW writes as `archonvibe` (scram,
existing `vault_db_password`). Principal-engineer reviewed (no blockers; the
memory caps were the key add; peer-for-OLD found in pre-flight, dropped the secret).
### CLOSED 2026-07-02 — unattended-merge count guard DROPPED (owner decision)
The proposed in-script guard (abort the merge if the new DB's vekn-account count
is implausibly low) is not worth building: prod is live and seeded above 18k
accounts and won't regress below it, and the whole legacy sync is decommissioned
with the end of the parallel run (#42). The ~18k check stays what it was — a
one-time manual cutover pre-flight, already satisfied.
