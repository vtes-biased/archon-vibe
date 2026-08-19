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
the same four gates:

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

In dev only the **database** runs in Docker; backend and frontend run natively. The
compose file is **not** production-hardened — uvicorn reload, a default password.
Its `test` profile backs `just test-e2e` ([testing](testing.md)).

## Deployment

Real deployment is **wheels plus systemd via Ansible**, under `ansible/`. There is
no Docker production path. Production runs on a ~2 GB VPS, which is why the
connection pool is small and bulk table loads are forbidden
([architecture](architecture.md#database-access)).

Because the backend ships as an installed wheel, **bundled data files must load
through `importlib.resources`**, never `Path(__file__)`
([dogmas](dogmas.md#dependencies-and-data)).

Nothing auto-deploys, and there is no public version endpoint — never sniff the app
for a version.

### The release order

The changeset is written **before** the tag, not after the deploy. `/release-notes`
appends a `## Unreleased` block to `CHANGELOG.md`; `just release` rewrites that
heading to the tag it is cutting plus today's date, commits it, pushes the branch
and only then tags. The tag therefore contains its own entry, so the frontend
bundle CI builds from it carries the notes for the version it *is* — that is the
whole point, and stamping afterwards would put every entry one release behind the
build that shows it ([architecture](architecture.md#whats-new)). A missing
`## Unreleased` section only nudges: a release with nothing user-facing is
legitimate.

`/post-deploy` runs after the deploy and closes the feedback issues it made live.
It holds no state — an open issue, the commit whose `Reported in #N.` names it and
`git tag --contains` are enough to say whether a fix is live.

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
`TWDA_SYNC_ENABLED`, `TWDA_SYNC_INTERVAL_HOURS` ([vekn](vekn.md#feature-flags)).

**Web Push** — `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`; generate
with `just vapid-keys`. The private key and subject are ansible-vault secrets. The
public key is served at runtime, never baked into the build
([architecture](architecture.md#web-push)).

**TWDA auto-PR** — `TWDA_GITHUB_APP_ID`, `TWDA_GITHUB_PRIVATE_KEY` (a file path or
inline PEM), `TWDA_GITHUB_INSTALLATION_ID`. The GitHub App needs Contents and Pull
requests at read-and-write, no webhook, installed on the TWD repository. With the
variables unset the feature is silently skipped.

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
