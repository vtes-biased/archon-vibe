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

## The dev IC account

`just dev-ic-account` creates one fixed account in the dev database —
`dev-ic@example.com` / `DevIC!2026`, VEKN ID `9998001`, role IC — so members
management can be exercised signed in. The dev dump carries the owner's own login
and nothing else, so without it there is no second way in. It is idempotent by
no-op: the account already being there ends the run, so roles edited in the UI
survive a re-run, and it refuses rather than adopt a VEKN ID it did not create.

**A dev login is never an app feature.** No sign-in-as button, no seeded-credentials
banner, no backend endpoint — anything the app can reach in dev, it can reach in
production, so the affordance is a script the repository ships and production never
runs.

The checked-in password is acceptable only because the script refuses every
`DATABASE_URL` but the compose default, and that refusal runs **before** `init_db`,
which would otherwise apply the schema to whatever it was pointed at. The VEKN ID
sits at `9998001` deliberately — outside the e2e cleanup's reach
([testing](testing.md)).

## Lint gates

`just lint` auto-fixes formatting, then runs the checks nothing can fix for you;
`just lint-check` is the read-only half and is what `just test` calls. Both end on
the same nine gates:

- `just permission-drift` — a role literal used to gate outside the engine's
  capability table.
- `just comment-blocks` — a contiguous comment block over three lines, in every
  tracked `.py`, `.rs`, `.ts`, `.svelte`, `.html`, `.css` and `.j2` file
  ([dogmas](dogmas.md#code)).
  `#`, `//`, `///`, `/* … */` and `<!-- … -->` all count, so the ceiling is not a
  question of which one the narration is written in. Two things it does not see:
  TypeScript's `/// <reference>`, which is compiler input rather than prose, and
  Python docstrings, which are strings. Nor does it see a block split by a blank
  line. Those are the reviewer's comment pass to delete, not the gate's.
- `just dark-variant` — Tailwind's `dark:` variant anywhere under `frontend/`,
  which tracks the OS preference rather than the app's theme
  ([design](design.md#palette)). A `dark:` followed by a space is an object key
  or a type annotation and passes.
- `just fold-grammar` — a chevron or a native `<details>` drawn outside
  `FoldableSection`, the app's one disclosure shell ([design](design.md#patterns)).
  A rotating chevron fails outright: it was the second idiom and has no exception.
  Every other file that draws one is listed in the script with its reason, and the
  two kinds differ: a **fold** that cannot be a section is also stated on the
  design page and the two move together, while an **arrow, reorder control or
  guide mockup** is not a fold and is listed in the script alone. The gate also
  fails on a listed file that has stopped drawing one, so the list cannot outlive
  what it excuses.
- `just locale-parity` — a message catalog whose keys disagree with the base
  locale's, in either direction ([i18n](i18n.md)). Paraglide resolves a missing
  key by falling back to the base locale, so an untranslated string ships as
  English with nothing failing; a key outliving its base entry is the same drift
  reversed. The locale list comes from the inlang project settings, so a sixth
  locale is covered without touching the gate.
- `just public-api-isolation` — the app naming the public API, or the API
  importing the app's machinery ([public-api](public-api.md#isolation)). It runs
  in CI too, unlike the three gates above it.
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

- `just help-mockups` — a help-guide "screenshot" that hand-rolls a `Button` or
  `Badge`, or hard-codes a live UI label ([i18n](i18n.md#guide-mockups)). The
  guides draw the console in miniature so the prose can point at it; nothing
  recomputes those drawings when the real screen moves. It bans the class
  signatures a primitive owns, so a control has to go through the component that
  draws it for real, and it bans any literal that matches an `en.json` value,
  because that literal is a copy of a live label. Sample data — a player name, a
  clock face, a VEKN ID — never appears in the catalog, so the label rule does not
  see it; the few that collide are listed in the script with their reason. The
  label rule also covers the creation wizard's guidance panel, which draws no
  console but names the same live controls.

In dev only the **database** runs in Docker; backend and frontend run natively. The
compose file is **not** production-hardened — uvicorn reload, a default password.
Its `test` profile backs `just test-e2e` ([testing](testing.md)).

## Deployment

Real deployment is **wheels plus systemd**, both environments deployed with
**pyinfra** from `deploy/`. There is no Docker production path. Production runs on a 945 MB single-core VPS with a
24 GB disk, which is why the connection pool is small and bulk table loads are
forbidden ([architecture](architecture.md#database-access)).

Production's system is `deploy/setup.py` (`just setup-prod`), which calls
[server-setup](https://github.com/lionel-panhaleux/server-setup)'s library with
the box's own parameters: PostgreSQL 17 from PGDG, the journal capped at 256 MB
and **one month**, the privacy policy's promise that server logs are kept only
briefly, and **no fail2ban** — it holds ~70 MB, and sshd refuses passwords
anyway. Every uv call runs `--no-cache`,
so a deploy leaves no build cache behind. PostgreSQL is sized to the pools that actually connect — 20 slots against
the app's 8 and the public API's 4, leaving the superuser reserve of 3 and
headroom for pg_dump and ad-hoc psql — not to a client count the box never sees.

**The backend's resident size is its jobs' peak, not its idle footprint.** glibc
keeps freed heap, so whatever a job materializes would stay resident until the
daily `RuntimeMaxSec` restart. Two defences: a scheduler listener calls
`malloc_trim(0)` after every job — the 15-minute snapshot check makes that at most
a quarter-hour's lag for a peak outside the scheduler, such as a deck import — and
every scheduled job streams or holds a narrow projection: a `vekn_id → uid` map
rather than 19k decoded users, the archive decoded into only the fields the TWDA
sync reads, rating tournaments by cursor and users in batches. Nothing large stays
cached between passes either: the member sync builds the ~45 MB city index per
run, krcg's ~75 MB card DB is dropped once the Amaranth id map is read off it, and
fpdf is imported on the first NDA render (idle, 34 MB). Measured on beta at
production corpus size (36.7k objects): imports 103 MB, the rating recompute
+44 MB, the TWDA fetch +22 MB. `MALLOC_ARENA_MAX=2` changes nothing — measured
under concurrent load, the event loop allocates from one thread.

Because the backend ships as an installed wheel, **bundled data files must load
through `importlib.resources`**, never `Path(__file__)`
([dogmas](dogmas.md#dependencies-and-data)).

**Beta runs on frankfurt, a server-setup box**: that repo's inventory owns
its system (packages, postgres cluster, backups, Alloy, nginx's default
server). Production stays out of that inventory — it is commissioned work for
BCP, with its own keys, backup bucket and healthchecks. `deploy/` imports
`server_setup` (the `deploy` dependency group, pinned to a tag). `just
deploy-beta` and `just deploy-prod` show every change, then ask; `--dry` only shows, `RELEASE_TAG`
pins a release and `BUILD_DIR` deploys a local build (a `frontend-dist/`
directory there is packed in place of the release tarball). `deploy/deploy.py`
derives every path, unit and database from the environment's `name` in
`deploy/group_data/`, which holds what differs between environments. A service
restarts only when its wheel, requirements, env file or unit changed; the venv
install and the frontend swap compare a marker on the box with the hash of what
is deployed, so re-running a deploy that failed halfway finishes it. A
certificate renews through `/var/www/certbot`. The backend's ops scripts are
copied from the working tree, not from the release being deployed. The app,
public API and bot connect to the database by peer auth over the socket, as
the OS user that owns it: the role has no password.

The vhosts send `Strict-Transport-Security: max-age=31536000` (this host only,
no `includeSubDomains`), a year-long promise every browser keeps, and pass the
client address as `X-Forwarded-For`.

Each environment's secrets are `deploy/secrets/<env>.sops.yaml` and the files
under `deploy/secrets/<env>/`, encrypted with sops to the SSH keys
`deploy/.sops.yaml` names; identifiers stay readable beside the secret they pair
with. Edit with `sops secrets/prod.sops.yaml` from `deploy/`; a key other than
`~/.ssh/id_ed25519` goes in `SOPS_AGE_SSH_PRIVATE_KEY_FILE`. Beta's are the
owner's and the fleet's `deploy` key; production's add `id_archon` and each BCP
developer. A new recipient is added to `.sops.yaml` by someone who already
decrypts, who then runs `sops updatekeys` on every production file.

**Production's logs are in the VEKN Grafana Cloud stack** (vtesbiased), shipped
from the journal by Fluent Bit rather than Alloy: measured at 4.4 MB against
Alloy's ~73 MB, under a 40 MB systemd cap. It sends logs with
the labels beta's Alloy sends to the personal stack (`unit`, `tag`, `level`,
`host`), so a query carries over: `{host="archon.vekn.net", unit="archon-backend.service"}`
in Explore on the Loki datasource. A first start ships no backlog, and a cursor in
`/var/lib/fluent-bit` keeps a restart from sending anything twice. On the box,
`journalctl -t archon` still reads the same lines.

**Production reports its health to the same stack as metrics**, through the same
Fluent Bit and the same token, which carries metrics write. Everything is scraped
every 60 s and labelled like beta's Alloy (`job="integrations/node_exporter"`,
`cluster="archon"`, `instance="archon.vekn.net"`), so Grafana's stock Linux node
dashboards render the host: CPU, memory, swap, disk, network and load under
node_exporter's names; the systemd state, restarts and start time of the archon
units, nginx, PostgreSQL and Fluent Bit; and Fluent Bit's own record and error
counters, where a failing log shipment shows. A `fluent-bit-units` loop writes a
textfile every 15 s with the host's CPU, memory and I/O pressure and, per unit, its
cgroup memory, swap, CPU and memory stall as `archon_unit_*{unit=…}` — per unit
rather than per process, since the backend and the public API are both `uvicorn`
and every PostgreSQL connection is a new pid. PostgreSQL's internals are not
reported: Fluent Bit cannot query it.

**Production access is per developer.** Each has their own sudo account
(`just add-admin-prod <name> <pubkey> <an existing admin>`) and a
`Host archon.vekn.net` block with their `User` and `IdentityFile` in
`~/.ssh/config`, which pyinfra reads — the inventory names no user. `ubuntu`,
the image's account, is kept for `id_archon`. Kernel reboots are never
automatic: tournaments run in every timezone, so `setup-prod` warns when one is
pending and a person picks the moment to run `just reboot-prod`.

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

Social crawlers reach an og stub through the nginx UA-split, which covers the bare
`/`, the tournament, short-link, league and help paths — and only those; every
other route previews from `app.html`'s static tags, which name production on both
hosts. `/` proxies to the backend's `/og/site` rather than preserving the URI,
because the backend's own `/` is the health check.

### Backups

server-setup's `postgres_backups`, to the `archon-db-backups` bucket on
production. Beta's database is excluded from its box's cluster backup: beta is
reseeded at will. Daily a systemd timer dumps every
non-template database in the cluster except `postgres` itself (`pg_dump -F c`,
one file per DB) plus the cluster globals — login roles and password hashes,
without which a full-cluster restore has no roles to connect as — into
`/var/backups/postgres`, kept locally for 7 days. Each dump is also pushed
off-box with restic to S3, one repository per database plus one for globals;
remote retention is 7 daily, 4 weekly and 12 monthly snapshots, applied with
`restic forget --group-by host` — the default `host,paths` grouping would put
each timestamp-named dump in a group of its own and keep everything forever.
Weekly a second timer proves the per-database backups
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

**Core** — `DATABASE_URL`; `JWT_PRIVATE_KEY` and `JWT_PUBLIC_KEYS` (`just
jwt-keys`, one pair per environment, both deploy secrets —
[access](access.md#authentication)); `ENVIRONMENT`, which anything but
`development` makes those two mandatory;
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
with `just vapid-keys`. The private key is a deploy secret. The
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
id are shared; only the two installation ids differ, and both are sops secrets.
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
deploy/     pyinfra deploy (beta and production)
reference/  official VEKN and VTES documents (external, not ours to edit)
scripts/    build and data tooling
wiki/       this wiki
board/      elaborated context for in-flight board lines
```

`README.md` is the public front door and `CHANGELOG.md` the human record of what
shipped; both stay at the repository root. `CHANGELOG.md` is also shipped content —
the frontend bundles it and the app renders it
([architecture](architecture.md#whats-new)).
