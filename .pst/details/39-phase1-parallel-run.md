# #39 — Phase 1 parallel run at `new.archon.vekn.net` (checklist)

## ✅ Phase-1 bring-up COMPLETE 2026-07-01 — now in the F monitoring window
**State:** Phase-1 stack **LIVE** on prod, push **ON + validated**. **C-1..C-4,
D-1, E-1..E-4 all DONE.** Parallel run is up: new stack at new.archon.vekn.net,
push on (first push 07:13 UTC created member 1000000; re-audit all-zero), daily
VEKN + legacy(#115) syncs firing, bot on a test guild with Linked Roles working
(3 metadata ladders, no Ethics), IC admins notified (one-app-per-event +
roles-in-new-app). Box: **1 vCPU / 945 MB** Xen VPS + 4 GB swap (undersized —
#344).

**NOW:** run for ~2 weeks and watch the **F exit criteria** (below) on real
events. When they hold → proceed to **#40 Phase-2 flip**. Deferred during the run:
**#346** (post-cutover push of stuck legacy event 13379), #344 (resize box), #343
(warning-free deploys), #345 (calendar URL), #115 residual TODO (unattended-merge
cutover-gate). Prod-guild bot install + Discord portal for archon.vekn.net = #41.
C-3 legacy merge finished 22:40 UTC **Result=success** (CPU 69s, peak 82 MB RAM /
53 MB swap — caps never near; ~33 min wall, IO/1-core bound). Summary: 513 rich
tournaments merged (284 ins / 229 upd), **7,897 echoes correctly skipped**; 3,129
decks; 1,476 member updates + 30 ins (17,379 unchanged); 606 discord auth; 9,939
coopted remaps; 17 leagues; 66 sanctions; 19,030 users. The **04:00 timer re-runs
it nightly** (idempotent — expect mostly unchanged/echo-skip; that's E-1 working).
**C-4 dedup query → 0 rows** (2026-07-01): one-live-per-vekn-id invariant holds,
no cleanup needed.

**D-1 push GATE = GREEN** (2026-07-01): Q2=Q3=**0** (dangerous re-submission cases
clean); Q1=1 is the expected **#216 vekn-less participant** (Araceli, vekn_id
1000000) — push-eligible by design, will register on vekn.net + self-stamp on the
first push. See D-1 item below.

**E-2 push ON + VALIDATED** (2026-07-01): flipped `vekn_push_enabled: "true"`
(literal string — empty ≠ default('true')), redeployed 05:57 UTC. First hourly
`batch_push` at 07:13 UTC created member 1000000 (Araceli) on live vekn.net and
stamped `vekn_synced` → **post-flip re-audit Q1=Q2=Q3=0**. Push behaving.

**E-3 DONE**: bot on a test guild (disabled portal "Requires OAuth2 Code Grant"),
Linked Roles working (3 metadata ladders, `>=` thresholds, no Ethics field).
**E-4 DONE**: IC admins notified. → Phase-1 bring-up complete; now watching F.

**Open tickets:** #344 (resize prod — strong case now: 1 vCPU/945 MB vs beta 6/11.4 GB; or trim PG) · #343 (warning-free deploys) · #115 wip (runner DONE; remaining TODO = add the ~18k cutover-gate to the script for unattended daily safety, then close) · #41/#24 (Discord portal, Phase 3). Optional: clean prod disk-read benchmark (skipped during merge).

---

Stand up archon-vibe on the **live vekn.net VPS** (`ubuntu@46.226.104.123`)
alongside legacy archon, push ON, daily VEKN + legacy-archon (#115) syncs, for
~2 weeks until battle-tested. This is the #91 beta runbook **re-run on prod**,
with three structural differences that drive the extra steps below:

1. **Prod uses archon's own ansible foundation**, not server-setup. Bring-up is
   `site.yml` = `bootstrap.yml` (common: nginx/ufw/certbot) → `database.yml`
   (postgresql) → `deploy.yml`. Beta dropped these (server-setup owned them); on
   prod they run, on a box legacy archon already configured — watch for collision.
2. **Legacy shares the box.** PG sequencing (#116) + nginx vhost coexistence are
   prod-only. The #115 sync reads the live `archondb` over the local socket — no
   separate dump/restore like beta §3.
3. **Push is live** (`VEKN_PUSH=true`). The #114 audit must read **0 on prod**
   before the first push interval fires — sequencing decision in D below.

State verified 2026-06-26: prod `hosts.ini` already has the real host
(`ubuntu@46.226.104.123`); prod vault is encrypted; `new.`/`bot.` DNS empty;
`archon.vekn.net` → .123 (legacy live). Prod box still PG16 + legacy on 5432.

## Open decisions / risks (resolve before starting)
- **D-1 push sequencing.** RESOLVED → (a). Deploy push-off, seed+merge+audit-zero,
  then flip + redeploy. Mechanism shipped in A-1 (`vekn_push_enabled=false` in the
  phase-1 override; `vars.yml` reads `VEKN_PUSH: {{ vekn_push_enabled | default('true') }}`).
- **D-2 bootstrap on a live box.** RESOLVED → keep + harden the existing prod
  foundation (it's already separate from beta and Ubuntu-aware: `pgdg_repo`
  targets Ubuntu 24.04, `common` uses ufw + ESM origins). Coexistence audit vs
  legacy (provisioned by `archon/ansible/`) — safe except one collision, now fixed:
  - **PG role collision (FIXED).** Both stacks used role `archon` on the shared
    PG17 cluster → `database-prod` would reset its password and lock legacy out.
    Fix: prod `db_user=archonvibe` (db stays `archon` ≠ legacy `archondb`). The
    role/db/owner/pg_hba/privs/DATABASE_URL all derive from `db_user`. Permanent
    (prod-final in vars.yml), not a phase-1 override.
    - **C-3 consequence:** the #115 merge can't read `archondb` as `archonvibe` —
      its `OLD_DATABASE_URL` must carry legacy's `archon` credential explicitly.
  - **Box-wide changes, accepted consciously** (dry-prod shows both diffs first):
    `ufw enable` default-deny is net-positive (legacy has no firewall; `common`
    allows OpenSSH/80/443 = all legacy needs, its uvicorn:8001 + PG are localhost);
    `50unattended-upgrades` overwrite is security-only, no auto-reboot.
  - **Verified no-collision:** nginx vhosts (`new.archon.vekn.net.{http,https}.conf`
    + `bot.*` vs legacy `archon_web.*`; ports 8007/9007 vs 8001), certbot (separate
    cert names, shared OS timer, identical reload-hook), systemd units, default-site
    removal (already gone), PG `alter_system` tunings (identical values → no-op).
  - Still rehearse with `just dry-prod` and read the diff before any live run.
- **D-3 ansible_user.** RESOLVED → connect as `ubuntu`. `hosts.ini` already sets
  `ansible_user=ubuntu`; every privileged task uses plain `become: true` (sudo) or
  `become_user: postgres`/service-user — nothing needs the human account. The
  `admin_user: lpanhaleux` var is unused dead config (referenced nowhere). Only
  prerequisite: `ubuntu` has passwordless sudo (verify in B-0).
- **D-4 child tickets?** This is one large ticket; decide whether to split A–F
  into `parent:#39` children or run it as a single ticket against this file.

---

## A · Repo deliverables (off-box, before touching prod)
- [x] **A-1 phase-1 domain override (committed).** DONE — `inventories/prod-phase1-override.yml`
      (OUTSIDE `inventories/prod/` so the `-i` dir scan doesn't mis-parse it as
      inventory) sets `domain_main=new.archon.vekn.net` (redirect URIs /
      `WEBAUTHN_RP_ID` / `site_url_base` derive) and `vekn_push_enabled=false`
      (D-1a push-off; vars.yml now reads `VEKN_PUSH: {{ vekn_push_enabled |
      default('true') }}`, prod-final stays on). Wired into `bootstrap-prod`/
      `deploy-prod`/`dry-prod` via the `phase1_override` justfile var (`-e @…`,
      beats group_vars). In the granular flow only `deploy-prod` needs it
      (foundation/database don't use `domain_main`). Render-verified both ways.
      Phase-2 revert = blank `phase1_override` in the justfile.
- [ ] **A-2 prod vault secrets.** Confirm real (not `CHANGE_ME`) values in
      `inventories/prod/group_vars/all/vault.yml`: db password, **new-archon**
      Discord app (`1495034668469194864`) client id/secret + bot token, VEKN
      push token, mail. Leave `vault_bot_oauth_client_id/secret` as placeholders
      — registered in-app after the seed (E-3).
- [x] **A-3 pin the release.** Deploy **`v0.3.5`** (latest CI tag, 2026-06-28).
      Verified it contains the recent code fixes (league RTP, vekn-import). The
      only two commits after the tag are ansible config (GitHub-OAuth env, portal
      doc) — they ship from the working tree at deploy time, not the wheel, so
      v0.3.5 + current `main` is complete. `RELEASE_TAG=v0.3.5 just deploy-prod`.

## B · Foundation on the prod box (one-time)
- [x] **B-0 P0 host sanity** (2026-06-30): passwordless sudo OK, **PG 16.14 on
      5432**, **Ubuntu 24.04 (noble)** (matches the `noble-pgdg` repo line in the
      dry-run), `archon` db free. Mirrors #91 P0.
- [x] **B-1 DNS A records** `new.archon.vekn.net` + `bot.archon.vekn.net` →
      `46.226.104.123`. DONE — both resolve (verified 2026-06-30). Certbot
      HTTP-01 won't hard-fail. Same IP as legacy — no TTL games.
- [x] **B-2 `cd ansible && just galaxy`** (collections). DONE.
- [ ] **B-3 foundation** — `just dry-foundation-prod` first (D-2), then
      `just foundation-prod` (runs `bootstrap.yml` = common role ONLY). **Do NOT
      use `bootstrap-prod`** on the shared box: it runs the full `site.yml`
      (foundation + database + deploy), so its database step would run *before*
      the PG migration and hit the two-cluster trap. `foundation-prod` installs
      packages incl. `python3-psycopg2` (the PG modules need it), the `archon`
      user/dirs, uv/python, nginx, ufw. New nginx vhosts coexist with legacy's
      `archon.vekn.net` server_name.
- [ ] **B-4 PG sequencing (#116)** — `just migrate-postgres-prod`: PG16→17, moves
      `archondb` to the 17 cluster on 5432 (stops/starts `archon_web` around the
      dump+swap — brief legacy write window; prompts y/N). Verify **legacy runs
      clean on PG17** (plain JSONB, expected fine). Then `just database-prod`
      creates the `archonvibe` role + new `archon` db in the shared 5432 cluster.
      Avoids the 5433 two-cluster trap; one cluster halves PG RAM on the ~2GB box.
      **Order is load-bearing:** `foundation-prod` → `migrate-postgres-prod` →
      `database-prod` → `deploy-prod` (C-2).

## C · Deploy + seed (the #91 §2–§5 sequence, prod)
- [x] **C-1 dry run** — DONE (2026-06-30). `dry-prod` surfaced the live-box
      coexistence + foundation diff; three latent prod-only bugs found & fixed
      (common users-before-python order, nginx `http2` directive on 1.24, ssl
      session-cache zone name) before the live run.
- [x] **C-2 deploy + first boot** — DONE (2026-06-30) on `v0.3.5`, push-off. New
      stack live (`new.archon.vekn.net` 200 + cert, bot up, all services active),
      seeded clean: **18,855 users / 8,113 tournaments / 2,176 decks**, snapshots
      `{public 8612, member 29144, full 29144}`. Sizing surprise: 945 MB box (not
      2 GB) → added 4 GB swap (#344).
- [x] **C-3 legacy merge seed (#115)** — DONE 2026-06-30 22:40 UTC, **success**
      via `archon-legacy-sync.service` (peer auth for OLD `archondb`; archonvibe
      scram for NEW). Summary: 513 rich tournaments (284 ins / 229 upd), **7,897
      echoes skipped** (echo guard ✓); 3,129 decks; 1,476 member upd + 30 ins
      (17,379 unchanged); 606 discord auth; 9,939 coopted remaps; 17 leagues; 66
      sanctions; 19,030 users. CPU 69s, peak 82 MB RAM / 53 MB swap. The 04:00
      timer re-runs it nightly (E-1, idempotent).
- [x] **C-4 dup cleanup (#170)** — DONE 2026-07-01. Ran the dedup query on prod
      `archon` → **0 rows**: no multi-rich tournaments live (the beta-side #170
      cleanup already resolved event 12642 et al.; the #115 merge preserved the
      invariant on the prod seed). No soft-deletes needed. One-live-per-vekn-id
      holds. → proceed to D-1.

## D · #114 push audit on prod — THE GATE (before push fires, before in-app test events)
- [x] **D-1 GATE GREEN** (2026-07-01). Ran the three `batch_push` selection
      queries on prod `archon`: **Q2=0, Q3=0** (the dangerous re-submission cases —
      no unstamped import would re-push ratified results or dup-create a calendar
      event). **Q1=1, expected — NOT a stamping bug:** it's the single **#216
      vekn-less participant** (Araceli Ruiz Bruno, uid `8c76e394…`, vekn_id
      **1000000** = first `allocate_next_vekn_id` gap, `coopted_by` set, no
      email/discord). `allocate_veknless_participant` (migrate.py:532, landed
      2026-06-19 — *after* the 2026-06-14 beta §7 audit, so beta showed Q1=0)
      deliberately marks such a played-but-unregistered legacy member
      `vekn_synced=False` so batch_push registers the gap-filled id on vekn.net
      (#184-class collision-claim). **Conscious side-effect:** enabling push will,
      as its first action, `create_member(1000000,…)` on live vekn.net registering
      Araceli, then stamp `vekn_synced=true` → Q1 drops to 0. Gate satisfied →
      proceed to E-2.

## E · Go-live parallel run
- [ ] **E-1 daily syncs scheduled** — confirm both the VEKN sync and the #115
      legacy-archon sync (reading `archondb`) are wired and firing daily; sync
      logs loud on conflicts (no drift automation — owner decision).
- [x] **E-2 enable push** — DONE 2026-07-01. Set `vekn_push_enabled: "true"` in the
      phase-1 override (NOT ""; empty does NOT hit the vars.yml `default('true')` —
      Jinja default() fires only on *undefined* — so an empty value silently
      deploys push-OFF; first redeploy hit exactly that, no `VEKN Push` job in the
      log). Redeployed 05:57 UTC, push job armed. First hourly `batch_push` ran
      **07:13 UTC**: `Created VEKN member 1000000: Araceli Ruiz Bruno` → `Member
      1000000 pushed to VEKN` → job executed successfully (VEKN accepted the
      synthetic id, `vekn_synced` stamped true). **Post-flip re-audit all-zero
      (Q1=Q2=Q3=0)** — gate validated live. Push on and behaving.
- [x] **E-3 bot** (test-guild scope; prod-guild install is Phase 3 / #41) —
      DONE 2026-07-01: bot installed on a test guild and **Linked Roles verified
      working**. Original checklist: register the bot OAuth client (redirect
      `https://bot.archon.vekn.net/oauth/callback`) + vault creds + redeploy; set
      the new-archon portal redirect URI
      (`https://new.archon.vekn.net/auth/discord/callback`). NOTES 2026-07-01:
      bot **installed on test guild** (had to disable "Requires OAuth2 Code Grant"
      in the portal — the callback-less bot-add flow is incompatible with it; not
      needed, archon's user Discord OAuth is a separate flow). Linked-Roles setup
      underway: archon exposes **3 role-connection metadata ladders** (`roles_hook`:
      VEKN Role 1–4 Member/Prince/NC/IC, Judge Level 1–3, Playtest Role 1–2, all
      type-2 `>=`) → create ≤9 Discord roles gated on `>=` thresholds, self-assigned
      via the verification URL. NB: **`Ethics` role is NOT exposed** as metadata
      (unmapped in `build_metadata`); a Discord Ethics linked-role needs a 4th
      metadata field (3 of 5 slots used) + redeploy — owner deciding whether to
      add it; file a ticket if pursued.
- [x] **E-4 comms** — DONE 2026-07-01. Sent to **Inner Circle admins** (top-tier
      testers): new stack live at new.archon.vekn.net; **one app per event** (never
      split an event across both); no double-entry (legacy events sync in read-only
      daily, new events push to VEKN once); **role management lives in the new app
      from day one** (legacy role changes no longer propagate); log in fresh
      (old sessions don't carry, Discord/magic-link).

## F · Exit criteria (the #35 flip-gate, exercised over ~2 weeks)
Phase 1 is "done"/ready-for-#40 when, on real events:
- [ ] An event held on **old archon** during the run shows up rich on the new
      stack after the next daily sync (rounds/seatings/decks/sanctions), not re-pushed.
- [ ] An event held on the **new stack** is pushed once, appears round-less on
      old archon, never overwritten by either sync.
- [ ] **Roles** untouched by both dailies (seeded set stable); in-app role edit
      sticks.
- [ ] Profile edit on the new stack survives both dailies (`local_modifications`).
- [ ] Member counts converge (± deletions); orphan scan clean; ratings recomputed,
      deltas ≤5% or documented.
- [ ] Old-archon Discord user logs into the new stack; email user re-establishes
      via magic link.
- [ ] Both syncs + push behaving, officials satisfied. → proceed to #40.

**Rollback at any point:** stop the new services. Zero impact on old archon
(the #115 sync only reads `archondb`).
