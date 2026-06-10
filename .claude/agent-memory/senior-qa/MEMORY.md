# Senior QA Agent Memory

## Pointers
- [Seating determinism](project_seating_determinism.md) — seeded ChaCha8Rng; which seating paths consume the seed + determinism test coverage.
- [Engine test topology](project_engine_test_topology.md) — how to run engine/PyO3/WASM + backend-with-engine tests; expected link failures; what each layer validates.
- [Account surgery](project_account_surgery.md) — merge/detach test infra (`test_account_surgery.py`) + non-obvious test-writing facts (calendar_token, fixture teardown, route prefixes).
- [Archon merge](project_archon_merge.md) — legacy-archon daily-merge test infra (`test_archon_merge.py`) + the "no sync writes roles" invariant and self-edit-survives-sync coverage.

## How to Run Tests
- **Backend**: `cd backend && uv run python3 -m pytest tests/ -v --tb=short`. Some suites need a test Postgres on port 5433 — skip with `--ignore` if unavailable (e.g. `test_users.py`). Pure-unit suites (SSE filters, offline mode, organizer access, access levels) need no DB.
- **Rust engine**: `cd engine && cargo test --lib` is the authoritative logic suite. `cargo` may not be on the default PATH (shell profile should load it). See [engine test topology](project_engine_test_topology.md) for the PyO3/WASM link-failure gotchas.
- **Frontend type check**: `cd frontend && npx svelte-check --tsconfig ./tsconfig.json`.
- **Frontend E2E**: `cd frontend && npx playwright test` (not routine — needs a running app; real auth + real DB truncate/seed + IDB polling, see TESTING.md).
- No frontend unit-test framework exists (Playwright E2E only).

## What's Tested Where
- Backend `backend/tests/test_*.py`: SSE filtering, access levels (all role permutations, pure unit), offline mode, organizer access, profile-update security boundary, ratings helpers, account surgery.
- Rust engine: inline `#[cfg(test)]` modules — seating, deck parse/validate, tournament lifecycle, ratings, permissions, league scoring; one `#[ignore]` benchmark.
- Frontend E2E: `tests/e2e/*.spec.ts` — `users.spec.ts` (SSE sync), `tournament.spec.ts` (full lifecycle).

## Durable Testability Facts (not obvious from code)
- Engine `ActorContext::from_json` gracefully defaults missing fields (empty vec / false) — `make_organizer()` omitting `can_organize_league_uids` parses as the "no league access" baseline.
- Backend guards expensive queries (e.g. `get_all_leagues`) behind action-type checks before calling the engine.
- Frontend `buildActorContext` is async (loads leagues from IndexedDB).
- SSE filtering is now **write-time** (precomputed public/member/full columns), not the old per-viewer `_filter_*` functions — test the projection logic in `access_levels.py`, not a read-time filter.
- Tournament offline fields (`offline_mode`, `offline_device_id`, …) are only in the full projection — non-full viewers never see them.
- `_remap_uids_in_tournament` (tournaments.py) uses naive JSON string-replace for UID mapping — substring-collision risk mitigated only by UUID v7 length.
- `_is_organizer`, `_build_actor_context` (tournaments.py) and `_map_vekn_to_tournament` (vekn_tournament_sync.py) are importable pure functions — unit-test directly.
- Multi-role users (IC+NC): the NC/Prince branch comes first in the if/elif chain — correct semantics, no separate test needed.

## Authorization (for test design)
- Authz checks run at TWO layers: backend REST endpoint AND the Rust engine. Decisions are single-sourced in `engine/src/permissions.rs` (PyO3 + WASM); the backend still enforces server-side.
- IC role bypasses the league-organizer check at both layers. NC same-country check exists in backend `_get_user_organizable_league_uids` and frontend `buildActorContext`.
