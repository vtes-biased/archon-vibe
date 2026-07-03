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
`python_version` in `group_vars/all/vars.yml` — currently `3.13`). uv downloads
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

On each server (first time only):
- **prod** (before `just bootstrap-prod`): a non-root admin user with
  passwordless sudo (see `inventories/prod/hosts.ini` — `ansible_user` must be
  that account) and SSH key auth.
- **beta**: nothing to prepare — the foundation, `deploy` user included, comes
  from server-setup.
- DNS A/AAAA records pointing at the server for both the main domain and the
  `bot.<main-domain>` subdomain (certbot HTTP-01 needs them before deploy).

## First-time setup

```bash
cd ansible
just galaxy                               # ansible collections (incl. server-setup foundation)

# Vault password: each env's lives age-encrypted in secrets/<env>.vault-pass.age and
# the deploy recipes decrypt it for you — see "Vault passwords" below for adding your
# key, creating/rotating a password, and editing vault.yml.

# beta (frankfurt) is server-setup-provisioned — there is no beta bootstrap.
# `just deploy-beta` is the only beta entrypoint (it creates the app user and
# the DB/role itself, via server-setup's postgres_db role).
just deploy-beta

just bootstrap-prod                        # prod: full provision (archon's own roles)
```

## Vault passwords

Each env (`beta`, `prod`) has its **own** ansible-vault password. We don't pass
them around by hand — each is stored **in the repo, age-encrypted**, decryptable
only by the admins whose public keys are listed in `secrets/age-recipients.txt`:

```
ansible/secrets/
├── age-recipients.txt   # admins' PUBLIC keys — decrypt BOTH env passwords
├── beta.vault-pass.age  # beta vault password, age-encrypted to that list
└── prod.vault-pass.age  # prod vault password, age-encrypted to that list
```

Both the recipients list (public keys) and the `*.age` files (ciphertext) are
**safe to commit**; `secrets/.gitignore` whitelists only those, so a plaintext
password can't slip in. Install [`age`](https://github.com/FiloSottile/age) first:
`brew install age` / `apt install age` / `winget install FiloSottile.age`.

### Use it (local deploy)

Decrypt the env's password into its git-ignored `.<env>.vault_pass` with **your**
age/SSH key, then run the deploy — the `just` deploy/provision recipes default
`ANSIBLE_VAULT_PASSWORD_FILE` to that per-env file for you:

```bash
cd ansible
age -d -i ~/.ssh/id_ed25519 -o .beta.vault_pass secrets/beta.vault-pass.age   # fill .beta.vault_pass
just deploy-beta            # recipe points ansible-vault at ./.beta.vault_pass
rm -f .beta.vault_pass      # plaintext on disk; git-ignored, but remove when done
```

Choose your identity with `-i` (`~/.ssh/id_ed25519`, `~/.ssh/id_rsa`, or an age key
like `~/.config/age/keys.txt`). Same for prod (`prod.vault-pass.age` →
`.prod.vault_pass` → `just deploy-prod`). For a one-off `ansible-vault` command (not
a recipe), point it at the same file: `ANSIBLE_VAULT_PASSWORD_FILE=.beta.vault_pass
ansible-vault edit inventories/beta/group_vars/all/vault.yml`.

> **A set `ANSIBLE_VAULT_PASSWORD_FILE` overrides this.** The recipe default only
> kicks in when the variable is *unset* — an exported value (yours or CI's) is
> respected as-is, and the env var also beats any `ansible.cfg` `vault_password_file`.
> So keep your *global* default in `~/.ansible.cfg` (`[defaults]` → `vault_password_file`),
> not a shell `export`, or it'll shadow the recipe's per-env `.<env>.vault_pass` here.

### Become a recipient

You decrypt with a private key whose public half is in `age-recipients.txt`. Pick
one (the file can mix types):

- **GitHub SSH key** (no new key if you already have one): `https://github.com/<you>.keys`
  serves your `ssh-ed25519` / `ssh-rsa` keys — append the line. (age does **not**
  support `ecdsa-sha2-*` or FIDO `sk-ssh-*` keys.)
- **Local SSH pubkey**: paste a line from `~/.ssh/id_ed25519.pub`.
- **Dedicated age key**: `age-keygen -o ~/.config/age/keys.txt` prints your `age1…`
  public line — add that.

### Create / rotate a password

Make sure your key is in `age-recipients.txt` (above), then generate the password
**straight into the age file** — it's never shown or written in plaintext. From
`ansible/`:

```bash
# fresh random password, age-encrypted to the recipients (-a = armored, diff-friendly):
openssl rand -base64 32 | tr -d '\n' | age -R secrets/age-recipients.txt -a -o secrets/beta.vault-pass.age
openssl rand -base64 32 | tr -d '\n' | age -R secrets/age-recipients.txt -a -o secrets/prod.vault-pass.age
```

After **first** creating a password, encrypt that env's `vault.yml` with it (decrypt
to the per-env file, then encrypt):

```bash
age -d -i ~/.ssh/id_ed25519 -o .beta.vault_pass secrets/beta.vault-pass.age
ANSIBLE_VAULT_PASSWORD_FILE=.beta.vault_pass ansible-vault encrypt inventories/beta/group_vars/all/vault.yml
```

To **rotate recipients** (add/remove an admin) without changing the password,
re-encrypt the existing password to the updated list — age can't re-wrap in place:

```bash
$EDITOR secrets/age-recipients.txt    # add/remove keys, then per env:
age -d -i ~/.ssh/id_ed25519 secrets/beta.vault-pass.age | age -R secrets/age-recipients.txt -a -o secrets/beta.vault-pass.age.new
mv secrets/beta.vault-pass.age.new secrets/beta.vault-pass.age
```

Commit the updated `*.age` / `age-recipients.txt`.

### CI mirror (GitHub Environment secret)

CI can't read a `*.age` (no admin key in the runner), and GitHub secrets are
**write-only** anyway (`gh`/the API set but never read a value back). So each env's
GitHub **Environment secret** `ANSIBLE_VAULT_PASSWORD` holds the same password and
`deploy.yml` writes it to `.vault_pass` for the run. Mirror it from the age file
(decrypt → `gh`, never on disk) whenever you create or rotate a password:

```bash
age -d -i ~/.ssh/id_ed25519 secrets/beta.vault-pass.age | gh secret set ANSIBLE_VAULT_PASSWORD --env beta       --repo vtes-biased/archon-vibe
age -d -i ~/.ssh/id_ed25519 secrets/prod.vault-pass.age | gh secret set ANSIBLE_VAULT_PASSWORD --env production --repo vtes-biased/archon-vibe
```

Same password, two delivery paths: humans decrypt the `.age` locally; CI reads the
Environment secret.

## Cutting a release

```bash
just release v1.2.3    # tags + pushes; CI runs e2e and, if green, creates the GitHub Release
```

`just release <tag>` validates the tag starts with `v`, the working tree is clean,
and the tag doesn't already exist, then runs `git tag` + `git push origin <tag>`.
From there:

1. `.github/workflows/release.yml` runs the full Playwright E2E suite (isolated
   stack). A failing suite aborts — no Release is created.
2. On success, the workflow runs `gh release create <tag> --verify-tag
   --generate-notes` to publish the GitHub Release.
3. The same run then calls `release-artifacts.yml` directly (`workflow_call`)
   to build and attach the wheel / frontend dist assets — no `release:
   published` event handoff (a `github.token`-created Release never fires it),
   so no PAT/token is needed.
4. Deploy is manual + approval-gated (`deploy.yml`) — nothing auto-deploys.

To run the E2E suite without cutting a release (e.g. on `main`), use
`workflow_dispatch` on `release.yml` in the Actions tab.

## Routine updates

```bash
just deploy-beta                           # deploy latest Release to beta
just deploy-prod                           # same for prod
RELEASE_TAG=v1.2.3 just deploy-prod        # deploy a specific Release
SOURCE=local just deploy-beta              # build locally + deploy (un-released change)
QUICK=1 just deploy-beta                   # version bump only: ship artifacts, skip provisioning
```

`QUICK=1` passes `--tags app`, running only the artifact-shipping roles
(backend/frontend/bot); TLS, nginx vhosts, db and user provisioning are skipped.
Use a full (default) deploy for any nginx/TLS/db/systemd/env change.

The playbook prints the concrete tag it resolved (so `latest` is auditable) and,
for a public repo, needs no auth — set `GITHUB_TOKEN` in the environment only to
lift the API rate limit. Note: re-running the release workflow re-uploads
(`--clobber`) a release's attached artifacts — treat a published release's assets
as the deployed bytes and cut a new release rather than re-running to change what
ships.

## Deploy from CI (GitHub Actions)

`.github/workflows/deploy.yml` runs the deploy from a runner — `beta` →
`deploy-beta.yml` (server-setup host), `production` → `deploy.yml` (standalone,
inventory dir `prod`). It is
**manual-only** (`workflow_dispatch`, pick `beta`/`prod` + an optional
`release_tag`) and **approval-gated**: the job binds to a GitHub Environment whose
required-reviewer rule pauses the run until someone approves. Nothing
auto-deploys.

For **beta**, server-setup owns the config — `just sync` (from the server-setup
repo) pushes `DEPLOY_HOST` + `DEPLOY_HOST_KEY` and `just sync-key ~/.ssh/deploy`
pushes `DEPLOY_SSH_KEY` to this repo's `beta` environment. One-time setup:

1. **Environments** (Settings → Environments): create `beta` and `production`,
   each with **Required reviewers** enabled.
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
   - `ANSIBLE_VAULT_PASSWORD` — the vault password for that env's `vault.yml`
     (set it with `gh secret set` — see [Vault passwords](#vault-passwords)).
4. The VPS must accept SSH from GitHub-hosted runner IPs (port 22 open).

`production` deploys require an explicit `release_tag` (a pre-check fails a
blank production dispatch before the approval gate), so the reviewer sees the
exact tag being shipped; `beta` allows blank (= latest).

## System updates / kernel upgrades

```bash
just upgrade-prod                          # apt upgrade; warns if reboot needed
REBOOT=1 just upgrade-prod                 # also reboot if /var/run/reboot-required
FULL=1 REBOOT=1 just upgrade-prod          # dist-upgrade + reboot (major kernel bumps)
```

The `system_upgrade` role stops the backend + bot services before rebooting and
restarts + health-checks them afterwards. Prod only: beta (frankfurt) system
updates, reboots included, are owned by server-setup's own upgrade pipeline.

## One-shot PG16 → PG17 migration (prod only)

Prod currently runs PostgreSQL 16. Run this **once** after a full on-disk
backup, **before** the Phase-1 stand-up:

```bash
just migrate-postgres-prod   # 1. archondb → PG17, back on port 5432
# verify legacy archon runs clean on PG17, then:
just database-prod           # 2. new archon db/user/tunings in the PG17 cluster
```

The order matters: with PG16 still holding 5432, apt puts the 17 cluster on
5433 while the postgresql role tasks and `DATABASE_URL` (unix socket, no
port) silently target 5432 — the legacy cluster. Migrating first puts PG17 on
5432, so everything that follows lands in the one shared cluster (which also
halves PG RAM on the ~2GB box).

The playbook stops both stacks (legacy `archon_web` included — it would
otherwise keep writing to the cluster being dumped), takes a `pg_dumpall`
backup, stands up PG17 in parallel on port 5433, restores, swaps the ports,
and restarts the services. PG16 stays on disk, stopped, as a ~48h rollback
path.

## Layout

```
ansible/
├── ansible.cfg           # defaults (roles_path, vault, SSH multiplex)
├── requirements.yml      # collection pins (incl. lionel_panhaleux.server_setup from git)
├── justfile              # deploy + local-build recipes (wraps ansible-playbook)
├── galaxy_collections/   # collections installed by `just galaxy` (git-ignored)
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
