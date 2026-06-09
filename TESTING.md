# Testing

## Test Structure

```
backend/tests/       # Backend unit tests (pytest)
frontend/tests/e2e/  # E2E tests (Playwright)
test-results/        # Test artifacts (screenshots, traces) - gitignored
playwright-report/   # HTML test report - gitignored
```

## Backend Tests (pytest)

```bash
docker compose up -d db
docker exec archon-vibe-db-1 psql -U archon -c "CREATE DATABASE archon_test;"
uv sync --dev
pytest backend/tests/test_users.py -v
```

Or simply `just test-backend` (starts the DB if needed, runs pytest, stops it).

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
  tournament name prefix `E2E `

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
| `users.spec.ts` | App loads, SSE streaming, user list display (real auth tokens) |
| `tournament.spec.ts` | Full tournament lifecycle: create → register 8 players → check-in → round 1 → round 2 → finish |

### Tournament Lifecycle Test Notes

- Uses WASM optimistic updates — table UI appears before server response
- Waits for `StartRound` server POST to complete before scoring via API (ensures server has committed seating)
- Reads seating from IDB (WASM result) to score via API — reliable because `StartRound` now forwards computed seating so WASM and server are identical
- `scoreAndEndRound()` helper: reads round tables from IDB with polling (up to 10s), posts `SetScore` per table, then `FinishRound`
