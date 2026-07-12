---
name: trap-tournament-action-route-untested
description: Where the tournament_action route's post-engine hooks live and why the engine-contract test pattern can't reach them
metadata:
  type: reference
---

The `tournament_action` route (`backend/src/routes/tournaments.py`) applies
server-side hooks **after** the Rust engine returns and before save: the
`finish` timestamp stamp, the online-only **timer lifecycle hooks**
(`TimerState` reset, `table_extra_time` clearing on round start/end), and the
**`vekn_results_stale` divergence hook** (sticky flag set when a post-push
action changes winner/standings/finals/rounds; mirrored in `sanctions.py`
`_apply_sanction_to_tournament`).

Two traps when assessing changes to that block:

- **No route-level test exists.** Nothing in `backend/tests/` POSTs to the
  tournament action route. `test_engine_model_contract.py` is the only
  tournament-action coverage and it calls `PyEngine().process_tournament_event`
  **directly** — so it structurally cannot reach the route's post-engine hooks.
  Asserting those hooks at an interface means a new route-level harness (auth +
  seeded tournament + real engine + real DB). Weigh that cost against the
  consequence before recommending it.

- **No file covers the timer.** `test_table_label_and_judge_call.py` (the
  nearest-named file) is `resolveTableLabelPy` + `broadcast_judge_call` only;
  there is no timer test anywhere, by design (see the consequence note below).

The timer is **online-only, cosmetic** (countdown display) — not engine-scored,
not pushed to VEKN, not access-control. Timer-logic regressions are low-
consequence and self-correct on the next round transition; they rarely clear
the new-test bar.

**`vekn_results_stale` assessed 2026-07, deliberately left untested.** The flag
is advisory (a UI staleness hint in `FinishedResults.svelte`) — it does not
corrupt data, gate access, or re-send results (the write-once push already
happened; the flag only notes the local copy later diverged). The sharpest
regression is a *spurious* always-stale flag if the engine round-trip
re-serializes untouched standings/rounds/finals differently — but the compare
rides the engine round-trip-fidelity invariant, which is already load-bearing
(every action re-saves the whole tournament; the e2e lifecycle exercises it).
A real test needs the nonexistent route harness (over-investment for an advisory
flag); a cheap extracted-helper unit test would restate the 4-way OR AND bypass
the round-trip (feeding hand-built objects), so it would verify nothing that
matters. The member-projection exclusion of the flag is already pattern-covered
by `test_access_levels.py::test_excludes_vekn_pushed_at` (same push-bookkeeping
category) and leaking a boolean staleness hint is not a privacy/access hole.
