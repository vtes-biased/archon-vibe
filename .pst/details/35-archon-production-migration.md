# Production migration: archon → archon-vibe (epic #35)

Migrated from `MIGRATION.md` (2026-06-06). **Status: shelved / draft for future execution.**
Depends on a production-ready deployment path for archon-vibe (see ansible work, ticket #37).

## Children (phases + gating work)
- **#36** Resolve open questions before Phase 0 (decisions below)
- **#37** Prereq: ansible systemd-deploy playbook for the VEKN VPS (blocks Phase 1)
- **#38** Phase 0 — build the ETL + validation harness, dry-run on a prod dump
- **#39** Phase 1 — parallel domain (`new.archon.vekn.net`), VEKN-sync only, IC/NC validation
- **#40** Phase 2 — authoritative migration window + DNS cutover
- **#41** Phase 3 — activate companion features + monitor
- **#42** Phase 4 — decommission old archon

---

## Context

`archon.vekn.net` currently runs the legacy **archon** app (`/Users/lpanhaleux/Developer/archon`): Python FastAPI + PostgreSQL 16, JSONB-everywhere schema (`members`, `tournaments`, `leagues`, `tournament_events`, `clients`, `member_deletions`), Jinja+vanilla-TS frontend, Ansible-deployed to a single Ubuntu VPS.

The rewrite **archon-vibe** (this repo) is ready: Svelte PWA + FastAPI + PostgreSQL 17, Rust/WASM engine, unified `objects` table with pre-computed access-level projections (public/member/full), separate `auth_methods` and OAuth tables, a companion Discord bot process.

Goal: cut over `archon.vekn.net` from old to new, **preserving all member identities, tournament history, leagues, sanctions, and OAuth registrations**, with minimal user-visible downtime. The existing `backend/src/archon_import.py` does **not** help — it imports from legacy Excel files, not from the old database. A purpose-built ETL is required.

---

## Key data-shape diffs (what the ETL must handle)

| Concept | Old | New |
|---|---|---|
| Storage | `members` / `tournaments` / `leagues` / `clients` tables, JSONB `data` | Unified `objects` table, type-discriminated, three access-level JSONB projections |
| Member identity | `Member` row (password, discord, email, sanctions, ratings embedded) | `User` row (contact fields) + one `AuthMethod` row per method + embedded `CategoryRating`s; sanctions become separate `Sanction` rows |
| Tournament | `players: dict[uid→Player]`, `rounds: [Round{tables:[Table{seating:[TableSeat{deck,result,judge}]}]}]`, `sanctions: dict[uid→[Sanction]]`, `finals_seeds: list[uid]` | `players: list[Player]`, `rounds: list[list[Table]]`, `finals: FinalsTable?`, `standings: list[Standing]` precomputed; decks extracted to `DeckObject` rows; sanctions extracted to `Sanction` rows |
| Roles | Admin, Playtester, (rest identical) | `Admin`→`IC`, `Playtester`→`PT`, + new `DEV` |
| Formats | Standard, V5, Limited, **Draft** | Standard, V5, Limited (no Draft) |
| IDs | UUID v4 | UUID v7 (strings). Old v4 UUIDs are valid strings — **keep them** |
| Tournament events log | `tournament_events` table, 366d retention | No equivalent. Dump to cold storage, drop from live DB |
| Access control | Filtered at read time | Pre-computed at write time via `backend/src/access_levels.py` |

---

## Recommended approach: 4-phase rollout, side-by-side domains, single cutover

Run new archon-vibe at a **parallel domain** (`new.archon.vekn.net` or `beta.archon.vekn.net`) during validation phases. Do the authoritative data migration during a short maintenance window, then swap DNS so `archon.vekn.net` points to the new stack. Old stack stays up read-only on `old.archon.vekn.net` for ~30 days as a safety net.

**Why not same-domain blue/green?** Harder with nginx/ansible on a single VPS and two different deployment topologies. Side-by-side domains let users test the new URL pre-cutover and give a trivial rollback (DNS flip back).

**Why not incremental (keep old + new writing to same DB)?** Schemas are incompatible at the write path — old writes flat JSONB, new writes three pre-computed projections and splits decks/sanctions into separate rows. Dual-writing would mean porting half the engine into old archon. Not worth it.

---

### Phase 0 (#38) — Build the ETL, dry-run against prod dump (no deploy)

**Deliverable**: `backend/scripts/migrate_from_archon.py` in archon-vibe.

**What it does** (reads from old archon DB, writes to new archon-vibe DB):
1. **Members → Users + AuthMethods**: stream `SELECT uid, vekn, data FROM members` in batches of 500 (VPS RAM budget). For each row:
   - Build `User` with preserved `uid`, map roles (`Admin`→`IC`, `Playtester`→`PT`), copy `name/country/city/nickname/vekn_id/contact_email/contact_phone`, move `discord.id` to `discord_id`, keep `coopted_by=None` initially.
   - Create `AuthMethod` rows per available method: email/password (if `password_hash`), discord (if `discord.id`), ignore passkeys (new only).
   - Skip embedded ratings — new archon recomputes them from tournaments post-import (see Phase 2 step 6).
2. **member_deletions → soft-deleted User shells** (optional; preserves referential integrity for old tournament records that reference deleted members).
3. **Leagues → League objects**: straightforward field copy, map `ranking`→`standings_mode`, attach `organizers_uids` from old `organizers` list.
4. **Tournaments → Tournament + DeckObject + Sanction**:
   - Reshape `players` dict → list; preserve `user_uid` link.
   - Reshape `rounds`: `[Round{tables:[Table]}]` → `list[list[Table]]`, move `TableSeat.judge` → `Seat.judge_uid`, extract `TableSeat.deck` → separate `DeckObject` row (keyed by tournament+user+round).
   - Extract last round if it's a finals round into `finals: FinalsTable` (build `seed_order` from old `finals_seeds`).
   - Extract `sanctions: dict[uid→[Sanction]]` → individual `Sanction` rows with `user_uid`, `issued_by_uid` (look up judge by vekn/name), `tournament_uid`.
   - **Draft tournaments**: log a warning, import as `Standard` with a note in `description` (or skip — decide based on how many exist; add a CLI flag `--skip-draft`). See decision #36.
   - Populate `standings: list[Standing]` by running the Rust engine's standings computation, or by flattening old embedded standings if available.
   - Compute access-level projections via `access_levels.py` before insert.
5. **clients → OAuthClient**: copy rows, but OAuth 2.0 semantics differ — old `clients` used a different flow. Re-register rather than migrate unless there are active integrations (list them in Phase 0 exploration). See decision #36.
6. **Skip**: `tournament_events` (dump separately as `pg_dump -t tournament_events` to S3/local backup, drop from live).

**Validation harness** (`migrate_validate.py`):
- Run against a `pg_dump` of prod into a local container.
- Assert counts match (members, tournaments, leagues).
- Spot-check 10 random tournaments: player counts, VP totals, winner, finals seats.
- Assert zero orphan references (every `user_uid` in Tournament.players resolves to a User).
- Run new archon-vibe's rating recompute; compare to old archon's stored ratings (expect small deltas from formula refinements — log, don't fail).

**Rollback**: N/A, nothing deployed.

**Exit criteria**: ETL runs end-to-end on a recent prod dump with zero errors, spot-checks pass, rating deltas reviewed.

---

### Phase 1 (#39) — Deploy archon-vibe at parallel domain, empty DB + VEKN sync only

Stand up the new stack at `new.archon.vekn.net`:
- Deployed via archon-vibe's ansible playbook (systemd-based, no Docker in prod — ticket #37).
- Fresh PostgreSQL 17 instance (do not share the old DB).
- Enable `VEKN_SYNC_ENABLED=true` → pulls ~5000 members from VEKN API. Produces a baseline member list we can compare against the ETL output.
- Enable Discord OAuth against a **new** redirect URI (`new.archon.vekn.net/auth/discord`) to avoid colliding with the prod one. Same Discord client ID is fine if you add the second redirect URI.
- Bot process stays **disabled** (or points at a test guild) until Phase 3 to avoid sending real DMs/role updates from two processes.

**Who gets access**: IC + NC only, via an invite/testing flag. Use it to validate UI, performance, VEKN sync output on the real VPS.

**Rollback**: Take `new.archon.vekn.net` offline. Zero impact on prod.

**Exit criteria**: New stack serves real traffic for ≥1 week; no P1 regressions; IC/NC sign-off.

---

### Phase 2 (#40) — Authoritative data migration (maintenance window, ~1–2 hours)

Scheduled downtime window announced ≥1 week in advance (banner on old archon, Discord notice).

**Sequence** (run from a laptop or jump host with access to both DBs):

1. **Freeze old archon**: put old archon in read-only mode (a quick patch that returns 503 on non-GET requests; or stop `archon_web.service` entirely and serve a maintenance page from nginx). Stop its scheduled VEKN sync.
2. **pg_dump old archon**: full logical dump as rollback insurance (`archon_prod_YYYYMMDD.sql.gz`).
3. **Wipe new archon-vibe DB**: the VEKN-seeded data from Phase 1 is discarded — the ETL produces authoritative state.
4. **Run ETL** (`migrate_from_archon.py --old-db ... --new-db ...`): streams all members, leagues, tournaments, sanctions, decks, OAuth clients. Expect 15–45 min on ~5k members and historical tournament set.
5. **Integrity checks**: row counts, random sampling, orphan-reference scan. Script exits non-zero if any check fails.
6. **Trigger reconciliation jobs** in new archon-vibe:
   - `run_rating_recompute()` — rebuilds `CategoryRating` embedded in users
   - `generate_snapshots()` — rebuilds access-level projections
   - VEKN sync (pulls any fresh members not in old archon)
7. **Smoke-test new stack**: login with email, login with Discord, view a historical tournament, create+finish a test tournament, sanction lookup.
8. **DNS swap**: `archon.vekn.net` → new stack's IP/container. Old stack moves to `old.archon.vekn.net` (read-only).
9. **Watch**: tail logs for 2 hours. Confirm VEKN sync schedule runs on the new stack.

**Rollback at step 8**: DNS flip back to old stack, remove new-stack from DNS. Old data is untouched (we only read from it). Users lose at most the downtime window.

**Rollback after step 8**: still possible for ~30 days by restoring the Phase 2 pg_dump to old archon and flipping DNS. Any writes to new stack during that period would be lost — communicate this risk if rollback is invoked.

**Exit criteria**: DNS swap complete, 24h elapsed with no rollback.

---

### Phase 3 (#41) — Activate companion features + monitor (2–4 weeks)

Post-cutover work, shipped as incremental versions of archon-vibe:
- **Enable Discord bot** pointed at prod Discord client, production guild(s). Subscribes to SSE, manages tournament voice channels, Linked Roles metadata push.
- **Enable TWDA import + push** if desired.
- **Enable `VEKN_PUSH=true`** scheduled job to publish newly-finished tournaments back to VEKN.
- **Passkey registration**: users can add passkeys (new capability — no migration needed, opt-in).
- **Session migration handling**: users logged in via old archon cookies won't carry over. Add a friendly "please log in again" banner for the first 7 days.
- **Monitor**: error rates, SSE reconnect storms, IndexedDB hydration times (esp. for organizers with large tournament history).

**Rollback**: per-feature feature flags (env vars) so each can be disabled without redeploy.

**Exit criteria**: 30 days stable, <1 P2 bug/week, IC approval.

---

### Phase 4 (#42) — Decommission old archon

- Final `pg_dump` of old archon (archive indefinitely — this is the history of record).
- Stop `archon_web.service`, remove from ansible inventory.
- Remove `old.archon.vekn.net` DNS + nginx vhost.
- Archive `/Users/lpanhaleux/Developer/archon` repo as read-only.
- Move `tournament_events` dump to cold storage.

---

## Critical files to create / modify

- **NEW**: `backend/scripts/migrate_from_archon.py` — the ETL, connects to both DBs, streams in batches
- **NEW**: `backend/scripts/migrate_validate.py` — post-ETL integrity checks
- **PREREQ** (#37): ansible playbook to deploy archon-vibe via systemd on the VEKN VPS
- **MODIFY (old repo)**: `/Users/lpanhaleux/Developer/archon/src/archon/app/main.py` — add a read-only middleware flag for Phase 2 freeze
- **REUSE** (read-only, as references for the ETL transformation):
  - `/Users/lpanhaleux/Developer/archon/src/archon/models.py` — source shapes
  - `backend/src/models.py` — target shapes
  - `backend/src/db.py` — `save_object_from_model`, `save_user`, etc.
  - `backend/src/access_levels.py` — projection computation
  - `backend/src/ratings.py` — `recompute_all_ratings`

---

## Open questions (#36 — decide before Phase 0)

1. **Same-domain cutover vs parallel domains?** Recommended: parallel (`new.archon.vekn.net`) until Phase 2, then DNS swap.
2. **Same VPS or new?** New archon-vibe on the same VPS is doable (~2GB RAM tight but feasible if old is stopped during Phase 2). Alternative: provision a second VPS and avoid any resource contention.
3. **Draft tournaments**: how many exist in prod? Strategy: import as `Standard` with description note, OR skip (and deliver them via `tournament_events` cold backup).
4. **OAuth `clients` table**: how many active integrations? Recommended: re-register (notify each client owner) rather than attempt to port hashed secrets across different auth schemes.
5. **`tournament_events` audit log**: keep as dump-only, or build a viewer in new archon? Recommended: dump-only, archive.
6. **Rating formula drift**: new archon's Rust engine may produce slightly different rating numbers than old archon's Python engine. Acceptable, or do we need a compatibility mode?
7. **Maintenance window timing**: when (day, timezone)? Recommend a weekend US/EU overlap off-hours, avoiding known VEKN tournament weekends.

---

## Verification checklist (before Phase 2 — full prod dump)

- [ ] `migrate_from_archon.py` runs clean on full prod dump
- [ ] Member count matches (±deletions)
- [ ] Tournament count matches exactly
- [ ] Random 10 tournaments: players, rounds, VPs, winner, finals all verified manually
- [ ] Every `Tournament.players[*].user_uid` resolves to a live User (no orphans)
- [ ] Every `Sanction.user_uid` and `issued_by_uid` resolves
- [ ] Ratings recomputed, deltas vs old ≤ 5% per user (document outliers)
- [ ] Access-level projections generated for every object
- [ ] Old-archon Discord-linked user can log in to new archon via Discord OAuth
- [ ] Old-archon email-password user can log in via email
- [ ] VEKN scheduled sync runs cleanly on new stack after ETL
- [ ] Bot disabled during Phases 0–2, enabled cleanly in Phase 3
- [ ] `old.archon.vekn.net` serves old data read-only for 30 days post-cutover
