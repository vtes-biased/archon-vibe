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

**`vekn_id` on Register/AddPlayer/CheckIn is a GATE, never stored data
(assessed 2026-08, ticket 622).** Grep `vekn_id` in
`engine/src/tournament/mod.rs`: it appears only in three
`is_none_or(|v| v.is_empty()) -> VeknIdRequired` checks — the Player object
literals carry `user_uid`/`state`/`payment_status`/`toss`/`result`/`finalist`/
`non_competing` and **no vekn_id**. `vekn_push.py` re-derives every id from
`user.vekn_id`. Consequence for test design: a fabricated client vekn_id has
**nothing observable to assert** — it can only flip the gate open, never land in
a row or reach vekn.net. Also: `TournamentActionRequest` has no `vekn_id` field
and no `model_config` exists anywhere in `backend/src`, so pydantic's default
`extra="ignore"` already drops one. Any "the server doesn't trust client
identity" test here is asserting pydantic + an engine gate that
`test_checkin_auto_register_requires_vekn_id` (tests.rs) already pins.

Relatedly, **a roster `user_uid` is always resolvable**: the engine requires a
VEKN id to seat anyone, and a uid holding a VEKN id is never soft-deleted
(merge raises, `DELETE /users/{uid}` 400s — see the invariant comment in
`accounts.py::merge_users`). So a resolve-or-404 in the action route has no
reachable false-positive, and "unresolvable target" is not a state you can seed
without hand-corrupting the roster.

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
