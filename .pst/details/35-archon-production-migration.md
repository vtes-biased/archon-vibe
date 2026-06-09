# Production migration: archon → archon-vibe (epic #35)

Migrated from `MIGRATION.md` (2026-06-06). **Status: shelved / draft for future execution.**
The production deployment path is ready: the standalone systemd ansible stack (prod inventory + roles + `just *-prod` recipes) was delivered by epics #81/#85 — #37 (its prereq ticket) is closed. Residual execution-time config is folded into Phase 1 (#39).

## Children (phases + gating work)
- **#36** Resolve open questions before Phase 0 (decisions below)
- **#37** ✅ done — ansible systemd-deploy playbook (delivered by #81/#85; residual config → #39)
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
| Formats | Standard, V5, Limited, **Draft** | Standard, V5, Limited (no Draft — ETL maps old `Draft`→`Limited`, see #36) |
| IDs | UUID v4 | UUID v7 (strings). Old v4 UUIDs are valid strings — **keep them** |
| Tournament events log | `tournament_events` table, 366d retention | No equivalent. Dump to cold storage, drop from live DB |
| Access control | Filtered at read time | Pre-computed at write time via `backend/src/access_levels.py` |

---

## Recommended approach: 4-phase rollout, side-by-side domains, single cutover

Run new archon-vibe at a **parallel domain** (`new.archon.vekn.net` or `beta.archon.vekn.net`) during validation phases. Do the authoritative data migration during a short maintenance window, then swap DNS so `archon.vekn.net` points to the new stack. Old stack stays up read-only on `old.archon.vekn.net` for ~30 days as a safety net.

**Why not same-domain blue/green?** Harder with nginx/ansible on a single VPS and two different deployment topologies. Side-by-side domains let users test the new URL pre-cutover and give a trivial rollback (DNS flip back).

**Why not incremental (keep old + new writing to same DB)?** Schemas are incompatible at the write path — old writes flat JSONB, new writes three pre-computed projections and splits decks/sanctions into separate rows. Dual-writing would mean porting half the engine into old archon. Not worth it.

### Data flow: ETL FIRST, then VEKN sync (settled, rehearsed 2026-06-09)

Old archon is a **superset** of vekn.net (it synced from vekn.net and added local data: discord logins, profile edits, and rich tournament rounds/finals/decks for events run in-app). So:

1. **ETL into an empty DB** — produces the complete baseline. Clean insert, no merge logic.
2. **Enable VEKN sync** — reconciles on top using its existing idempotent merge (match by `vekn_id` / `external_ids["vekn"]`, respect `local_modifications`). Running it the other way round would force re-implementing merge semantics inside the ETL.

**Conflict matrix (who wins what):**

| data | winner | mechanism |
|---|---|---|
| member identity (name/country/city/state) | **vekn.net** | sync overwrites (authoritative registry); came from there originally |
| roles | **archon** | ETL marks `local_modifications={"roles"}` so sync can't strip Judge/Ethics/etc |
| contact / nickname / discord_id / community links / coopted_by | **archon** | VEKN sync doesn't manage these fields |
| tournament metadata (name/venue/dates/…) | **vekn.net** | sync refreshes |
| in-app tournament play-data (rounds/finals/standings/players/winner) | **archon** | `vekn_tournament_sync` refreshes metadata only when `rounds`/`finals` present |
| vekn-origin (round-less) tournament results | **vekn.net** | sync is authoritative for those |

**Auth migration:** Discord login carries over (migrate `discord_id` + a discord `AuthMethod`; no token to migrate — OAuth re-auths each session). Legacy passwords do NOT migrate (88-char legacy hash ≠ argon2); email users re-establish via magic-link (keyed on migrated `contact_email`) or Discord.

**Rehearsal result (local, real vekn.net API):** member sync 0 created / 18,669 updated / 0 errors; tournament sync 6 created / 7,546 updated / 0 errors; 0 duplicate vekn_id/event-id, rich rounds preserved (267→267), protected roles intact (109→109), 0 orphans, 30,957 objects decode clean. See `.pst/details/38-etl-phase0.md`.

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
   - **Draft tournaments**: map old `Draft` format → new `Limited` (Draft is a limited format; #36 decided). Optionally prepend an "originally Draft format" note to `description` for provenance. No skip flag needed.
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

### Phase 1 (#39) — Deploy archon-vibe at parallel domain, validate the full ETL→sync path

Stand up the new stack at `new.archon.vekn.net`:
- Deployed via archon-vibe's ansible playbook (systemd-based, no Docker — the standalone prod path: `inventories/prod` + `playbooks/{site,database,deploy}.yml`, `just bootstrap-prod`/`database-prod`/`deploy-prod`). The playbook itself was delivered by epics #81/#85 (#37 closed); only execution-time config remains for this phase:
  - fill the real VEKN-VPS host in `ansible/inventories/prod/hosts.ini` (currently the placeholder `archon-prod.example`)
  - populate `ansible/inventories/prod/group_vars/vault.yml` (db/jwt/mail/discord/vekn secrets)
  - for the parallel domain, override `domain_main` → `new.archon.vekn.net` (group_vars/`--extra-vars`) so nginx_tls + static_site + redirect URIs target the beta host, not prod `archon.vekn.net`
- Fresh PostgreSQL 17 instance (do not share the old DB).
- **Run the ETL from a recent prod dump** (`migrate_from_archon.py`), then **enable VEKN sync** so it reconciles on top — exercise the real Phase-2 ordering and dataset on the VPS. (See the data-flow note below: ETL first, then sync, no wipe.)
- Enable Discord OAuth against a **new** redirect URI (`new.archon.vekn.net/auth/discord`) to avoid colliding with the prod one. Same Discord client ID is fine if you add the second redirect URI.
- Bot process stays **disabled** (or points at a test guild) until Phase 3 to avoid sending real DMs/role updates from two processes.

**Who gets access**: IC + NC only, via an invite/testing flag. Use it to validate UI, performance, and the merged dataset on the real VPS.

**Rollback**: Take `new.archon.vekn.net` offline. Zero impact on prod.

**Exit criteria**: New stack serves real traffic for ≥1 week; no P1 regressions; IC/NC sign-off.

---

### Phase 2 (#40) — Authoritative data migration (maintenance window, ~1–2 hours)

Scheduled downtime window announced ≥1 week in advance (banner on old archon, Discord notice).

**Sequence** (run from a laptop or jump host with access to both DBs):

1. **Freeze old archon**: put old archon in read-only mode (a quick patch that returns 503 on non-GET requests; or stop `archon_web.service` entirely and serve a maintenance page from nginx). Stop its scheduled VEKN sync.
2. **pg_dump old archon**: full logical dump as rollback insurance (`archon_prod_YYYYMMDD.sql.gz`).
3. **Start from an empty new archon-vibe DB** (apply `schema.sql`). No VEKN seeding first — old archon is a superset of vekn.net, so the ETL produces the complete baseline and VEKN sync reconciles afterward.
4. **Run ETL** (`migrate_from_archon.py`): streams all members→users(+auth), leagues, tournaments(+decks, +sanctions). ~45s locally on the full ~19k members / 8.4k tournaments; budget more on the VPS.
5. **ETL integrity checks** (`migrate_validate.py`): counts, orphan scan, prelim-standings invariant, decode round-trip. Exits non-zero on failure.
6. **Enable VEKN sync** (`run_vekn_sync.py` / scheduled): member sync then tournament sync. It MERGES onto the ETL data — matches members by `vekn_id` and tournaments by `external_ids["vekn"]`, refreshes vekn-owned identity/metadata, and **preserves** archon-owned data (roles via `local_modifications`, in-app tournament rounds/finals/standings, discord/contact auth). Then `check_merge.py` to assert no dupes / no wiped play-data / roles intact.
7. **Reconciliation jobs**: rating recompute (rebuilds `CategoryRating` — also the place to verify ratings vs old) + snapshot/projection regen.
8. **Smoke-test new stack**: magic-link login (legacy passwords don't migrate — argon2 vs legacy), Discord login, view a historical + a rich tournament, create+finish a test tournament, sanction lookup.
9. **DNS swap**: `archon.vekn.net` → new stack. Old stack → `old.archon.vekn.net` (read-only).
10. **Watch**: tail logs for 2 hours. Confirm the VEKN sync schedule runs cleanly on the new stack.

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
- **DONE** (#37): ansible systemd deploy stack — `ansible/{inventories/prod,roles,playbooks}`, `just deploy-prod` (built by #81/#85)
- **MODIFY (old repo)**: `/Users/lpanhaleux/Developer/archon/src/archon/app/main.py` — add a read-only middleware flag for Phase 2 freeze
- **REUSE** (read-only, as references for the ETL transformation):
  - `/Users/lpanhaleux/Developer/archon/src/archon/models.py` — source shapes
  - `backend/src/models.py` — target shapes
  - `backend/src/db.py` — `save_object_from_model`, `save_user`, etc.
  - `backend/src/access_levels.py` — projection computation
  - `backend/src/ratings.py` — `recompute_all_ratings`

---

## Resolved decisions (#36 — settled 2026-06-09)

1. **Cutover strategy → parallel domain.** Stand up `new.archon.vekn.net` for IC/NC validation, then DNS-swap `archon.vekn.net` to the new stack; old moves to `old.archon.vekn.net` read-only for ~30d. Rollback = DNS flip.
2. **VPS → same VPS** (no second box). ⚠️ Constraint: Phase 1 runs **both** stacks at once on ~2GB RAM. Mitigation: run the new stack lean during Phase 1 (minimal uvicorn workers, IC/NC-only traffic so load is low); Phase 2 stops/freezes old archon during the window to free RAM for the ETL + reconcile. Watch memory in Phase 1 — if it's too tight, revisit a temporary second box.
3. **Draft tournaments → map `Draft`→`Limited`.** Draft is a limited format, so it imports as a real `Limited` tournament (preserves players/standings/sanctions). Optionally note "originally Draft" in `description`. No `--skip-draft` flag, no cold-backup-only path.
4. **OAuth `clients` → re-register.** Notify each active integration owner to re-register on the new stack; don't port hashed secrets across the incompatible auth scheme. Enumerate active clients from a prod dump in Phase 0 (expected: very few).
5. **`tournament_events` audit log → dump-only.** `pg_dump -t tournament_events` to cold storage, drop from live DB. No viewer in new archon.
6. **Rating formula drift → tolerated.** New Rust engine needn't match old Python bit-for-bit; ratings recompute from tournaments post-ETL anyway. Validation logs per-user deltas and flags any >5% for manual review — does not fail the run. No compatibility mode.
7. **Maintenance-window timing → policy now, date later.** Weekend EU/US off-hours overlap, avoid known VEKN tournament weekends, announce ≥1 week ahead (banner on old archon + Discord). Pin the exact date near execution (gated on #37 ansible + #38 ETL being ready).
8. **Migration order → ETL FIRST, then VEKN sync** (not VEKN-first). Old archon is a superset; ETL gives the complete baseline and VEKN sync reconciles on top via its existing merge. See the "Data flow" section above for the full conflict matrix. Rehearsed end-to-end against the real vekn.net API on 2026-06-09 — passed.
9. **Identity conflict → vekn.net wins** for name/country/city/state; archon wins roles (protected via `local_modifications`) and all fields VEKN doesn't manage (contact/discord/nickname).

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
