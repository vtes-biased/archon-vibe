# Senior QA Agent Memory

## Test Infrastructure

### Backend (Python)
- **Runner**: `uv run python3 -m pytest` from project root `/Users/lionelpanhaleux/dev/perso/archon-cursor`
- **Test dir**: `backend/tests/`
- **Test files**: `test_sse_filters.py` (33 tests, pure unit, no DB), `test_users.py` (4 tests, needs test DB), `test_offline_mode.py` (11 tests, pure unit)
- **Test DB**: PostgreSQL at `localhost:5433/archon_test` -- not always available locally
- **Key pattern**: SSE filter tests import functions directly from `src.main` and test pure logic without DB; tournament/user helpers use `**kwargs` for easy extension

### Rust Engine
- **Runner**: `cargo test` from `engine/` directory
- **Tests**: 57 unit tests + 1 ignored benchmark + 3 ignored doc-tests
- **Coverage**: seating, deck parsing/validation, tournament lifecycle, ratings, permissions, league scoring

### Frontend (Svelte/TypeScript)
- **E2E**: Playwright (`npx playwright test` from `frontend/`), config at `frontend/playwright.config.ts`
- **Test file**: `frontend/tests/e2e/users.spec.ts` (app load, login, user list filtering, edit mode, sanctions)
- **Type check**: `npx svelte-check --tsconfig ./tsconfig.json` from `frontend/` (58 errors pre-existing as of 2026-02-15, mostly optional field strictness in Tournament type)
- **No unit tests**: No vitest/jest setup for frontend

## Known Issues
- `test_users.py` requires running test PostgreSQL on port 5433 -- always skip with `--ignore=backend/tests/test_users.py` if DB unavailable
- Frontend `svelte-check` has ~58 pre-existing TS errors from optional Tournament fields (`rounds?`, `players?`, etc.)

## Architecture Notes for Testing
- SSE filter functions (`_filter_user`, `_filter_tournament`, `_filter_sanction`, `_filter_rating`) in `backend/src/main.py` are pure functions -- ideal for unit testing
- Tournament offline fields (`offline_mode`, `offline_device_id`, etc.) are NOT copied in member-level or non-member SSE filter -- only full-access viewers see them
- `_remap_uids_in_tournament` in `backend/src/routes/tournaments.py` uses naive JSON string-replace for UID mapping -- substring collision risk with short UIDs (mitigated by UUID v7 length)
