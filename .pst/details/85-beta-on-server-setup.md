# #85 — archon-vibe beta as a server-setup deploy target

## Model (owner)
- **beta → frankfurt (57.129.110.107)**: rides the `../server-setup` pipeline as
  its single deploy target. server-setup provisions (base/ssh/ufw/tuning/PG/
  observability/backups); archon ships only the app via `nginx_site` + `postgres_db`,
  the `deploy` user, and `DEPLOY_SSH_KEY` (populated by server-setup `just sync`/`sync-key`).
- **prod → vekn.net**: a completely independent standalone target keeping archon's
  own roles (common/system_upgrade/postgresql-PG17/nginx_tls). No server-setup dep.

## Decisions
- Beta app domain `new.archon.krcg.org`, bot domain `bot.archon.krcg.org`.
- `service_name = new_archon` (flows to nginx_site tag + postgres_db name; distinct
  from the old `archon` already on frankfurt).
- Extend server-setup `deploy-targets.yml` with a per-target **env** field so
  `just sync` pushes archon-vibe's vars to its **beta** environment (not the default
  `production`). [#89]

## #86 — galaxy wiring (done)
server-setup's roles live under `server-setup/roles/`, so the README's
`role: server-setup/nginx_site` does **not** resolve. Verified working form:
- `make galaxy` installs server-setup into git-ignored `ansible/galaxy_roles/`
  (`ansible-galaxy role install -r requirements.yml -p galaxy_roles`).
- `ansible.cfg` `roles_path = roles:galaxy_roles/server-setup/roles` → reference the
  roles plainly as `nginx_site` / `postgres_db`.
- `version: main` in requirements.yml (pin to a tag/SHA once server-setup releases).
- TODO: fix server-setup's README consumer example to this form (do with #89).

## #87 — manage_nginx gate (done)
`static_site` + `discord_bot` vhost tasks now `when: r.manage_nginx | default(true)`,
and their nginx-only asserts (server_name / backend_port) are conditional on it.
Prod is unchanged (defaults true); beta passes `manage_nginx: false` and uses nginx_site.

## #88 — beta playbook (done: playbooks/deploy-beta.yml)
Key finding: **nginx_site `spa` mode immutable-caches `*.js`**, which would cache the
PWA **service worker** → broken updates. So the **frontend keeps archon's own
`static_site` (PWA-correct vhost) + `nginx_tls` (cert)**; only the **bot** uses
`nginx_site` (`proxy` mode — a plain reverse proxy, perfect fit + journald tag).

Compose (deploy-beta.yml): shared self-fetch (#82) + `tasks/app_user.yml` (creates
the `new_archon` runtime user/dirs — server-setup doesn't) → `postgres_db`
(become_user postgres) → `nginx_tls` (main cert) → `fastapi_backend` (service) →
`static_site` (frontend vhost+dist, manage_nginx default) → `discord_bot`
(manage_nginx=false, service only) → `nginx_site` proxy (bot vhost, name
`new_archon_bot`).

- **Peer auth**: runtime user == db role == `new_archon` → Postgres connects over
  the unix socket by peer; the `DATABASE_URL` password is vestigial.
- **new_archon namespace** everywhere (user/group, /opt/new_archon,
  /var/www/new_archon, /etc/new_archon, /var/lib/new_archon, services
  new-archon-backend / new-archon-bot, db new_archon, domain new.archon.krcg.org)
  to avoid colliding with the legacy `archon` on frankfurt.
- Shared self-fetch extracted to `vars/release_artifacts.yml` + `tasks/fetch_release.yml`
  (prod deploy.yml now imports the same — no duplication).
- Beta inventory: host `frankfurt` 57.129.110.107, `ansible_user=deploy`.
- `make deploy-beta` → deploy-beta.yml; `galaxy_roles/` excluded from ansible-lint.

### Deploy prerequisites (before first run)
- DNS: `new.archon.krcg.org` + `bot.archon.krcg.org` → 57.129.110.107 (certbot HTTP-01).
- `deploy` user key authorized on frankfurt; `make galaxy` to install server-setup.
- Vault password available; `just sync` / `sync-key` to populate the GitHub env (#89).

## #89 — CI workflow rework (done)
archon `.github/workflows/deploy.yml`: secret `DEPLOY_SSH_KEY` (was SSH_PRIVATE_KEY);
the Deploy step selects the playbook by env (beta → deploy-beta.yml, prod →
deploy.yml); `ansible_user=deploy` comes from the beta inventory. README's CI-deploy
section updated to match (DEPLOY_SSH_KEY, deploy user, `just sync`/`sync-key`).

server-setup (separate repo, uncommitted there):
- `deploy-targets.yml`: `vtes-biased/archon-vibe: {host: frankfurt, env: beta}` — the
  value is now either a hostname (env defaults `production`) or a `{host, env}` map.
- `justfile` `sync`/`sync-key`: push DEPLOY_* to each target's configured env
  (`(.value.env // "production")`), so archon-vibe's land in its **beta** env.

Flagged, NOT changed (uncertain vs other consumers): server-setup's README documents
`role: server-setup/nginx_site`, which doesn't resolve (roles live under
`server-setup/roles/`); archon uses the verified form (see #86).
