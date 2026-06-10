# Legacy-archon daily sync (#115)

Rework `backend/scripts/migrate_from_archon.py` from insert-only ETL into an
**idempotent merge** run daily on the new stack during the parallel run (#39).
Old archon becomes a temporary second upstream, peer of the VEKN sync, until
decommission (#42). There is **no Phase-2 wipe**: cutover (#40) is just a freeze +
final sync + vhost swap. Keep the clean-insert mode for beta rebuilds (#91) and
as a disaster fallback.

Decided with owner 2026-06-10. Supersedes the wipe+re-ETL design in `#35`
(decision 8 there covers the *initial* population only, which stays ETL-first).

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
  roles (mapped `Admin`→`IC`, `Playtester`→`PT`). That is the one and only time
  roles are written by anything other than the new app.
- **From then on, no sync ever writes roles.** The VEKN member sync's role
  derivation/overwrite (Prince/NC/IC inference + `JUDGES` map,
  `vekn_sync.py:557-584,702`) stops being applied — permanently, not behind an
  era flag, so beta and prod behave identically by construction. This (recurring
  archon) sync excludes roles from its field set.
- Consequences (accepted): role changes made on old archon during the parallel
  run do NOT propagate — role management moves to the new app at Phase-1 start
  (mirror manually on old archon only if needed for its own authz during the
  window). Post-seed appointments on vekn.net's lists likewise need an in-app
  grant; archon is the authoritative point for archon behavior.
- The ETL needs no `local_modifications={"roles"}` trick (nothing to protect
  against anymore); in-app role edits still record it, harmlessly. The old
  vekn-sync role code becomes dead and should be removed with this work.

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
