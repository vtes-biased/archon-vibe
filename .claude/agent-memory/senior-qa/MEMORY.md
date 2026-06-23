# Senior QA Agent Memory

## Pointers
- [Seating determinism](project_seating_determinism.md) — seeded ChaCha8Rng; which seating paths consume the seed + determinism test coverage.
- [Engine test topology](project_engine_test_topology.md) — how to run engine/PyO3/WASM + backend-with-engine tests; expected link failures; what each layer validates.
- [Account surgery](project_account_surgery.md) — merge/detach test infra (`test_account_surgery.py`) + non-obvious test-writing facts (calendar_token, fixture teardown, route prefixes).
- [Archon merge](project_archon_merge.md) — legacy-archon daily-merge test infra (`test_archon_merge.py`) + the "no sync writes roles" invariant and self-edit-survives-sync coverage.
- [VEKN member sync](project_vekn_member_sync.md) — member-sync role-seed test infra (`test_vekn_member_sync.py`) + the non-obvious update-path enforcement surface (`_update_user` enumeration, not vekn_data).
- [No git checkout during mutation tests](feedback_no_git_checkout_during_mutation_tests.md) — back up the file first; `git checkout` wiped uncommitted feature code mid-QA.
- [Engine test fixture traps](project_engine_test_fixture_traps.md) — `tournament_with_round`/`waiting_after_round` carry engine-impossible stored VP vectors; inert only because standings recompute never re-validates. Don't build full-standings asserts on their untouched tables.
- [Engine↔model state drift](project_engine_model_state_drift.md) — engine emits state strings as bare literals (enum can be stale); route strict-converts → a missing Python enum value 500s every action. `test_engine_model_contract.py` pins it.
- [Open-rounds non-VEKN flag](project_open_rounds_non_vekn.md) — `open_rounds`/`self_organized_rounds` = house format; "never push" invariant lives in the shipped `vekn_push.py` queries (tested), "never rate" is an inert in-Python skip (not tested, by design).

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
- **`StartFinals` finalist-selection coverage**: the `test_gw_finals_*` tests target `compute_gw_finals` (winner-of-finals scoring) and `test_rating_*` the rating path — NONE drove the `StartFinals` event handler's top-5-eligible selection until `test_start_finals_includes_completed_excludes_withdrawn` (added 2026-06). That test pins #272: `Completed` (capped) players ARE finalists, `Finished`/`Disqualified` are excluded and the next-ranked promoted. Engine-valid setup: 6 players, 2 single-table `[2,1,1,1,0]` rounds, distinct toss to avoid cutoff ties. `StartFinals`/`compute_preliminary_standings` read stored `result.vp` and never call `check_table_vps`, but keep tables oust-valid per convention.
- **`RestoreRound` coverage (#295)**: un-voids a soft-cancelled non-last round. Two Rust tests in `tests.rs` (added 2026-06): `test_restore_round_rederives_finished_from_retained_scores` (cancel round 0 via the real engine, then RestoreRound it; assert the table flips back to Finished from retained scores, capped players re-arm to Completed, the live round is untouched) and `test_restore_round_respects_over_cap_before_flip` (the fragile count-before-flip ordering — over_cap is computed WHILE the round is still Cancelled so the target round is excluded from each seated player's count). **Over-cap fixture arithmetic trap**: `count_player_rounds_played` excludes Cancelled tables, so to make a seated player *at* cap you must give them N OTHER non-cancelled finished rounds, not just seat them with high-cap teammates — a player appearing ONLY in the cancelled round + one other round counts 1, not 2. Mutation-verified: deleting the `over_cap` guard flips the over-cap player Checked-in→Completed and the test fails. Kept in Rust, NOT extending the Python contract test: RestoreRound only emits Finished/In Progress (already model-decodable), so it adds no enum-drift surface.

## Authorization (for test design)
- Authz checks run at TWO layers: backend REST endpoint AND the Rust engine. Decisions are single-sourced in `engine/src/permissions.rs` (PyO3 + WASM); the backend still enforces server-side.
- IC role bypasses the league-organizer check at both layers. NC same-country check exists in backend `_get_user_organizable_league_uids` and frontend `buildActorContext`.
