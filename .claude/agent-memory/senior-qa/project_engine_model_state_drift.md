---
name: engine-model-state-drift
description: The engine emits table/player state strings as bare literals (not from its own TableState enum, which can be stale); the backend action route strict-converts them into the Python model, so a missing enum value 500s every action. Where to test the contract.
metadata:
  type: project
---

The Rust engine writes table/player **state strings as bare literals** scattered
through `engine/src/tournament/mod.rs` apply_event (`"In Progress"`, `"Finished"`,
`"Invalid"`, `"Cancelled"`, ...), **not** from its own `TableState` enum
(`engine/src/tournament/types.rs`). That enum's `from_str`/`as_str` are only used on
a few paths — so it can go **stale relative to its own emitter** and stay green
(observed: `Cancelled` was emitted as a literal at `mod.rs` while the enum still
lacked it; inert because the soft-cancel path compares raw JSON, never
`TableState::from_str`).

**The consequential drift is engine -> Python model.** The action route does a strict
`msgspec.convert(t_data, Tournament)` (`backend/src/routes/tournaments.py`, ~line
1117). If the engine emits a state string the Python `models.TableState` /
`PlayerState` enum doesn't list, that convert raises `msgspec.ValidationError` ->
**every tournament action 500s** the moment any table/player reaches that state.
This is the `#274`-class bug: `Cancelled` had to be added to `models.py` (enum +
`Table.organized_by`) or soft-cancel 500s.

**Why:** there is no single importable source of truth for the state-string set —
engine literals, the engine enum, and the Python enum are three independent copies
that drift silently. A test that re-lists the strings is a fourth copy (passes
forever against a stale list) — does NOT clear the bar.

**How to apply (what's covered now):**
- `backend/tests/test_engine_model_contract.py` pins the invariant the robust way:
  it drives a **real `CancelRound` soft-cancel through the shipped `PyEngine`** and
  runs the route's exact `msgspec.convert(..., Tournament)`, asserting `Cancelled`
  decodes to `TableState.CANCELLED`. No DB/mock — real engine binding + real model.
  Verified to fail with the exact prod error (`Invalid enum value 'Cancelled'`) when
  the enum value is removed.
- When a future feature adds/renames a **table or player state in the engine**, that
  one test guards the table-state contract; for a new *player* state add a sibling
  assertion (same pattern, drive an event that produces it). Don't write a copied
  string-list test.
- The e2e `frontend/tests/e2e/tournament.spec.ts` exercises the convert path live but
  only for states its StartRound..FinishFinals happy path produces — never
  `Cancelled`. So new terminal/voided states need the backend contract test, not e2e.

See [[engine-test-topology]] for running backend-with-engine (`just test-backend`
rebuilds the PyO3 `.so` from current source — required, the repo `.venv` ships a
stale/missing `archon_engine.*.so`).
