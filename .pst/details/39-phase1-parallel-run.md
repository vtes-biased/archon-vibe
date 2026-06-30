# #39 — Phase 1 parallel run at `new.archon.vekn.net` (checklist)

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
- [x] **A-1 phase-1 domain override (committed).** DONE — `inventories/prod/phase1-override.yml`
      sets `domain_main=new.archon.vekn.net` (redirect URIs / `WEBAUTHN_RP_ID` /
      `site_url_base` derive) and `vekn_push_enabled=false` (D-1a push-off; vars.yml
      now reads `VEKN_PUSH: {{ vekn_push_enabled | default('true') }}`, prod-final
      stays on). Wired into `bootstrap-prod`/`deploy-prod`/`dry-prod` via the
      `phase1_override` justfile var (`-e @…`, beats group_vars). Render-verified
      both ways. Phase-2 revert = blank `phase1_override` in the justfile.
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
- [ ] **B-0 P0 host sanity** (read-only, as `ubuntu@46.226.104.123`): legacy
      archon + `archon_web` active, PG16 on 5432, passwordless sudo, db name
      `archon` free (`SELECT datname FROM pg_database`). Mirrors #91 P0.
- [x] **B-1 DNS A records** `new.archon.vekn.net` + `bot.archon.vekn.net` →
      `46.226.104.123`. DONE — both resolve (verified 2026-06-30). Certbot
      HTTP-01 won't hard-fail. Same IP as legacy — no TTL games.
- [ ] **B-2 `cd ansible && just galaxy`** (collections).
- [ ] **B-3 bootstrap foundation** — `just dry-prod` first (D-2), then
      `just bootstrap-prod`. Adds the common foundation; new nginx vhosts coexist
      with legacy's `archon.vekn.net` server_name.
- [ ] **B-4 PG sequencing (#116)** — `just migrate-postgres-prod`: PG16→17, moves
      `archondb` to the 17 cluster on 5432 (stops/starts `archon_web` around the
      dump+swap — brief legacy write window). Verify **legacy runs clean on
      PG17** (plain JSONB, expected fine). Then `just database-prod` creates the
      new `archon` db in the shared 5432 cluster. Avoids the 5433 two-cluster
      trap; one cluster halves PG RAM on the ~2GB box.

## C · Deploy + seed (the #91 §2–§5 sequence, prod)
- [ ] **C-1 dry run** — `just dry-prod` (or check-mode deploy); review
      names/paths/templates/diff.
- [ ] **C-2 deploy + first boot** — `RELEASE_TAG=vX.Y.Z just deploy-prod` (with
      push-off override if D-1(a)). Startup VEKN sync chain seeds the **empty
      `archon` db** (members → tournaments → TWDA → ratings → snapshot). Verify:
      `systemctl status archon-backend archon-bot`; `curl -I https://new.archon.vekn.net`
      (200 + cert); `curl -sI https://bot.archon.vekn.net`; `/api/cards` from the
      wheel (**#80**); snapshots under `/var/lib/.../snapshots`.
- [ ] **C-3 legacy merge seed (#115)** — `migrate_from_archon.py --merge` reading
      the live `archondb` over the socket. Since the new stack's role is now
      `archonvibe` (D-2), `OLD_DATABASE_URL` must use **legacy's `archon`
      credential**: `postgresql://archon:<legacy-pw>@/archondb?host=/var/run/postgresql`.
      **Cutover gate:** refuse the merge if live vekn-account count < ~18k
      (beta synced 18,831 clean) — guards against a half-failed sync seeding
      under wrong uids. Rich archon data merges INTO the vekn-created copies
      (uid survives via #169 remap).
- [ ] **C-4 dup cleanup (#170)** — resolve the multi-rich tournament(s):
      `SELECT "full"->'external_ids'->>'vekn' evt, count(*) FROM objects WHERE
      type='tournament' AND deleted_at IS NULL AND "full"->'external_ids'->>'vekn'
      IS NOT NULL GROUP BY 1 HAVING count(*)>1;` Known: vekn event **12642**
      (3-way dump dup) nets to 2 live. Pick the canonical/most-complete copy per
      event, soft-delete the rest. Re-run query → **0 rows**.

## D · #114 push audit on prod — THE GATE (before push fires, before in-app test events)
- [ ] **D-1** Run the three `batch_push` selection queries (runbook #91 §7) on the
      prod `archon` db → **all 0**. Any query-2/3 row tracing to a migrated
      import = stamping bug → stop and fix before enabling push (prod would
      re-submit ratified results). A query-1 `vekn_synced=false` user is a bug
      unless it's a brand-new member the live sync hasn't stamped yet — re-run
      after the sync settles. **Do not enable push until all three read 0.**

## E · Go-live parallel run
- [ ] **E-1 daily syncs scheduled** — confirm both the VEKN sync and the #115
      legacy-archon sync (reading `archondb`) are wired and firing daily; sync
      logs loud on conflicts (no drift automation — owner decision).
- [ ] **E-2 enable push** — if deployed push-off (D-1a), flip `VEKN_PUSH` and
      redeploy; re-run the D audit once more post-flip before trusting it.
- [ ] **E-3 bot** — log in as IC, Profile → Developer: register the bot OAuth
      client (redirect `https://bot.archon.vekn.net/oauth/callback`), put
      `vault_bot_oauth_client_id/secret` in the vault, redeploy. Set the
      new-archon Discord app portal redirect URI
      (`https://new.archon.vekn.net/auth/discord/callback`). Install on a **test
      guild** first (prod-guild install is Phase 3 / #41).
- [ ] **E-4 comms** — tell officials: open access, **one app per event**, role
      management lives in the new app from day one (role changes no longer sync).

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
