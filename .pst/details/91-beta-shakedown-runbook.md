# #91 — beta shakedown runbook (turnkey host steps)

First real-host bring-up of archon-vibe on owner infra. **Gates #39.**

Off-host pre-flight 2026-06-12: lint green, 208 backend tests green, workflow
files reviewed — the deploy fileglobs (`archon-*.whl`, `archon_engine-*.whl`,
`archon_discord_bot-*.whl`, `backend-requirements.txt`, `bot-requirements.txt`,
`frontend-dist.tar.gz`) match the upload names in `release-artifacts.yml`.
That workflow has **never run** (no Release exists): step 0 is its first live
exercise — that's part of the shakedown, not a precondition of it.

## At a glance
| | |
|---|---|
| Host | `deploy@57.129.110.107` (frankfurt), `ansible_user=deploy`, env=beta |
| Foundation | **server-setup** owns base/ssh/ufw/nginx/certbot/Alloy/PG+backups. PG major = distro default — **verify on box (P0)**; ticket assumes 17 |
| App domain | `new.archon.krcg.org`  · bot `bot.archon.krcg.org` |
| Namespace | `new_archon` (user/group, /opt·/var/www·/etc·/var/lib, db `new_archon`) |
| Services | `new-archon-backend`, `new-archon-bot` |
| DB auth | peer over unix socket (runtime user == db role `new_archon`); DSN password vestigial |
| Push | `VEKN_PUSH=false` — beta never pushes (the whole point of the #114 audit) |
| Admin API | `Authorization: Bearer <JWT>` on `/admin/*` — **no `/api` prefix, no cookie auth** |

## Outstanding as of 2026-06-12 (all verified, not assumptions)
- **No GitHub Release exists** and `release-artifacts.yml` has never run → step 0.
- **DNS records absent** (`dig new.archon.krcg.org` / `bot.…` both empty) → P1.
- **`inventories/beta/group_vars/vault.yml` is plaintext `CHANGE_ME` placeholders,
  not yet encrypted**; `vault_db_password` is `""` and the postgres_db role
  *asserts* it non-empty → P2.
- **GitHub `beta` environment exists but is empty** (no `DEPLOY_*` vars/secrets) —
  the CI deploy path is optional wiring (§CI); the shakedown path is local
  `just deploy-beta`.

## On-host findings 2026-06-13 (P0, verified on the box)
- **PG is 17.10** on Debian 13 (trixie) — matches the assumption, **no 16 fork**.
  Services all active, passwordless sudo OK.
- **A legacy-archon BETA already runs on this box** (its own FastAPI/uvicorn) with
  database **`archondb`** on the shared PG17 cluster. It is a **do-not-touch
  neighbor**: nothing of ours references it, and our `§Cleanup dropdb
  archon_legacy` is a *different* database — never drop `archondb`. `archon_legacy`
  and `new_archon` are both free (confirmed).
- **Port collision**: the legacy beta's uvicorn owns `127.0.0.1:8007`, which was
  beta's original `backend_port`. Moved beta to the **+8 pair `8008`/`9008`** in
  `inventories/beta/group_vars/all.yml` (backend/bot kept consistent). The two
  stacks are otherwise fully isolated (own DB, ports, server_names, `new-archon-*`
  units). The whole 8xxx/9xxx band is otherwise empty.

## Read before running anything

1. **Beta is `just deploy-beta` ONLY** (plus `just dry-deploy-beta` for check
   mode). The beta wrappers for `site.yml`/`database.yml`/`upgrade.yml`
   (`bootstrap-beta`/`database-beta`/`dry-beta`/`upgrade-beta`) were **removed**:
   archon's `common`+`postgresql` roles collide with the server-setup
   foundation, and frankfurt system upgrades (apt + reboots) are server-setup's
   job. `deploy-beta.yml` ships only the app (runtime user/dirs via
   `tasks/app_user.yml`, DB/role via server-setup's `postgres_db`, then
   backend/frontend/bot). See `.pst/details/85-beta-on-server-setup.md`.
2. **Ops scripts run from a source checkout on the box, as the `postgres` OS
   user** (peer auth reaches both `archon_legacy` and `new_archon`; the
   `new_archon` user is nologin and has no rights on the scratch DB).
   `uv sync --no-dev --no-install-project` is enough: the ETL import chain
   (`src.db` / `src.models` / `src.vekn_sync`) never touches the Rust engine,
   and `card_data.py` falls back to the committed `engine/data/cards.json`.
3. Dry-run with `just dry-deploy-beta`: the release-fetch block is marked
   `check_mode: false` (localhost-only, fills `ansible/build/`), so a plain
   `--check --diff` works against the Release with no prep; everything
   host-side stays check-mode. `RELEASE_TAG=…` / `SOURCE=local` work as for
   `deploy-beta`.
4. **Export `ANSIBLE_VAULT_PASSWORD_FILE=.vault_pass`** — neither `ansible.cfg`
   nor the justfile sets it; without it every playbook run fails to decrypt vault.yml.
5. Keep `?host=/var/run/postgresql` in all DSNs — psycopg's bundled libpq
   defaults to the wrong socket dir.
6. Writes from on-box scripts are **not broadcast over SSE** (broadcast is
   in-process in the backend); open clients catch up on reconnect. After bulk
   rewrites (truncate/ETL), restarting the backend is the clean reset anyway.
7. server-setup's `postgres_db` sets per-DB timeouts on `new_archon`
   (statement 15s / idle-in-txn 60s / lock 5s). `pg_dump`/`pg_restore` override
   their own; ETL statements are small and per-transaction. If the ETL ever
   trips one on real volume, lift it per-database temporarily
   (`ALTER DATABASE new_archon SET statement_timeout = 0`), restore after.

## Prerequisites (one-time, before first deploy)

- [ ] **P0 · host sanity** (read-only, as `deploy@57.129.110.107`):
  ```sh
  lsb_release -ds; psql --version; pg_lsclusters    # PG major — ticket says 17, distro decides
  systemctl is-active nginx postgresql alloy postgres-backup.timer certbot.timer
  sudo -n true && echo sudo-ok                      # become:true needs passwordless sudo
  sudo -u postgres psql -Atc "SELECT datname FROM pg_database WHERE NOT datistemplate"
  ```
  `archon_legacy` / `new_archon` must be free. If PG turns out to be 16: decide
  accept-for-beta vs upgrade-frankfurt-first (prod #39 gets PG17 via its own
  playbooks either way). Note `postgresql_version: 17` in beta group_vars is
  **inert** — only archon's own `postgresql` role reads it, which beta never runs.
- [ ] **P1 · DNS** A records `new.archon.krcg.org` + `bot.archon.krcg.org` →
  `57.129.110.107`. Certbot HTTP-01 hard-fails the deploy until they resolve.
- [ ] **P2 · vault** (from `ansible/`):
  ```sh
  echo '<vault password>' > .vault_pass && chmod 600 .vault_pass
  export ANSIBLE_VAULT_PASSWORD_FILE=.vault_pass
  $EDITOR inventories/beta/group_vars/vault.yml     # replace every CHANGE_ME; vault_db_password non-empty
  uv run --project .. ansible-vault encrypt inventories/beta/group_vars/vault.yml
  ```
  (First time is `encrypt` — the file is currently plaintext; `ansible-vault
  edit` works from then on.) `vault_bot_oauth_client_id/secret` **cannot be real
  yet**: that OAuth client is registered in-app after the ETL (§6). Leave the
  placeholders — the bot service deploys and runs; only its login flow waits.
- [ ] **P3 · beta Discord app**: create the application (+ bot user), set user-OAuth
  redirect `https://new.archon.krcg.org/auth/discord/callback`, copy client
  id/secret + bot token into the vault. (The bot's
  `https://bot.archon.krcg.org/oauth/callback` redirect is registered against
  the **backend** OAuth client in §6, not in the Discord portal.)
- [ ] **P4 · legacy dump** (custom format) from the production box, onto frankfurt:
  ```sh
  ssh ubuntu@46.226.104.123 'sudo -u postgres pg_dump -Fc archondb' > archondb.dump
  scp archondb.dump deploy@57.129.110.107:/tmp/
  ```
- [ ] **P5 · collections**: `cd ansible && just galaxy` (server-setup installs
  from git `main`; reinstalls every run, so new server-setup commits are picked up).
- [ ] *(optional)* officials contacts: ansible-vault file at
  `ansible/roles/fastapi_backend/files/officials_contacts.json.vault` →
  deployed to `/etc/new_archon/officials_contacts.json`; absent = graceful no-op.

## Steps

### 0 · Cut the first release
```sh
just release v0.1.0     # repo root: pushes the tag ONLY — CI then runs e2e → (green) creates the Release → release-artifacts.yml attaches assets
gh run watch --repo vtes-biased/archon-vibe    # wait for that Actions run; the Release + its assets don't exist until it's green (~minutes)
gh release view v0.1.0 --repo vtes-biased/archon-vibe --json tagName,assets --jq '{tag:.tagName,assets:[.assets[].name]}'
```
`just release` only tags+pushes; the Release is created asynchronously by CI, so
`gh release view` 404s until the run above is green — don't skip the `gh run
watch`. Expect exactly the six assets listed in the pre-flight note. A failing
e2e suite aborts the Release — fix and re-tag. For un-released changes later,
`SOURCE=local just deploy-beta` (needs Docker for the manylinux engine wheel) —
but the gate run must ship **CI-built** wheels; that's the point of #91.

### 1 · Dry run (optional)
```sh
cd ansible
just dry-deploy-beta     # deploy-beta.yml --check --diff; fetches the Release for real (localhost only)
```
Command-ish tasks report `skipped` in check mode; the value is reviewing
names/paths/templates before first contact.

### 2 · Deploy + first boot  *(this is also leg A's vekn-first seed)*
```sh
cd ansible
just deploy-beta                       # latest Release; RELEASE_TAG=vX.Y.Z to pin
```
On the box:
```sh
systemctl status new-archon-backend new-archon-bot
journalctl -u new-archon-backend -f    # init_db, then the startup VEKN sync chain
curl -I  https://new.archon.krcg.org                          # 200 + valid cert
curl -sI https://bot.archon.krcg.org                          # bot vhost answers
curl -s  https://new.archon.krcg.org/api/cards | head -c 200  # #80: cards.json from the wheel
systemctl show -p NRestarts new-archon-bot                    # placeholder OAuth creds OK? expect 0 — it's a pure OAuth client, creds only used at login (§6); a climbing count = crash-loop, check journalctl -u new-archon-bot
```
**The backend auto-runs the full VEKN sync chain at startup** (members →
tournaments → TWDA → ratings → snapshot) into the empty DB — the vekn-first
half of leg A happens by itself. Wait for `VEKN sync completed: N created …`
and the tournament-sync summary (expect many minutes for a full first pull).
TWDA may log errors without `vault_twda_github_*` — out of scope here. No login
is possible yet (sync-created users carry no auth methods); that arrives with
the ETL in leg B.

### 3 · On-box ETL workbench (one-time)
```sh
sudo -iu postgres
git clone --depth 1 https://github.com/vtes-biased/archon-vibe.git ~/archon-vibe
cd ~/archon-vibe && uv sync --no-dev --no-install-project
createdb archon_legacy
pg_restore -O -x -d archon_legacy /tmp/archondb.dump   # strip owners/ACLs: prod roles don't exist here
export OLD_DATABASE_URL='postgresql:///archon_legacy?host=/var/run/postgresql'
export NEW_DATABASE_URL='postgresql:///new_archon?host=/var/run/postgresql'
export DATABASE_URL="$NEW_DATABASE_URL"
cd backend
```
Run §4/§5 from this shell. Sequencing guard: step 2's first boot already ran
`init_db` as `new_archon`, so tables exist with the right owner — never let this
`postgres` shell be the one that creates them (a fresh-DB `init_db` as postgres
would leave tables the app can't write).

### 4 · Leg A — vekn-first (#115): merge the dump onto the synced corpus
```sh
uv run --no-sync python scripts/migrate_from_archon.py --merge --backup-dir /var/backups/postgres
```
(`--merge` pre-dumps the NEW DB to the backup dir, keeps last 7.) Rich archon
data merges INTO the vekn-created copies — their uid survives. Then:
```sh
psql -d new_archon -c "SELECT \"full\"->'external_ids'->>'vekn' AS evt, count(*)
  FROM objects WHERE type='tournament' AND deleted_at IS NULL
    AND \"full\"->'external_ids'->>'vekn' IS NOT NULL
  GROUP BY 1 HAVING count(*) > 1;"     -- expect 0 rows: ≤1 live tournament per vekn id
```
Eyeball the merge summary; both-rich conflicts are loud in the output — expect
none on clean data. Run the **§7 audit now** (configuration 1 of 2).

### 5 · Leg B — archon-first (#115) → the state beta keeps
```sh
sudo systemctl stop new-archon-backend     # from the deploy user: deterministic window
# back in the postgres workbench shell (§3), under backend/:
uv run --no-sync python scripts/migrate_from_archon.py --truncate   # full re-seed from the dump
uv run --no-sync python scripts/migrate_validate.py                 # parity + orphans + spot-checks (nonzero exit = hard fail)
uv run --no-sync python scripts/check_merge.py --snapshot           # ETL-only baseline (/tmp/merge_baseline.json)
sudo systemctl start new-archon-backend    # startup sync chain runs again — rich-guard now in play
journalctl -u new-archon-backend -f        # wait for member+tournament sync completion
uv run --no-sync python scripts/check_merge.py --check              # roles untouched, no vekn-id dupes, rounds intact
uv run --no-sync python scripts/migrate_from_archon.py --merge --backup-dir /var/backups/postgres   # idempotence: ≈ all unchanged
```
`--limit N` on the ETL first for a quick smoke if desired. Expected: 0 ETL
errors; roles seeded via the old-archon mapping (`Admin`→IC, `Playtester`→PT);
`check_merge --check` green (ETL-seeded PROTECTED_ROLES surviving the sync is
the regression net for "no sync ever writes roles"); the rich-guard
(`vekn_tournament_sync.py` ≈:332) keeps rounds/finals intact; the final merge
pass reports ≈ everything unchanged. Re-run the dup-invariant query from §4,
then the **§7 audit again** (configuration 2 of 2). This ETL-seeded,
vekn-reconciled state is what beta keeps.

### 6 · Login, bot OAuth client, admin panel
1. Log in at `https://new.archon.krcg.org` — Discord login matches your migrated
   account through the imported discord auth method (other migrated auth methods
   work too). Confirm your roles came through (IC from old-archon `Admin`).
2. As IC, Profile → **Developer** section (visible to IC/DEV): register the
   bot's OAuth client with redirect `https://bot.archon.krcg.org/oauth/callback`
   — the client_secret is shown **once**.
3. Put `vault_bot_oauth_client_id/secret` into the vault
   (`uv run --project .. ansible-vault edit inventories/beta/group_vars/vault.yml`),
   re-run `just deploy-beta` — the bot env re-renders and the service restarts.
4. Install the beta Discord app on a test guild; exercise a bot login + command.
5. Profile → **Admin** section: the #123 status panel shows last job outcomes;
   "Run now" on the VEKN syncs exercises the Bearer-authed endpoints end-to-end.
   curl equivalent (token from the app's network tab — `Authorization` header):
   ```sh
   curl -X POST https://new.archon.krcg.org/admin/sync-vekn             -H "Authorization: Bearer <jwt>"
   curl -X POST https://new.archon.krcg.org/admin/sync-vekn-tournaments -H "Authorization: Bearer <jwt>"
   curl        https://new.archon.krcg.org/admin/vekn-status            -H "Authorization: Bearer <jwt>"
   ```
   (Paths are `/admin/*` — there is no `/api/admin/*`. vekn-status state is
   in-process and resets on restart.)

### 7 · #114 push audit — THE GATE (read-only; run after EACH leg)
All three `batch_push` selection queries must return **0**. Source of truth:
`vekn_push.py` ≈:335 (events), ≈:351 (results), ≈:390 (members, inline).
`sudo -u postgres psql -d new_archon`:
```sql
-- 1. members owed a push  (ETL stamps vekn_synced=true → expect 0)
SELECT count(*) FROM objects
 WHERE type='user' AND "full"->>'vekn_id' IS NOT NULL
   AND ("full"->>'vekn_synced')::boolean = false;

-- 2. tournaments owed a calendar event  (ETL stamps vekn_pushed_at → expect 0)
SELECT count(*) FROM objects
 WHERE type='tournament' AND "full"->>'state' <> 'Planned' AND deleted_at IS NULL
   AND ("full"->'external_ids'->>'vekn') IS NULL
   AND "full"->>'vekn_pushed_at' IS NULL
   AND "full"->>'name' IS NOT NULL AND "full"->>'start' IS NOT NULL;

-- 3. tournaments owed a results push  (imports stamped; expect 0)
SELECT count(*) FROM objects
 WHERE type='tournament' AND "full"->>'state'='Finished' AND deleted_at IS NULL
   AND "full"->>'vekn_pushed_at' IS NULL
   AND ("full"->'external_ids'->>'vekn') IS NOT NULL
   AND jsonb_array_length(COALESCE("full"->'rounds','[]'::jsonb)) > 0;
```
**All three = 0 → #114 confirmed on real data → #91 gate satisfied.** Any
nonzero row is a finding: sync-created vs unstamped-import (a bug). Caveats:
run **before** creating in-app test events — a hand-made non-Planned tournament
legitimately matches query 2 (that's exactly what prod *should* push; not a
stamping bug). `VEKN_PUSH=false` keeps beta inert regardless — the audit
validates the stamping that prod (#39, push on) relies on.

**Stop condition — this is the #39 gate.** Any query-2/3 row that traces to an
ETL-migrated import is a stamping bug: **block #39 and fix the ETL before
cutover** (prod runs `VEKN_PUSH=true`, so an unstamped import there re-submits
results vekn.net already ratified — thousands of rows). A query-1 user with
`vekn_synced=false` is likewise a bug *unless* it's a brand-new member the live
sync just created and hasn't stamped yet — re-run the audit once the sync chain
settles before calling it. Do not proceed to #39 until all three read 0 on the
state beta keeps (post-§5 leg B).

### 8 · #80 clean-install check
Already half-done in §2 (`/api/cards` served from the installed wheel). Confirm
in addition: service entrypoint is `backend.src.main:app` (deploy-beta.yml),
no path/resource errors in `journalctl -u new-archon-backend`, and snapshots
appear under `/var/lib/new_archon/snapshots` after the startup chain.

## Cleanup (after the gate)
```sh
sudo -u postgres dropdb archon_legacy      # or keep for #39 rehearsal — note the daily
                                           # pg-backup dumps EVERY non-template DB (restic offsite incl.)
sudo rm -rf ~postgres/archon-vibe          # the ETL workbench, when no longer wanted
```

## Optional · wire the CI deploy path (`deploy.yml` workflow)
From the server-setup repo: `just sync` pushes `DEPLOY_HOST`/`DEPLOY_HOST_KEY`
into archon-vibe's `beta` environment (mapping already in `deploy-targets.yml`),
`just sync-key ~/.ssh/deploy` pushes `DEPLOY_SSH_KEY`; then set the
`ANSIBLE_VAULT_PASSWORD` secret + required reviewers on the environment. Today
the `beta` env exists but is **empty**. (The workflow's prod input now binds to
the existing `production` environment — the former `prod` naming mismatch is
fixed.)

## Done when
All of: first Release published with all six assets · deploy green from CI
artifacts · startup sync clean · leg A merge clean (dup-invariant holds) ·
leg B: ETL 0-error, `migrate_validate` green, `check_merge --check` green,
merge idempotent · **§7 audit all-zero after both legs** · #80 clean · login +
bot OAuth client + admin panel exercised. Then close #91 and unblock #39.
