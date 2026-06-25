---
name: trap-tournament-action-route-untested
description: Where the tournament_action route's post-engine hooks live and why the engine-contract test pattern can't reach them
metadata:
  type: reference
---

The `tournament_action` route (`backend/src/routes/tournaments.py`) applies
server-side hooks **after** the Rust engine returns and before save: the
`finish` timestamp stamp, and the online-only **timer lifecycle hooks**
(`TimerState` reset, `table_extra_time` clearing on round start/end).

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
