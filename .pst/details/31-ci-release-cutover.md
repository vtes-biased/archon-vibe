# #31 — CI Release artifacts: full cutover

Extend the bot's GitHub-Release wheel delivery (#30) to **every** deployable
artifact so CI is the single source of deployed builds. Local `build-*` targets
stay for development.

## Decision (owner)
Full cutover: CI is the only build path for **deploys**; local build/test for dev
iteration stays intact. Frontend included now (not a fast-follow).

## What CI produces (`.github/workflows/release-artifacts.yml`)
One workflow, four jobs, triggered on `release: published` (attach to Release) and
`workflow_dispatch` (downloadable workflow artifacts). Replaces `bot-wheel.yml`.

| job      | build                                                              | Release assets |
|----------|--------------------------------------------------------------------|----------------|
| engine   | `PyO3/maturin-action` manylinux_2_28, x86_64, `-i python3.13`      | `archon_engine-*.whl` |
| backend  | `uv build --wheel` + `uv export` pinned reqs                        | `archon-*.whl`, `backend-requirements.txt` |
| bot      | `uv build --wheel` (bot/) + `uv export`                             | `archon_discord_bot-*.whl`, `bot-requirements.txt` |
| frontend | rust+wasm32 → `wasm-pack build --target web --release -- --features wasm`, then `npm ci && npm run build` (paraglide+vite, adapter-static → `build/`) | `frontend-dist.tar.gz` |

Card data freshness is owned by `update-cards.yml` (daily commit of
`engine/data/cards.json`); the release workflow builds from the committed copy.

> **Superseded by #82:** the `make fetch-release` step below was retired — the
> deploy playbook now self-fetches Release assets (native `uri`/`get_url`, no
> `gh`). See epic #81. The CI *build* side (this ticket) is unchanged.

## How ansible consumed them (`ansible/Makefile`) — pre-#82
- `fetch-release` — `gh release download` (default: latest; `RELEASE_TAG=vX.Y.Z`)
  into `build/`, untar `frontend-dist.tar.gz` → `build/frontend-dist`.
- `deploy-beta` / `deploy-prod` depend on `$(DEPLOY_ARTIFACTS)`:
  default `fetch-release`; `SOURCE=local` → `build-all` (test an un-released build).
- `build-*` targets unchanged (local dev / `SOURCE=local`).
- `deploy.yml` already globbs wheels from `build/` and asserts presence — only the
  fail message changed; the integration point is unchanged.

## Out of scope — pre-existing backend deploy gaps (filed #80, parent:#35)
Surfaced while tracing artifact flow; **independent of build location**, blocks a
clean prod deploy (relates #37):
1. backend wheel packages top-level `src/` (hatch `packages=[backend/src]`) but
   systemd `ExecStart` imports `backend.src.main:app` → unresolvable.
2. neither wheel nor any role ships `engine/data/cards.json`, yet `routes/cards.py`
   + `tournaments.py._load_cards_json` read it site-packages-relative → `/api/cards`
   and server-side deck validation 503 on a clean install.

## Hardening (from principal-engineer review)
- Attach steps gated on `release.prerelease == false` — prereleases don't become
  the deploy source, avoiding the "latest" split-brain with `fetch-release`.
- `fetch-release` resolves + echoes the concrete tag (no silent "latest at fetch
  time" drift between a beta and a prod deploy).
- wasm-pack via `cargo install` (deterministic, on PATH) instead of `curl | sh`.
- Least privilege: workflow default `contents: read`; per-job `contents: write`.
- `concurrency:` per release tag so close publishes don't race uploads.
- Deferred (out of #31 scope): `build-all` doesn't `clean`, so the deploy.yml
  `fileglob | sort | last` could pick a stale local wheel once versions bump past
  static 0.1.0 (lexical sort). Moot today; forcing `clean` would gut fast local
  iteration the owner wants kept.

## Notes / risks
- The whole workflow is untestable locally (no GH Actions runner here); commands
  mirror `justfile` (wasm) and the local `Makefile` (wheels) exactly.
- `gh` must be authed on the control node for `fetch-release` (repo is public).
