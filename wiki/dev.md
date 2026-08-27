# Development

## Prerequisites

Rust (rustup), Node 24+, `uv`, `just`, and Docker or OrbStack. `uv` auto-installs
Python.

Deferred, on the trigger "SvelteKit and svelte-check ship TS 7 support": bump
TypeScript 6 → 7 — done when `npm ls` is clean and `svelte-check` passes on TS 7.

```bash
just update    # install Python, Node, Rust and wasm-pack deps, build the engine
just dev       # database + backend + frontend
just dev-stop
```

Frontend on `:5173`, backend on `:8000`, PostgreSQL on `:5433`.

```bash
just           # list all recipes
just test      # engine + backend + frontend
just lint      # lint and auto-fix
just dev-reset # reset the dev database
```

## Lint gates

`just lint` auto-fixes formatting, then runs the checks nothing can fix for you;
`just lint-check` is the read-only half and is what `just test` calls. Both end on
the same seven gates:

- `just permission-drift` — a role literal used to gate outside the engine's
  capability table.
- `just comment-blocks` — a contiguous comment block over three lines, in every
  tracked `.py`, `.rs`, `.ts` and `.svelte` file ([dogmas](dogmas.md#code)).
  `#`, `//`, `///`, `/* … */` and `<!-- … -->` all count, so the ceiling is not a
  question of which one the narration is written in. Two things it does not see:
  TypeScript's `/// <reference>`, which is compiler input rather than prose, and
  Python docstrings, which are strings. Nor does it see a block split by a blank
  line. Those are the reviewer's comment pass to delete, not the gate's.
- `just dark-variant` — Tailwind's `dark:` variant anywhere under `frontend/`,
  which tracks the OS preference rather than the app's theme
  ([design](design.md#palette)). A `dark:` followed by a space is an object key
  or a type annotation and passes.
- `just locale-parity` — a message catalog whose keys disagree with the base
  locale's, in either direction ([i18n](i18n.md)). Paraglide resolves a missing
  key by falling back to the base locale, so an untranslated string ships as
  English with nothing failing; a key outliving its base entry is the same drift
  reversed. The locale list comes from the inlang project settings, so a sixth
  locale is covered without touching the gate.
- `just public-api-isolation` — the app naming the public API, or the API
  importing the app's machinery ([public-api](public-api.md#isolation)). It runs
  in CI too, unlike the two gates above it.
- `just migration-pairing` — a stored-value migration with no proof section in
  [post-deploy](post-deploy.md), or a section proving an entry that no longer
  exists ([architecture](architecture.md#stored-value-migrations)). Nothing in
  the tree records that an entry ran, so the section is the only proof it reached
  a database, and the pairing is what makes the entry die in the commit that
  retires it. It parses `migrations.py` with `ast` rather than importing it —
  importing would pull in the engine — and fails when that parse stops matching,
  which is what keeps an empty result from passing everything in silence. It runs
  in CI, on the lint job.
- `just model-drift` — `models.py`, `types.ts` and the engine disagreeing on a
  field name or an enum value ([sync](sync.md#adding-a-new-object-type)). Nothing
  generates one from another. It compares names and values, not types: `datetime`
  is `string` over the wire and every optional spelling differs, so types would be
  noise. A shape that genuinely belongs to one side is listed in the script with
  its reason, which is also what keeps a parse that stopped matching from passing
  everything in silence. The engine leg reads `engine/src/model.rs`, where every
  stored field name the engine touches is a const in a module named for its model,
  so `player::STATE` is checked against `Player` alone — a rename is caught even
  when the old name survives on another model. It then parses the engine with
  tree-sitter and fails on a field name written any other way: indexed by literal,
  an object-literal key in either the `"k" =>` or the bare `k:` form, a `has_key`
  or `remove` argument, or an entry in a list a loop then indexes by — the shapes
  that let a key hide, since a macro body is one token tree and `has_key` is a
  call. It reads each `field == "literal"` against the enum the field's type
  names, including `matches!` arms and the allowed-values list `validate_enum`
  takes. Test modules are outside the sweep, so `tests.rs` keeps raw keys. In CI
  it rides the backend job, not the lint one: `models.py` instantiates `PyEngine`
  at import, so it needs the built engine.

In dev only the **database** runs in Docker; backend and frontend run natively. The
compose file is **not** production-hardened — uvicorn reload, a default password.
Its `test` profile backs `just test-e2e` ([testing](testing.md)).

## Deployment

Real deployment is **wheels plus systemd via Ansible**, under `ansible/`. There is
no Docker production path. Production runs on a 945 MB single-core VPS with a
24 GB disk, which is why the connection pool is small and bulk table loads are
forbidden ([architecture](architecture.md#database-access)).

The `common` role guarantees the box's baseline beyond what it installs: the
daemons a single-disk VM never uses (multipath, fwupd, ModemManager, udisks2,
VMware guest tools) and rsyslog — a second copy of what the journal already
keeps — are purged, the journal is capped at 256 MB, apt keeps no downloaded
packages, and every uv call runs `--no-cache`, so a deploy leaves no build cache
behind. PostgreSQL is sized to the pools that actually connect — 20 slots against
the app's 8 and the public API's 4, leaving the superuser reserve of 3 and
headroom for pg_dump and ad-hoc psql — not to a client count the box never sees.

Because the backend ships as an installed wheel, **bundled data files must load
through `importlib.resources`**, never `Path(__file__)`
([dogmas](dogmas.md#dependencies-and-data)).

Vault secrets are edited in place — `just vault-edit-beta` / `just vault-edit-prod`
from `ansible/`, committing the re-encrypted file. The per-env password files are
gitignored; an admin decrypts them from `ansible/secrets/<env>.vault-pass.age`.

**A role's `defaults/main.yml` is its parameter contract.** Every `r.*` key the
role reads is listed there, and is either required — asserted in the role, so
omission fails the play — or carries a `*_default` that makes omission correct.
The playbooks pass only what genuinely differs between beta and prod, so a
parameter added to one caller and not the other can no longer be silently
skipped on the other. A role resolves its defaults into `_`-prefixed facts, and
those are host-scoped: they outlive the role that set them, so each role must set
every `_` fact it reads rather than inherit a same-named one from an earlier role.

Three units and three vhosts per environment: the app, the Discord bot, and the
**public read API**, which installs nothing of its own — it runs a second uvicorn
off the backend's wheel and venv, is `PartOf` the backend unit so a wheel restart
reaches it, and owns the only vhost carrying rate limits
([public-api](public-api.md#deployment)).

Nothing auto-deploys, and there is no public version endpoint — never sniff the app
for a version.

The `new.` hostnames the parallel run used — `new.archon.vekn.net` and
`new.archon.krcg.org` — still resolve, with no vhost and no certificate behind
them. That is deliberate: the A records are kept as the affordance for standing a
future major version beside the live one, so a resolving name with nothing serving
it is the expected state, not a leftover to clean up.

### Environment identity

One release artifact is deployed to both hosts, so nothing about the environment
can be baked at build time. It is resolved at **runtime from the hostname** —
`archon.krcg.org` is beta, `archon.vekn.net` production — in the three runtimes
that each need it independently, because none can read another's answer: the
`app.html` head script (which resolves before first paint, since the manifest is
read at install time, and publishes the answer as `documentElement.dataset.env`
for the app to read), `service-worker.ts` off `self.location.hostname`, and
`og.py` off the host the crawler reached. Anywhere else, read `dataset.env`
rather than re-deriving. What each surface then shows is
[design](design.md#beta-identity).

Beta's identity assets ship in the same artifact under `-beta` names —
`manifest-beta.webmanifest`, `favicon-beta.svg`, `icon-{192,512}-beta.png`,
`apple-touch-icon-beta.png` — and production never requests them. The icons are
generated from `favicon-beta.svg` onto the `#2A2520` ground; they are committed
assets, not a build step.

Social crawlers reach an og stub through the nginx UA-split, which now covers the
bare `/` as well as the object and help paths. `/` proxies to the backend's
`/og/site` rather than preserving the URI, because the backend's own `/` is the
health check.

### Backups

Production only — `ansible/roles/db_backup`, gated on `db_backup_enabled`; the
beta playbook never runs it. Daily at 03:00 UTC a systemd timer dumps every
non-template database in the cluster except `postgres` itself (`pg_dump -F c`,
one file per DB) plus the cluster globals — login roles and password hashes,
without which a full-cluster restore has no roles to connect as — into
`/var/backups/postgres`, kept locally for 7 days. Each dump is also pushed
off-box with restic to S3, one repository per database plus one for globals;
remote retention is 7 daily, 4 weekly and 12 monthly snapshots, applied with
`restic forget --group-by host` — the default `host,paths` grouping would put
each timestamp-named dump in a group of its own and keep everything forever.
Weekly (Wednesday 06:00 on prod) a second timer proves the per-database backups
restorable: `restic check` decodes a 10% sample of each database's repo, then
the latest snapshot is restored round-trip into a throwaway database that must
come back with user tables — the globals repo gets no such check. Both timers
carry a healthchecks.io dead-man's switch that alerts by *absence* of the
success ping. A restic repository belongs to its database: one that is dropped
or excluded leaves a repo nothing prunes, which the backup run surfaces as a
journald warning for manual deletion.

### The release order

The changeset is written **before** the tag, not after the deploy. `/changeset`
appends a `## Unreleased` block to `CHANGELOG.md`; `just release` rewrites that
heading to the tag it is cutting plus today's date, commits it, pushes the branch
and only then tags. The tag therefore contains its own entry, so the frontend
bundle CI builds from it carries the notes for the version it *is* — that is the
whole point, and stamping afterwards would put every entry one release behind the
build that shows it ([architecture](architecture.md#whats-new)). A missing
`## Unreleased` section only nudges: a release with nothing user-facing is
legitimate.

`/post-deploy` runs after the deploy. It first works
[post-deploy](post-deploy.md) — the actions the deployed commits have just made
safe, a one-time script run being the usual shape — and then closes the feedback
issues the same deploy made live. Only the issue half holds no state: an open
issue, the commit whose `Reported in #N.` names it and `git tag --contains` are
enough to say whether a fix is live, while a script run leaves nothing behind to
derive from and so has to be written down when it is written.

Production nginx proxies only an allowlist of top-level path prefixes to FastAPI
([access](access.md#deployment-gate)), and its templates own the Open Graph
crawler UA list ([architecture](architecture.md#reports-and-social-sharing)).

## Configuration

Copy `.env.example` to `.env`. **Local dev works with no `.env` at all** — every
variable has a sensible default. Production requires explicit configuration.

**Core** — `DATABASE_URL`; `JWT_SECRET` (generate with `openssl rand -base64 32`
in production); `ENVIRONMENT` (`production` enforces JWT validation);
`FRONTEND_URL`, the public frontend origin used for OAuth redirects, calendar links
and error pages; `API_BASE_URL`, the backend's view of its *own* public address for
URLs it generates; `VITE_API_URL`, the frontend's view of where to reach the
backend, baked at build time and safely empty behind a same-domain reverse proxy;
and `SNAPSHOT_DIR`, which **must be a persistent path in production** — the `/tmp`
default is cleared on reboot.

**Auth** — WebAuthn needs `WEBAUTHN_RP_ID`, `WEBAUTHN_RP_NAME` and
`WEBAUTHN_ORIGIN`, which must exactly match what the browser sees. Discord OAuth
needs `DISCORD_CLIENTID`, `DISCORD_SECRET` and `DISCORD_REDIRECT_URI`, plus
`DISCORD_BOT_TOKEN` from the **same application** for Linked Roles
([discord](discord.md)). Magic links need the `MAIL_*` SMTP set.

**VEKN** — `VEKN_SYNC_ENABLED`, `VEKN_SYNC_INTERVAL_HOURS`, `VEKN_API_BASE_URL`,
`VEKN_API_USERNAME`, `VEKN_API_PASSWORD`, `VEKN_PUSH`,
`VEKN_PUSH_INTERVAL_HOURS`, `VITE_VEKN_PUSH`, and the separately-flagged
`TWDA_SYNC_ENABLED` ([vekn](vekn.md#feature-flags)).

**Web Push** — `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`; generate
with `just vapid-keys`. The private key and subject are ansible-vault secrets. The
public key is served at runtime, never baked into the build
([architecture](architecture.md#web-push)).

**TWDA auto-PR** — `TWDA_GITHUB_CLIENT_ID`, `TWDA_GITHUB_PRIVATE_KEY` (a file path or
inline PEM), `TWDA_GITHUB_INSTALLATION_ID`, `TWDA_GITHUB_FORK_INSTALLATION_ID`,
`TWDA_GITHUB_FORK_OWNER`. **One App, installed twice**, because GitHub App
permissions are repository-wide and the archive will not grant write: the
**fork installation** (`vtes-biased/TWD`) is asked for Contents read-and-write and
holds every write — the fork sync, the branch, the deck commit — while the
**archive installation** (`GiottoVerducci/TWD`) is asked for Pull requests
read-and-write and nothing else. The App *declares* both permissions because the
fork needs Contents, but an installation holds only what its owner approved: the
archive's approved Pull requests alone, which is exactly why the old
both-at-once token request was refused. The per-request `permissions` narrowing is
what keeps us from ever asking it for more. No webhook on either. The private key and client
id are shared; only the two installation ids differ, and both are vault secrets.
**The fork must stay public** — the archive's token has no access to it and can
only reference a public head. **The PR request must decline maintainer
modification** (`maintainer_can_modify: false`): GitHub turns it on by default for
a cross-repository pull request, and the archive's installation cannot grant edit
rights on a fork it cannot see, so the default is refused with a 422. With any of
the five unset the feature is silently skipped.

Secrets and PII never enter the repository — the repo is public and CI publishes
wheels as release assets ([dogmas](dogmas.md#dependencies-and-data)).

## Library documentation

Fetch current docs through the Context7 MCP server rather than answering from
memory. Chosen for the best combination of snippet count and benchmark score:

| Library | Context7 ID |
|---|---|
| Svelte 5 | `/websites/svelte_dev` |
| Vite | `/vitejs/vite` |
| TypeScript | `/websites/typescriptlang` |
| Tailwind CSS v4 | `/websites/tailwindcss` |
| Playwright | `/websites/devdocs_io_playwright` |
| FastAPI | `/websites/fastapi_tiangolo` |
| msgspec | `/jcrist/msgspec` |
| psycopg 3 | `/websites/psycopg_psycopg3` |
| pytest | `/pytest-dev/pytest` |
| PyO3 | `/pyo3/pyo3` |
| wasm-bindgen | `/rustwasm/wasm-bindgen` |
| MDN (IndexedDB, Service Workers, Web APIs) | `/mdn/content` |

## Repository layout

```
engine/     Rust core — the single source of business logic
backend/    FastAPI service
frontend/   Svelte PWA
bot/        Discord tournament bot (separate process)
ansible/    deployment
reference/  official VEKN and VTES documents (external, not ours to edit)
scripts/    build and data tooling
wiki/       this wiki
board/      elaborated context for in-flight board lines
```

`README.md` is the public front door and `CHANGELOG.md` the human record of what
shipped; both stay at the repository root. `CHANGELOG.md` is also shipped content —
the frontend bundles it and the app renders it
([architecture](architecture.md#whats-new)).
