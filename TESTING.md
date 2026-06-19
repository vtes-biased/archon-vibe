# Testing

## Test Structure

```
backend/tests/       # Backend unit tests (pytest)
frontend/tests/e2e/  # E2E tests (Playwright)
test-results/        # Test artifacts (screenshots, traces) - gitignored
playwright-report/   # HTML test report - gitignored
```

## Backend Tests (pytest)

`just test-backend` is canonical: it builds the PyO3 engine into the venv, brings the `db` container up if needed, runs `pytest backend/tests/`, then stops the DB. `conftest.py` points `DATABASE_URL` at a separate `archon_test` DB on `:5433` and **auto-creates it**, so no manual DB setup is needed — just have the `db` container up (`docker compose up -d db`) and the engine built (`uv run maturin develop --manifest-path engine/Cargo.toml`). Override the target with `TEST_DATABASE_URL`.

## Running gates in a fresh git worktree

A fresh worktree has empty venvs / no `node_modules` / no generated artifacts.

- **Backend**: `uv run maturin develop --manifest-path engine/Cargo.toml`, then `uv run python -m pytest backend/tests/` (Postgres on `:5433`). Do **not** use `just test-backend` from a worktree — its compose-project check won't match and it tries to bring up `db` on a clashing port.
- **Bot**: needs env vars `DISCORD_BOT_TOKEN` / `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` at import; run `uv run --with pytest python -m pytest` from `bot/`.
- **Frontend**: `npm ci`, `npx svelte-kit sync`, `npx @inlang/paraglide-js compile --project ./project.inlang --outdir ./src/lib/paraglide` (else ~75 phantom errors). The only expected remaining `svelte-check` errors are the missing generated artifacts (`engine/pkg`, geonames JSON). Prettier is not project tooling.

## E2E Tests (Playwright)

### Via Docker (recommended)

```bash
just test-e2e
```

This spins up a **fully isolated** stack (compose `test` profile) and tears it
down afterward — it never touches your dev `db`/`backend` or the `postgres_data`
volume:
- `db-test` — a throwaway Postgres whose data lives in tmpfs (RAM), destroyed
  with the container
- `backend-test` — a backend bound to `db-test`, VEKN sync off
- `populate-db` — runs `backend/scripts/seed_e2e.py --output /shared/e2e-seed.json`
  to seed and publish the seed file (`E2E_FORCE=1`, since `db-test` is empty)
- `frontend-test` — builds the WASM engine, serves Vite, runs Playwright, writes
  the report to `playwright-report/`

> ⚠️ The seed script opens with `DELETE FROM objects` / `DELETE FROM auth_methods`.
> Never point it at a DB you care about. It refuses to run against a non-empty DB
> unless `E2E_FORCE=1` (see the guard in `seed_e2e.py`).

> ⚠️ `docker compose down -v` is **project-scoped, not profile-scoped** — it removes
> every named volume in the compose file (ignoring `--profile`), so an ad-hoc test
> teardown can wipe the dev `postgres_data`. `just test-e2e` is safe (its data is
> tmpfs), but if you run a stack by hand, give it its own project (`docker compose -p
> archon-vibe-e2e …`) so `down -v` can only touch the test volumes — and stop it with
> `docker compose -p <proj> down`, never by killing the CLI child (that lets the
> parent recipe fire its `down -v` EXIT trap).

### View Test Report

```bash
open playwright-report/index.html
# or
cd frontend && npx playwright show-report ../playwright-report
```

### Manual/Local Run

Run against a **throwaway DB** so you don't wipe dev data. Example using a
dedicated `archon_e2e` database on the dev Postgres container:

```bash
# 1. Fresh throwaway DB
docker exec archon-vibe-db-1 psql -U archon -d postgres -c \
  "DROP DATABASE IF EXISTS archon_e2e; CREATE DATABASE archon_e2e;"

# 2. A backend bound to it (separate port), VEKN sync off
DATABASE_URL=postgresql://archon:archon_dev_password@localhost:5433/archon_e2e \
  VEKN_SYNC_ENABLED=false \
  uv run uvicorn backend.src.main:app --port 8001 &

# 3. Seed it + write the seed file Playwright reads (repo-root/e2e-seed.json)
DATABASE_URL=postgresql://archon:archon_dev_password@localhost:5433/archon_e2e \
  uv run python backend/scripts/seed_e2e.py --output e2e-seed.json

# 4. A frontend dev server pointed at the test backend
cd frontend && VITE_API_URL=http://localhost:8001 npx vite dev --port 5174 &

# 5. Run the suite against the isolated stack
BASE_URL=http://localhost:5174 VITE_API_URL=http://localhost:8001 npm run test:e2e
```

`playwright.config.ts` skips its own Vite `webServer` when `BASE_URL` is set.

## E2E Infrastructure

### Global Setup / Teardown

- `global-setup.ts` — runs before all tests. It does **not** seed or clean the
  DB (seeding is `populate-db` in Docker, or your manual seed run above):
  1. Health-checks the backend (`VITE_API_URL`, default `http://localhost:8000`)
  2. Reads the seed file (`E2E_SEED_FILE`, default `repo-root/e2e-seed.json`)
  3. Logs in the organizer via `POST /auth/login` → stores real JWT tokens in
     `tests/e2e/.e2e-state.json`
  4. Warms up the Vite dev server (pre-compiles bundles for parallel workers)
- `global-teardown.ts` — removes the `.e2e-state.json` token file. DB cleanup is
  not needed: Docker uses an ephemeral tmpfs DB; for manual runs drop the
  throwaway DB (or run `seed_e2e.py --cleanup`).

### Test Data (`backend/scripts/seed_e2e.py`)

Seeds a minimal isolated DB:
- Truncates `objects` + `auth_methods` first (avoids syncing the full VEKN
  dataset) — guarded by `E2E_FORCE` against non-empty DBs
- Creates 1 organizer (IC + Ethics roles, VEKN ID `9999901`, email `e2e-organizer@example.com`)
- Creates 10 players with VEKN IDs `9990010`–`9990019`
- Regenerates snapshots for fresh SSE sync
- `--output <path>` writes the JSON the Playwright global setup reads
- `--cleanup` removes test objects by VEKN ID prefix (`9999%` / `9990%`) and
  tournament/league name prefix `E2E `

### Auth Helpers (`helpers/auth.ts`)

Two strategies for injecting tokens:

| Helper | When to use |
|--------|-------------|
| `loginAsOrganizer(page)` | After `page.goto()` — clears `last_sync_timestamp` to force full-level resync |
| `setupAuthBeforeNavigation(page)` | Before first `page.goto()` via `addInitScript` — first sync uses full-level data immediately |

### Sync Helpers (`helpers/wait.ts`)

- `waitForSync(page)` — waits for emerald SSE dot (sync complete)
- `waitForUsers(page)` — waits for sync + first `.user-row`

## Test Coverage

| Spec | Coverage |
|------|----------|
| `users.spec.ts` | App loads, SSE streaming, user list display, profile page, sanction modal UI (real auth tokens) |
| `tournament.spec.ts` | Full nominal tournament arc: create → register 8 players → check-in → decklist upload + replacement (organizer-entered, real precon list from `fixtures/tremere-precon.txt`) → 2 rounds scored via the UI, with a seating modification (unseat/re-seat) and an in-event caution (sanction delivered over SSE) during round 1 → random toss → finals → winner banner → rating points on `/rankings` |
| `leagues.spec.ts` | League creation (IC) via the form, detail page, list page |

### Tournament Lifecycle Test Notes

- Everything goes through the real UI — no direct API calls. Mutations are
  optimistic (WASM), but server POSTs are serialized per tournament, so
  chaining UI steps is ordering-safe.
- Tables are scored with the VP dropdowns: the first seat gets all VPs (a
  sweep is a valid oust order), which flips the table badge to Finished.
- Sweep scoring guarantees score ties at the finals cutoff, so the
  Random Toss step is always exercised. The toss shuffle is seeded from the
  tournament uid, so the WASM optimistic result and the server agree.
- The test awaits the `StartRound` server response before scoring (seating
  committed) and the `FinishFinals` response before checking `/rankings`
  (the server-side ratings recompute + SSE push happen in that request).
- Decklist: the organizer uploads on a player's behalf (engine allows it —
  the paper-decklist flow), replaces it pre-round-1 while contents are
  hidden, and the replaced name is asserted after round 1 starts (the
  reveal). Seating changes use the click-based Unseat/Seat-a-player flow —
  `AlterSeating`'s drag-and-drop is not reliably scriptable. The caution's
  indicator dot renders from IDB, so its appearance proves SSE delivery
  (`POST /sanctions` is not optimistic).
