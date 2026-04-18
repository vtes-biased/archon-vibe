# Archon Ansible deploy

Provisions and deploys `archon-vibe` (FastAPI backend, Svelte/Vite PWA frontend,
Discord bot, PostgreSQL 17, nginx + Let's Encrypt) to one of two targets:

| env  | host                 | main domain          | bot domain                 |
|------|----------------------|----------------------|----------------------------|
| beta | `krcg.org` VPS       | `archon.krcg.org`    | `bot.archon.krcg.org`      |
| prod | `vekn.net` VPS       | `archon.vekn.net`    | `bot.archon.vekn.net`      |

Build strategy: all artifacts (Rust engine wheel, backend wheel, bot source,
frontend static dist) are built **locally on your workstation** and rsynced to
the server. The servers never run `cargo`, `maturin`, `npm`, or `uv build`.

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
- Docker Desktop (for the manylinux PyO3 wheel build)
- Node 20+ (`brew install node`)
- Ansible 2.17+ (`brew install ansible`)
- `yamllint` + `ansible-lint` for `make lint`

On each server (first time only, before `make bootstrap-<env>`):
- A non-root admin user with passwordless sudo (see `inventories/<env>/hosts.ini`
  — `ansible_user` must be that account).
- SSH key auth already set up.
- DNS A/AAAA records pointing at the server for both the main domain and the
  `bot.<main-domain>` subdomain.

## First-time setup

```bash
cd ansible
make galaxy                               # install ansible collections

# Create the vault password file (git-ignored) and encrypt the vault
echo '<your vault password>' > .vault_pass
chmod 600 .vault_pass

# Edit and encrypt the placeholder secrets
ansible-vault edit inventories/beta/group_vars/vault.yml
ansible-vault edit inventories/prod/group_vars/vault.yml

make bootstrap-beta                        # provision beta end-to-end
```

## Routine updates

```bash
make deploy-beta                           # rebuild artifacts + deploy to beta
make deploy-prod                           # same for prod
```

## System updates / kernel upgrades

```bash
make upgrade-beta                          # apt upgrade; warns if reboot needed
make upgrade-beta REBOOT=1                 # also reboot if /var/run/reboot-required
make upgrade-beta FULL=1 REBOOT=1          # dist-upgrade + reboot (major kernel bumps)
```

The `system_upgrade` role stops `archon-backend` + `archon-bot` before rebooting
and restarts + health-checks them afterwards.

## One-shot PG16 → PG17 migration (prod only)

Prod currently runs PostgreSQL 16. Run this **once** after a full on-disk backup:

```bash
make migrate-postgres-prod
```

The playbook takes a `pg_dumpall` backup, stands up PG17 in parallel on port
5433, restores, swaps the ports, and restarts archon services.

## Layout

```
ansible/
├── ansible.cfg           # defaults (inventory path, vault, SSH multiplex)
├── requirements.yml      # collection pins
├── Makefile              # local build + deploy entrypoints
├── inventories/<env>/    # hosts.ini + group_vars/{all.yml, vault.yml}
├── playbooks/
│   ├── bootstrap.yml     # common role only
│   ├── database.yml      # postgresql role
│   ├── deploy.yml        # backend + frontend + bot
│   ├── upgrade.yml       # system_upgrade role
│   ├── migrate_postgres.yml   # PG16 -> PG17 migration (prod)
│   └── site.yml          # bootstrap + database + deploy
├── roles/
│   ├── common/           # base packages, admin user, ufw, unattended-upgrades
│   ├── system_upgrade/   # apt upgrade + safe reboot flow
│   ├── postgresql/       # PGDG repo, PG17, db + user + hba + tunings
│   ├── nginx_tls/        # http vhost + certbot webroot + renewal hook
│   ├── fastapi_backend/  # wheel install, venv, systemd (localhost only)
│   ├── static_site/      # dist rsync, https vhost, backend proxy, SSE
│   └── discord_bot/      # src rsync, venv, systemd, bot.<domain> vhost
└── build/                # local build artifacts (git-ignored)
```
