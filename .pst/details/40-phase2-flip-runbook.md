# Phase 2 flip — runbook (#40)

Green light 2026-08-06, flip announced for **2026-08-07** (comms: `40-flip-comm.md`).

**Executed 2026-08-07** — beta first, then prod. Corrections found while running it
are folded in below. Post-flip follow-ups (#41, #521, #346, #42) are unchanged.

**Owner decision, deviates from #40/#42 as filed:** legacy archon is *shut down*,
not re-hosted read-only at `old.archon.vekn.net`. No `old.` DNS record, no `old.`
vhost. The safety net is the pre-flip `pg_dump` + `archondb` left intact on the box
(legacy is re-deployable from `~/Developer/archon` in minutes if ever needed).

Same operation on pre-prod: `archon.krcg.org` (frankfurt) stops serving legacy beta
and starts serving archon-vibe beta. **Do beta first — it rehearses both traps.**

---

## The three traps (why the order below is what it is)

1. **The nightly legacy merge must be disabled at the flip, not at Phase 4.**
   `migrate_from_archon --merge` rebuilds legacy-originated tournaments *wholesale*
   from `archondb` ("old archon wins", ~line 1160) — there is no
   `local_modifications` guard on tournament rich data. Left armed against a frozen
   legacy DB it silently reverts every post-flip edit made in the new app on those
   513 tournaments, every night at 04:00. It is also what blocks #346 and #521.
   `legacy_sync_enabled: false` only makes ansible *skip* the role — the installed
   timer keeps firing, so it must be disabled on the box.

2. **Certbot renewal webroot mismatch on both boxes.** The `archon.vekn.net` /
   `archon.krcg.org` certs were issued by the *legacy* tooling with
   `--webroot-path /usr/share/nginx/html` — **both** boxes, verified on each
   2026-08-07 (the earlier `-w /var/www/certbot` guess for beta was wrong; that
   path isn't in play). Only the legacy-issued cert is affected: `bot.` and `new.`
   were issued by `nginx_tls` and already renew from `/var/www/acme`. After the flip the
   `:80` vhost is archon-vibe's `nginx_tls/templates/http.conf.j2`, which serves
   `/.well-known/acme-challenge/` from **`/var/www/acme`** and 301s everything else.
   `certbot renew` then fails ~60 days later, silently. Fix the renewal conf (or
   pass `r.acme_webroot`) and prove it with `certbot renew --dry-run` in the window.

3. **Discord redirect URIs are pre-flip work.** `DISCORD_REDIRECT_URI` derives from
   `site_url_base`, so the moment the deploy lands it is
   `https://archon.vekn.net/auth/discord/callback`. If that URI is not already
   whitelisted on app `1495034668469194864`, every Discord login breaks. Adding a
   redirect URI is additive and harmless while Phase 1 still runs — do it the day
   before. Same for the beta app on `archon.krcg.org`.

Non-trap, verified: legacy has **no service worker** and sets **no HSTS**, so no
stale-client residue on the old origin.

**Correction (2026-08-07, beta box):** the filenames *do* collide on frankfurt.
Legacy beta there is the unit `archon.krcg.org.service` (not `archon_beta`) and its
vhosts are `/etc/nginx/sites-enabled/archon.krcg.org.{http,https}.conf` — exactly
the paths `nginx_tls` (`{{ r.server_name }}.http.conf`) and `static_site`
(`.https.conf`) write once `domain_main` flips. So the deploy would overwrite them
in place, and if either is a symlink into `sites-available` the write lands
somewhere unintended. Move the legacy confs aside *before* deploying rather than
letting the template land on them.

**Prod does not have this problem** (box state, 2026-08-07): legacy there really is
`archon_web.{http,https}.conf`, regular files, no symlinks, and `sites-available`
holds only `default`. The deploy writes the *new* filenames
`archon.vekn.net.{http,https}.conf`, so step 6 below is a plain removal of the
legacy vhost, not a collision.

---

## Pre-flip (T-1)

- [ ] **Discord portal**, app `1495034668469194864`: add redirect URI
      `https://archon.vekn.net/auth/discord/callback`; Linked Roles verification URL
      → `https://archon.vekn.net/auth/discord/authorize`; ToS/Privacy →
      `https://archon.vekn.net/legal/terms` / `/legal/privacy` (#24). Beta app: add
      `https://archon.krcg.org/auth/discord/callback`.
- [ ] **Cut the release.** `just release patch` → `v0.4.15` (v0.4.14 predates the
      two TWDA fixes). Wait for CI green (e2e → release → artifacts).
- [ ] **Rehearse on beta** (section below) with that tag.
- [ ] **Box state check** (prod):
      ```
      ls /etc/nginx/sites-enabled/
      sudo certbot certificates
      sudo grep -R webroot /etc/letsencrypt/renewal/archon.vekn.net.conf
      systemctl list-timers | grep archon
      sudo journalctl -u archon_web --since -30d | grep ' /api' | head   # who consumes legacy /api?
      ```
      The legacy `/api` was CORS-`*` open; the new stack has no public read API
      (#97/#99), so any external consumer found here breaks at the flip — decide
      then, don't discover it after.
- [ ] **Send the Princes announcement** (`40-flip-comm.md`, approved).

## Flip window — prod (~30 min, announced downtime)

1. **Freeze legacy** (also stops its in-app VEKN sync *and* push):
   `sudo systemctl disable --now archon_web`
2. **Insurance dump:**
   `sudo -u postgres pg_dump -Fc archondb -f /var/backups/postgres/archondb-preflip-$(date +%F).dump`
   — then copy it off-box.
3. **Final legacy merge:** `sudo systemctl start archon-legacy-sync.service`,
   follow `journalctl -u archon-legacy-sync -f`, check the summary (expect mostly
   unchanged + echo-skips).
4. **Disable the merge, permanently:** `sudo systemctl disable --now archon-legacy-sync.timer`
   (trap 1). Also set `legacy_sync_enabled: false` in `inventories/prod/group_vars/all/vars.yml`
   so a later deploy doesn't re-render it.
5. **Wall-clock normalization** (#527) — report, then apply. The script needs a
   DSN (`--dsn` or `DATABASE_URL`); the docstring's bare `python …` invocation
   supplies neither and exits on `--dsn or DATABASE_URL is required`. Borrow the
   backend's own `EnvironmentFile` so nothing parses the password by hand and it
   never lands in `ps`:
   ```
   sudo systemd-run --uid=archon --pipe --wait \
     -p EnvironmentFile=/etc/archon/archon-backend.env \
     /opt/archon/backend/.venv/bin/python \
     /opt/archon/backend/scripts/normalize_wall_clock.py           # report
   … same, with --apply appended
   ```
   Must run after the final merge/sync and before the ratings recompute.
6. **Drop the legacy vhosts:**
   `sudo mv /etc/nginx/sites-enabled/archon_web.{http,https}.conf /root/`
   `sudo nginx -t && sudo systemctl reload nginx`
   (Optional nicety: drop a static 503 at
   `/etc/nginx/sites-enabled/archon.vekn.net.https.conf` — the deploy's `static_site`
   role writes that exact path, so the maintenance page is replaced automatically.)
7. **Flip the deploy.** In `ansible/justfile` set `phase1_override := ""` (keep
   `inventories/prod-phase1-override.yml` on disk until #42 — it is the rollback),
   commit, then:
   `cd ansible && RELEASE_TAG=v0.4.15 just deploy-prod`   ← full deploy, **not** `QUICK=1`
   (nginx/TLS/env/units all change). This renders `archon.vekn.net.{http,https}.conf`,
   rewrites `SITE_URL_BASE` / `DISCORD_REDIRECT_URI` / `WEBAUTHN_RP_ID` / the bot's
   `ARCHON_FRONTEND_URL`, and turns `VEKN_PUSH` back on via the vars.yml default.
   Certbot is skipped (`creates:` — the cert already exists).
8. **Ratings recompute — free.** `main.py` fires the full sync chain on startup
   (member → tournament → TWDA → `run_rating_recompute` → snapshot), so the
   backend restart in step 7 *is* the recompute, correctly ordered after step 5.
   Confirm in the log rather than triggering anything.
9. **Fix cert renewal** (trap 2): point `webroot_path` + `[[webroot_map]]` in
   `/etc/letsencrypt/renewal/archon.vekn.net.conf` at `/var/www/acme`, then
   `sudo certbot renew --dry-run`.
10. **Smoke:** `curl -I https://archon.vekn.net` (200 + valid cert) ·
    `/api/cards` · SSE stream · Discord login · magic-link login · bot vhost ·
    calendar feed · a tournament page + its og stub (Discord unfurl).

**Keep `new.archon.vekn.net` serving** — same dist, same backend, so Phase-1
bookmarks and calendar subscriptions don't break. Only OAuth/passkeys now anchor on
the plain domain. Retire or 301 it later, not in this window.

**Rollback:** restore the two `archon_web.*` confs, `systemctl enable --now archon_web`,
`nginx -t && reload` (the new stack's vhost loses to nothing — remove
`archon.vekn.net.*` confs too), and redeploy with the phase-1 override restored.
Writes made in the new app during the window stay in the new DB.

## Flip window — beta / pre-prod (`archon.krcg.org`, frankfurt)

1. `ansible/inventories/beta/group_vars/all/vars.yml`: `domain_main: archon.krcg.org`
   (`domain_bot` unchanged). `site_url_base` / `WEBAUTHN_RP_ID` / redirect URIs derive.
2. Stop legacy beta: `sudo systemctl disable --now archon.krcg.org.service`, then
   `sudo mv /etc/nginx/sites-enabled/archon.krcg.org.{http,https}.conf /root/` and
   `sudo nginx -t && sudo systemctl reload nginx`. Ports don't clash (legacy 8007,
   archon-vibe beta 8008) — this is about the vhost, and about not templating over
   legacy's files (see the correction above). Legacy beta's `archondb` stays.
3. `cd ansible && RELEASE_TAG=v0.4.15 just deploy-beta` (full, not `QUICK=1`).
4. Cert renewal fix: in `/etc/letsencrypt/renewal/archon.krcg.org.conf` replace
   `/usr/share/nginx/html` → `/var/www/acme` (both `webroot_path` and the
   `[[webroot_map]]` entry — a single `sed s#…#…#g` on that literal path does it),
   then `certbot renew --dry-run --cert-name archon.krcg.org`.
5. Smoke as above. `new.archon.krcg.org` keeps working — leave it.

## After the flip

- #41 Phase 3: prod-guild bot install, passkey opt-in, monitoring 2–4 weeks.
- #521: `dedup_tournaments.py --probe-vekn` on prod, review, `--apply` (safe now
  that the merge is off) — then tell the "Draft that Was Promised" organizer.
- #346: delete the empty round 4 on legacy event 13379, clear its `vekn_pushed_at`,
  let the hourly `batch_push` upload results.
- #42 decommission: what's left after this runbook is the final archive dump, the
  `archon_web` unit removal, archiving the old repo, and cold-storing
  `tournament_events`. The sync-disable and service-stop happen here, in step 1/4.
