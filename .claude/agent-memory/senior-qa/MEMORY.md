# Senior QA Agent Memory

## Test Infrastructure

### How to Run Tests
- **Backend**: `cd /Users/lpanhaleux/Developer/archon-vibe && python3 -m pytest backend/tests/ -v --tb=short`
- **Rust engine**: `export PATH="$HOME/.cargo/bin:$PATH" && cd /Users/lpanhaleux/Developer/archon-vibe/engine && cargo test` (cargo not in default PATH on this machine)
- **Frontend type check**: `cd /Users/lpanhaleux/Developer/archon-vibe/frontend && npx svelte-check --tsconfig ./tsconfig.json`
- **Frontend E2E**: `cd /Users/lpanhaleux/Developer/archon-vibe/frontend && npx playwright test` (not run routinely -- requires running app)

### Test File Locations
- Backend: `/Users/lpanhaleux/Developer/archon-vibe/backend/tests/test_*.py` (116 tests)
  - `test_sse_filters.py` (pure unit, no DB), `test_users.py` (needs test DB), `test_offline_mode.py` (pure unit), `test_organizer_access.py` (pure unit, no DB)
- Rust engine: `/Users/lpanhaleux/Developer/archon-vibe/engine/src/` (120 tests, inline `#[cfg(test)]` modules)
  - Coverage: seating, deck parsing/validation, tournament lifecycle, ratings, permissions, league scoring
- Frontend E2E: `/Users/lpanhaleux/Developer/archon-vibe/frontend/tests/e2e/*.spec.ts` (tournament.spec.ts, users.spec.ts)
- No frontend unit tests exist (no vitest/jest setup)

### Known Pre-existing Issues
- `svelte-check` reports 1 error in `src/lib/api.ts:566` (null assignability) -- pre-existing, not a regression
- 2 a11y warnings for `autofocus` in TournamentFields.svelte and leagues/new page -- pre-existing
- `test_users.py` requires running test PostgreSQL on port 5433 -- skip with `--ignore=backend/tests/test_users.py` if DB unavailable

## Visual QA Notes
- **Global cursor bug**: ALL buttons across tournament pages have `cursor: default` instead of `cursor: pointer`. Links (`<a>`) are fine.
- **Touch targets**: Filter pill buttons (Standings/Name/VEKN/All/Pending/Paid) are 24px tall -- well below 44px minimum. Toss number inputs are 48x22px, Set buttons are 33x22px. Action buttons (Reset Check-In, etc.) are 36px tall.
- **Tab buttons**: Overview/Players/Rounds/Config tabs are 46px tall -- above minimum, OK.
- **Pluralization bug**: English `overview_round_count` says "{count} rounds" always -- shows "1 rounds" for single round. All languages affected.
- **Players table mobile**: Horizontal scroll works, but table is clipped with no visual affordance indicating more content to the right.
- **Bottom nav**: 6-7 items -- "Developer" and last item may crowd at narrow widths.
- **Tournament list mobile**: Correctly switches from table to card layout.

## Architecture Notes for Testing
- SSE filter functions (`_filter_user`, `_filter_tournament`, `_filter_sanction`, `_filter_rating`) in `backend/src/main.py` are pure functions -- ideal for unit testing
- Tournament offline fields (`offline_mode`, `offline_device_id`, etc.) are NOT copied in member-level or non-member SSE filter -- only full-access viewers see them
- `_remap_uids_in_tournament` in `backend/src/routes/tournaments.py` uses naive JSON string-replace for UID mapping -- substring collision risk with short UIDs (mitigated by UUID v7 length)
- `_is_organizer` and `_build_actor_context` in `backend/src/routes/tournaments.py` are importable pure functions -- easy to unit test
- `_map_vekn_to_tournament` in `backend/src/vekn_tournament_sync.py` is a pure function (no DB) -- testable directly with dict input

## Project Architecture Notes
- Backend uses pytest with asyncio (pytest-asyncio strict mode)
- Rust engine uses standard `#[test]` with one `#[ignore]` benchmark test
- Frontend has Playwright for E2E but no unit test framework
- Cargo binary is at `~/.cargo/bin/cargo`, not in default shell PATH
- Key pattern: SSE filter tests import functions directly from `src.main` and test pure logic without DB
