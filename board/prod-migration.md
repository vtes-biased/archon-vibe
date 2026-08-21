> Elaborated context for **two** lines in `BOARD.md` — the post-flip steps and
> the legacy-archon decommission. Deleted with the later of the two.
> `#N` below is a **retired tracker number**, not a GitHub issue and not a live
> pointer — the surrounding prose carries the fact. A real GitHub issue is
> written `gh-N`.

# Production migration: archon → archon-vibe (epic #35)

**Status: active.** Strategy revised 2026-06-10 (owner discussion): **no wipe, no
big-bang migration window**. The new stack runs **two daily syncs** during a
parallel-run period — the existing VEKN sync plus a new idempotent legacy-archon
sync (#115) — and cutover collapses to: freeze old → final sync → nginx vhost
swap. Old archon is decommissioned once the new stack is battle-tested.

Deployment path is ready: the systemd ansible stack (prod + beta inventories,
CI-built Release artifacts, tag-then-release ceremony) was delivered by epics
#81/#85 (#37 closed).

## Children (gating work + phases)
- **#36** ✅ pre-Phase-0 decisions (several revised 2026-06-10, see Decisions)
- **#37** ✅ ansible deploy stack (via #81/#85)
- **#38** ✅ ETL + validation harness, rehearsed end-to-end on a prod dump
- **#114** push stamping/guards — migrated/synced data must be push-inert (gates #39)
- **#115** legacy-archon daily sync — idempotent merge mode (gates #39; design:)
- **#116** prod PG sequencing + `migrate_postgres.yml` must stop `archon_web`
- **#91** beta shakedown on owner infra at `new.archon.krcg.org` (gates #39)
- **#39** Phase 1 — parallel run at `new.archon.vekn.net` (weeks)
- **#40** Phase 2 — flip (vhost swap, minutes)
- **#41** Phase 3 — post-flip (bot guild install, TWDA, passkeys, monitoring)
- **#42** Phase 4 — decommission old archon
- related: **#113** officials-contacts re-projection on deploy (not a migration
  concern per owner; rides its own ticket)

---

## Context

`archon.vekn.net` runs legacy **archon** (`/Users/lpanhaleux/Developer/archon`):
Python FastAPI + PostgreSQL 16 (`archondb`, service `archon_web`, port 8001,
`ubuntu@46.226.104.123`), JSONB schema (`members`, `tournaments`, `leagues`,
`tournament_events`, `clients`, `member_deletions`), Jinja+vanilla-TS frontend,
ansible-deployed. It syncs from vekn.net **and pushes to it** (`VEKN_PUSH=1`),
and can mint VEKN ids. Its VEKN sync is an in-app asyncio task (stopping the
service stops the sync). It has **no** read-only/maintenance mode — freeze =
stop `archon_web` + a static nginx maintenance page.

The rewrite **archon-vibe** (this repo) deploys to the **same VPS** (~2GB RAM,
decision: no second box): Svelte PWA + FastAPI + PG17, Rust/WASM engine, unified
`objects` table with pre-computed access projections, companion Discord bot.
Note: archon-vibe has its **own Discord application** (`1495034668469194864`),
distinct from old archon's (`1381856472161456139`) — Discord identity carries
over via `discord_id` (app-independent); redirect URIs are configured on the
*new* app only.

Goal: move `archon.vekn.net` to the new stack preserving all member identities,
tournament history, leagues, sanctions — with near-zero user-visible downtime.

## Key data-shape diffs (what the ETL/merge handles)

| Concept | Old | New |
|---|---|---|
| Storage | per-type tables, flat JSONB `data` | unified `objects` table, 3 access projections |
| Member | one row, everything embedded | `User` + `AuthMethod` rows + separate `Sanction` rows |
| Tournament | `players: dict`, `rounds:[Round{tables}]`, embedded decks/sanctions | `players: list`, `rounds: list[list[Table]]`, `finals`, precomputed `standings`; decks → `DeckObject`, sanctions → `Sanction` |
| Roles | Admin, Playtester, … | `Admin`→`IC`, `Playtester`→`PT`, + `DEV` |
| Formats | …, Draft | Draft→`Limited` (provenance note in description) |
| IDs | UUID v4 | UUID v7 — old v4s are valid strings, **preserved** (what makes the merge an upsert) |
| `tournament_events` log | 366d retention | no equivalent — dump to cold storage (#42) |

Full mapping (ranks, states, sanction categories, decks, league fields) and the
rehearsed and validated before the cutover.

---

## Architecture: two upstreams, single writer per field

During the parallel run the new stack ingests from **vekn.net** (identity,
round-less ratified results, calendar — unchanged) and from **old archon**
(everything vekn doesn't carry: contact/discord/nickname/coopted_by, roles,
sanctions, leagues, rich play data for events held there). Three rules make the
combination graceful and idempotent — see `wiki/vekn.md`
for the full design:

1. **Single writer per field** — each field has exactly one sync source, so the
   two dailies can never flip-flop a value. Old-archon identity edits flow in
   *via* vekn.net (old pushes members there).
2. **`local_modifications` trumps both syncs** — already enforced field-by-field
   by the VEKN sync (`vekn_sync.py:662`); set by in-app edits
   (`routes/users.py:188-262`). **Roles are special-cased harder: seeded once by
   the ETL (old-archon mapping), then app-managed only — no sync ever writes
   roles again** (the vekn-sync role derivation is removed outright, no flags;
   beta and prod identical by construction). Old-archon role changes during the
   parallel run don't propagate — role management moves to the new app at
   Phase-1 start.
3. **Rich-wins + single-holder invariant** for tournaments — vekn-first then
   archon-rich merges INTO the vekn-created copy (the existing rich-guard at
   `vekn_tournament_sync.py:332` protects it afterwards); at most one live
   tournament per vekn event id; both-rich = one-app-per-event violation, logged.

**Dual push.** Both stacks run `VEKN_PUSH` during the parallel run; officials
handle each event wholly in ONE app, vekn.net mediates. Safe only once #114
lands: ETL/sync-ingested data must be stamped push-inert
(`vekn_pushed_at`/`vekn_synced=True`), else the first `batch_push` re-submits
thousands of ratified results and ~19k member updates (`vekn_push.py` selects on
those markers).

**Initial population is SYNC-FIRST** (revised 2026-06-14 — supersedes the
original ETL-first call; principal-engineer review + #169). Empty DB → VEKN
member+tournament sync creates accounts (fresh uuid7) → legacy `--merge` layers
archon-owned fields and rich play data on top, **matching members by `vekn_id`**
and remapping every old-archon uid reference through a `member_uid_map` (#169).
This is the exact path the #91 beta exercises, so prod ships the ordering we
battle-tested instead of a second one. ETL `--truncate` (uid-preserving,
rehearsed 2026-06-09: 0 errors / 0 dupes) demotes to **disaster-recovery +
dev-seed**, not the prod seed.

What made the flip safe: #169's reference remap removes ETL-first's only real
advantage (uid preservation → native ref integrity), so which uid an account
carries no longer matters — nothing external depends on old-archon uids
(calendar tokens keyed by their own column, bot state by `discord_id`,
tournament deep-links preserved because rich data merges INTO the vekn-created
copy and keeps its uid). The two decisions are **coupled**: sync-first makes the
remap load-bearing — the VEKN tournament sync writes uuid7 player uids
(`vekn_tournament_sync.py:180`), so an un-remapped rich merge would split one
tournament across uuid7 `players` and old-archon `rounds`/`seating`. **Cutover
gate:** refuse the final `--merge` if the live vekn-account count is below
threshold (~18k; beta synced 18,831 clean), so a half-failed sync can't seed
thousands under old uids. The recurring merge then keeps the DB converged daily.

**Auth:** Discord carries over (`discord_id` + discord `AuthMethod`); legacy
password hashes don't migrate — email users re-establish via magic link on
migrated `contact_email`. Passkeys are new-stack-only, opt-in post-flip.

---

### Phase 1 (#39) — parallel run at `new.archon.vekn.net` (a couple of weeks)

Both apps live on the same VPS, both pushing to vekn.net, the new stack syncing
daily from both upstreams. **Open access** — officials are the live testers (no
invite gate; the one comms rule is one-app-per-event). **Bot enabled** (new
Discord app; side effects scoped by guild installation — test guild first).
Nothing created on the new stack is ever wiped.

Prereqs/config (see ticket): #91 beta passed, #114 + #115 landed, PG sequencing
per #116 (recommended: `just migrate-postgres-prod` first — with #116's
`archon_web` fix — so one PG17 cluster on 5432 hosts both `archondb` and the new
`archon` db; avoids the 5433 two-cluster trap and halves PG RAM), real host in
`inventories/prod/hosts.ini`, vault populated, committed phase-1 override
(`domain_main=new.archon.vekn.net` — redirect URI/RP_ID derive), DNS A records.

**Rollback:** stop the new services. Zero impact on old archon.

**Exit:** a couple of weeks of real events run end-to-end on the new stack, both
syncs and push behaving, officials satisfied. (No automated drift reporting —
owner decision; sync logs must be loud on conflicts.)

### Phase 2 (#40) — flip (minutes)

Announce → freeze old archon (stop `archon_web` + nginx maintenance page; that
also stops its in-app sync/push) → insurance `pg_dump` of `archondb` → final
#115 run + checks → **wall-clock normalization** (below) → ratings recompute →
**nginx vhost swap** (both stacks share
the IP, so this is NOT a DNS cutover): redeploy new stack with
`domain_main=archon.vekn.net`; re-host legacy read-only at `old.archon.vekn.net`
(domain is a var in `archon/ansible/archon.yml`; Discord login breaks there —
acceptable for a 30-day safety net). The `archon.vekn.net` cert already exists
on the box; watch the two certbot renewal setups until #42 consolidates them.

**Wall-clock normalization** (`backend/scripts/normalize_wall_clock.py`, #527):
`start`/`finish` are naive wall clock paired with `timezone`, and three writers
used to store tz-aware instants instead — readers anchor them a second time, so
the venue's offset shows up as a wrong time. The fix lets the VEKN sync and the
#115 merge heal what they own; a `finish` stamped by the app on a tournament run
*here* is owned by no sync and never gets rewritten, hence the one-off. Report by
default, `--apply` to write, idempotent (only touches values still carrying an
offset). Order matters: after the final merge/sync so the self-healing writers
have gone first, before the ratings recompute because a rating's date comes from
`finish or start` and a shifted instant lands on the wrong day at the edges. It
rewrites `modified`, so touched tournaments re-download on each client's next
reconnect — free inside a window that already redeploys. Dev-DB run: 8187 rows in
24 s, second run reports 0.

**Rollback:** vhost flip back (instant; old data untouched — the sync only reads
it). After the flip, writes land on the new stack; rolling back later loses
them — same trade-off as any cutover, but the window shrinks to whenever the
flip is judged failed.

### Phase 3 (#41) — post-flip

Install the bot on prod guild(s) (installation, not deployment), Discord portal
redirect URIs + ToS/privacy URLs (#24), TWDA import/push if desired, passkey
opt-in, optional re-login notice, monitor error rates / SSE / IDB hydration for
2–4 weeks. `VEKN_PUSH` has been live since Phase 1.

### Phase 4 (#42) — decommission

Disable #115 (roles need nothing — they're app-managed since the seed, no
re-enable question); final `pg_dump` archive; stop
`archon_web`; remove `old.archon.vekn.net` vhost/DNS; consolidate certbot;
archive the old repo; cold-store `tournament_events`.

---

## Critical files

- `backend/scripts/migrate_from_archon.py` — ETL (done, #38) → gains merge mode (#115)
- `backend/scripts/migrate_validate.py`, `check_merge.py` — validation (done; extend for merge invariants)
- `backend/src/vekn_push.py` — stamping/guards (#114)
- `backend/src/vekn_sync.py`, `vekn_tournament_sync.py` — remove role writes, sync stamping (#114/#115)
- `ansible/playbooks/migrate_postgres.yml` — must stop `archon_web` (#116)
- old repo: nothing to modify — freeze is operational (stop service + maintenance page)

## Decisions

Settled 2026-06-09 (#36), still standing: parallel domain on the **same VPS**;
Draft→Limited; OAuth `clients` re-register (enumerate active ones from a dump —
expected few); `tournament_events` dump-only; rating drift tolerated (recompute
post-import, log >5% deltas).

**Revised 2026-06-14** (supersedes "ETL-first for initial population" above):
initial population is **sync-first**, matching the beta — see the SYNC-FIRST
paragraph in Data flow and #169. ETL `--truncate` is now DR/dev-seed only.

Revised 2026-06-10 (owner):
1. **No wipe / no migration window** — recurring idempotent legacy sync (#115);
   cutover = freeze + final sync + vhost swap.
2. **Dual push during the parallel run** — both apps push to vekn.net;
   one-app-per-event discipline; #114 makes ingested data push-inert first.
3. **Bot enabled everywhere** (beta included) — it's a primary test subject;
   guild installation scopes its side effects. No deploy toggle needed.
4. **Open access in Phase 1** — no invite gate; officials get told, everyone can
   try it on real events.
5. **Roles**: seeded once by the ETL from old archon, then **app-managed only,
   permanently** — no sync (vekn or legacy) ever writes roles again. Old-archon
   role changes during the parallel run don't propagate (manage roles in the new
   app from Phase-1 day one); post-seed vekn.net list appointments need an
   in-app grant.
6. **No drift-report automation** — officials are the live testers; rely on loud
   sync logs.
7. Officials-contacts delivery/cloaking is ordinary app deployment (#113), not a
   migration workstream.
8. ~~"DNS swap" cutover~~ → it was always a same-IP setup: cutover is an nginx
   vhost swap; DNS only gains `new.`/`old.`/`bot.` records ahead of time.

## Verification checklist (gates the flip, #40)

- [ ] #114 audit: all three `batch_push` queries return zero candidates after
      ETL + both syncs on a prod dump (run on #91, re-run on the Phase-1 stack
      before enabling push)
- [ ] #115 exercised in both orders (vekn-first / archon-first) incl. the
      single-holder dedup; deck/sanction identity stable across re-runs
- [ ] An event held on old archon during Phase 1 shows up rich on the new stack
      after the next daily sync (rounds/seatings/decks/sanctions), and is not
      re-pushed
- [ ] An event held on the new stack is pushed once, appears round-less on old
      archon, and is never overwritten by either sync
- [ ] Roles untouched by both dailies (seeded set stable across runs); in-app
      role edit sticks; officials informed role management lives in the new app
      from Phase-1 start
- [ ] Profile edit on the new stack survives both dailies (`local_modifications`)
- [ ] Member counts converge (± deletions); orphan scan clean; ratings
      recomputed with deltas reviewed (≤5% or documented)
- [ ] Old-archon Discord user logs into the new stack; email user re-establishes
      via magic link
- [ ] Vhost swap rehearsed against the box's nginx state: no duplicate
      `server_name`, certs valid for `archon.vekn.net`/`old.`/`bot.`
- [ ] `old.archon.vekn.net` serves read-only legacy for ~30 days post-flip

## The dedup run, as beta measured it

Rehearsed on beta 2026-08-20, after the archive backfill: **49 mixed-vekn groups,
1 double-counted in ratings, and 30 holding an archive reconstruction that get no
proposal and must be decided by hand.** Those 30 are a class the archive backfill
*creates*: reconcile finds no candidate when a held copy's standings yield no
winner name, so it reconstructs an event we already hold — a `players=1, decks=1`
row beside a full vekn-linked one of the same name and date. Run the dedup after
the backfill on prod, not before, or that class is invisible to it.

Beta also holds two live Finished copies of one event under the *same* vekn id
(`12642`), which is outside the audit's stated scope of groups where some but not
all copies hold one. The event-code backfill gave one the code `12642` and minted
`SCHNJG` for the other; short links survive it either way, since
`get_tournament_by_event_code` falls back to a vekn external-id lookup. Check for
that shape on prod before the code backfill — a duplicate arriving after the
2026-08-17 check would land in it.
