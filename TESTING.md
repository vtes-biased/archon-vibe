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
- Populates database with 300 mock users
- Runs Playwright tests in a container
- Outputs report to `playwright-report/`

### View Test Report

After running tests:
```bash
open playwright-report/index.html
# or
cd frontend && npx playwright show-report ../playwright-report
```

### Manual/Local Run

```bash
docker compose up -d db backend
uv run python backend/scripts/populate_test_db.py
cd frontend && npm run test:e2e
```

## Coverage

**Backend:** Create, list, get, update users  
**E2E:** App loads, SSE streaming, user list display
