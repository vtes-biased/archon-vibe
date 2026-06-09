# Archon Ansible deploy

Provisions and deploys `archon-vibe` (FastAPI backend, Svelte/Vite PWA frontend,
Discord bot, PostgreSQL 17, nginx + Let's Encrypt) to one of two targets:

| env  | host                     | main domain             | bot domain                 |
|------|--------------------------|-------------------------|----------------------------|
| beta | server-setup (frankfurt) | `new.archon.krcg.org`   | `bot.archon.krcg.org`      |
| prod | `vekn.net` VPS           | `archon.vekn.net`       | `bot.archon.vekn.net`      |

Build strategy: all deployable artifacts (Rust engine wheel, backend wheel, bot
wheel, frontend static dist) are built **by GitHub Actions** (`.github/workflows/
release-artifacts.yml`) and attached to the published Release. The **deploy
playbook fetches them itself** (a `delegate_to: localhost` pre_task downloads the
Release assets via the GitHub API — no `gh` CLI), so CI is the single source of
deployed builds and the servers never run `cargo`, `maturin`, `npm`, or `uv
build`. `just deploy-*` (run from `ansible/`) is a friendly wrapper over
`ansible-playbook`, and `ansible-playbook playbooks/deploy.yml` is self-contained
(runs the same from a laptop or a CI runner).

The `just build-*` recipes still build everything locally for development, and
`SOURCE=local just deploy-<env>` deploys a local build instead of the Release
(handy for testing an un-released change on beta).

Runtime Python is managed by **uv** (same version on both hosts, pinned via
`python_version` in `group_vars/all.yml` — currently `3.13`). uv downloads
python-build-standalone binaries into `/opt/uv/python`, independent of the
distro. No third-party PPAs; no abi3 tricks in the Rust engine build.

PostgreSQL 17 is installed from the official PGDG apt repository (maintained
upstream by the PostgreSQL Global Development Group) so both environments run
the same major version.

## Prerequisites

On your workstation:
- Python 3.13 + `uv` (`brew install uv`)
- `uv sync --group dev` from the repo root — installs pinned `ansible-core`,
  `ansible-lint`, `yamllint` and everything else the deploy recipes need.
- `just` (`brew install just`) — the ansible task runner (recipes in `ansible/justfile`).
- Network access to GitHub (the deploy playbook downloads Release assets).
- Only for `SOURCE=local` builds: Docker Desktop (manylinux PyO3 wheel),
  Node 22 (matches CI), and `wasm-pack` (frontend WASM engine).

On each server (first time only, before `just bootstrap-<env>`):
- A non-root admin user with passwordless sudo (see `inventories/<env>/hosts.ini`
  — `ansible_user` must be that account).
- SSH key auth already set up.
- DNS A/AAAA records pointing at the server for both the main domain and the
  `bot.<main-domain>` subdomain.

## First-time setup

```bash
cd ansible
just galaxy                               # ansible collections + server-setup roles

# Create the vault password file (git-ignored) and encrypt the vault
echo '<your vault password>' > .vault_pass
chmod 600 .vault_pass

# Edit and encrypt the placeholder secrets
ansible-vault edit inventories/beta/group_vars/vault.yml
ansible-vault edit inventories/prod/group_vars/vault.yml

just bootstrap-beta                        # provision beta end-to-end
```

## Routine updates

```bash
just deploy-beta                           # deploy latest Release to beta
just deploy-prod                           # same for prod
RELEASE_TAG=v1.2.3 just deploy-prod        # deploy a specific Release
SOURCE=local just deploy-beta              # build locally + deploy (un-released change)
```

The playbook prints the concrete tag it resolved (so `latest` is auditable) and,
for a public repo, needs no auth — set `GITHUB_TOKEN` in the environment only to
lift the API rate limit. Note: re-running the release workflow re-uploads
(`--clobber`) a release's attached artifacts — treat a published release's assets
as the deployed bytes and cut a new release rather than re-running to change what
ships.

## Deploy from CI (GitHub Actions)

`.github/workflows/deploy.yml` runs the deploy from a runner — `beta` →
`deploy-beta.yml` (server-setup host), `prod` → `deploy.yml` (standalone). It is
**manual-only** (`workflow_dispatch`, pick `beta`/`prod` + an optional
`release_tag`) and **approval-gated**: the job binds to a GitHub Environment whose
required-reviewer rule pauses the run until someone approves. Nothing
auto-deploys.

For **beta**, server-setup owns the config — `just sync` (from the server-setup
repo) pushes `DEPLOY_HOST` + `DEPLOY_HOST_KEY` and `just sync-key ~/.ssh/deploy`
pushes `DEPLOY_SSH_KEY` to this repo's `beta` environment. One-time setup:

1. **Environments** (Settings → Environments): create `beta` and `prod`, each with
   **Required reviewers** enabled.
2. **Per-environment variables** (Variables — not sensitive; `just sync` sets these
   for beta):
   - `DEPLOY_HOST` — the real server host/IP (the committed inventory ships a
     placeholder; CI overrides it via `-e ansible_host`).
   - `DEPLOY_HOST_KEY` — a `known_hosts` line for `DEPLOY_HOST` (e.g.
     `ssh-keyscan "$DEPLOY_HOST"`); its host field must match `DEPLOY_HOST`
     **exactly** (same hostname-or-IP form) — a mismatch is a hard connect failure
     since `host_key_checking` is on.
3. **Per-environment secrets** (Secrets):
   - `DEPLOY_SSH_KEY` — the deploy keypair's private half (LF newlines); its public
     half is in the deploy user's `authorized_keys` (`just sync-key` for beta).
   - `ANSIBLE_VAULT_PASSWORD` — the vault password for that env's `vault.yml`.
4. The VPS must accept SSH from GitHub-hosted runner IPs (port 22 open).

`prod` deploys require an explicit `release_tag` (a pre-check fails a blank prod
dispatch before the approval gate), so the reviewer sees the exact tag being
shipped; `beta` allows blank (= latest).

## System updates / kernel upgrades

```bash
just upgrade-beta                          # apt upgrade; warns if reboot needed
REBOOT=1 just upgrade-beta                 # also reboot if /var/run/reboot-required
FULL=1 REBOOT=1 just upgrade-beta          # dist-upgrade + reboot (major kernel bumps)
```

The `system_upgrade` role stops `archon-backend` + `archon-bot` before rebooting
and restarts + health-checks them afterwards.

## One-shot PG16 → PG17 migration (prod only)

Prod currently runs PostgreSQL 16. Run this **once** after a full on-disk backup:

```bash
just migrate-postgres-prod
```

The playbook takes a `pg_dumpall` backup, stands up PG17 in parallel on port
5433, restores, swaps the ports, and restarts archon services.

## Layout

```
ansible/
├── ansible.cfg           # defaults (roles_path, vault, SSH multiplex)
├── requirements.yml      # collection + server-setup role pins
├── justfile              # deploy + local-build recipes (wraps ansible-playbook)
├── galaxy_roles/         # server-setup roles installed by `just galaxy` (git-ignored)
├── inventories/<env>/    # hosts.ini + group_vars/{all.yml, vault.yml}
├── playbooks/
│   ├── bootstrap.yml     # common role only
│   ├── database.yml      # postgresql role
│   ├── deploy.yml        # prod: backend + frontend + bot (standalone)
│   ├── deploy-beta.yml   # beta: app on the server-setup foundation (frankfurt)
│   ├── upgrade.yml       # system_upgrade role
│   ├── migrate_postgres.yml   # PG16 -> PG17 migration (prod)
│   └── site.yml          # bootstrap + database + deploy
├── tasks/                # fetch_release.yml (shared self-fetch) + app_user.yml (beta)
├── vars/                 # release_artifacts.yml (shared artifact resolution)
├── roles/
│   ├── common/           # base packages, admin user, ufw, unattended-upgrades
│   ├── system_upgrade/   # apt upgrade + safe reboot flow
│   ├── postgresql/       # PGDG repo, PG17, db + user + hba + tunings
│   ├── nginx_tls/        # http vhost + certbot webroot + renewal hook
│   ├── fastapi_backend/  # wheel install, venv, systemd (localhost only)
│   ├── static_site/      # dist rsync, https vhost, backend proxy, SSE
│   └── discord_bot/      # wheel install, venv, systemd, bot.<domain> vhost
└── build/                # fetched/built artifacts (git-ignored)
```
