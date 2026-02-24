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
docker exec archon-cursor-db-1 psql -U archon -c "CREATE DATABASE archon_test;"
uv sync --dev
pytest backend/tests/test_users.py -v
```

## E2E Tests (Playwright)

### Via Docker (recommended)

```bash
just test-e2e
```

This automatically:
- Starts database and backend
- Seeds test data via `setup_e2e.py`
- Runs Playwright tests in a container
- Outputs report to `playwright-report/`

### View Test Report

```bash
open playwright-report/index.html
# or
cd frontend && npx playwright show-report ../playwright-report
```

### Manual/Local Run

```bash
docker compose up -d db backend
cd frontend && npm run test:e2e
```

## E2E Infrastructure

### Global Setup / Teardown

- `global-setup.ts` — Runs before all tests:
  1. Health-checks backend
  2. Cleans up leftover test data (`setup_e2e.py --cleanup`)
  3. Seeds test users via `setup_e2e.py` (organizer + 10 players with stable VEKN IDs `9999xxx`/`999xxxx`)
  4. Logs in organizer via `POST /auth/login` → stores real JWT tokens
  5. Warms up Vite dev server
- `global-teardown.ts` — Cleans up all test objects after suite completes

### Test Data (`setup_e2e.py`)

Seeds a minimal isolated DB:
- Truncates `objects` + `auth_methods` tables (avoids syncing full VEKN dataset)
- Creates 1 organizer (IC + Ethics roles, VEKN ID `9999901`, email `e2e-organizer@example.com`)
- Creates 10 players with VEKN IDs `9990010`–`9990019`
- Regenerates snapshots for fresh SSE sync
- Cleanup identifies test objects by VEKN ID prefix (`9999%` / `9990%`) and tournament name prefix `E2E `

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
