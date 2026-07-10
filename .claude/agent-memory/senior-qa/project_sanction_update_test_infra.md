---
name: sanction-update-test-infra
description: How to test PUT /sanctions/{uid} cheaply (no engine) + the null-expiry-PROBATION permanent-suspension trap that makes its validation matter.
metadata:
  type: project
---

Testing the sanctions HTTP endpoints (`backend/src/routes/sanctions.py`).

**Cheap route test with NO tournament/engine.** All post-save DQ/SA recompute
branches in `update_sanction_endpoint` / `create_sanction` / `delete` are gated on
`sanction.tournament_uid`. Give the sanction `tournament_uid=None` and the route
is pure validation + `save_sanction` — no `_apply_sanction_to_tournament`, no
`update_standings`, no engine-valid VP/round/table fixtures. Use `test_client` +
`make_auth_header` (conftest) on the real `test_db` Postgres. `has_modify_fields`
gates on IC/ETHICS, so the caller user needs `roles=[Role.IC]`. The `test_db`
fixture only wipes `type='user'`; tear down `type='sanction'` yourself in a
finally. See `test_sanction_update.py`.

**Why null-expiry PROBATION is not cosmetic.** `accounts.user_has_active_suspension`
treats `expires_at is None` on a SUSPENSION/PROBATION as PERMANENTLY active
(no expiry → active forever). A PROBATION persisted without expiry therefore
permanently blocks the member from abandoning their VEKN ID (and vekn.py:148
actions). The 18-month `_validate_expiry` cap exists to bound exactly this; the
pst #365 fix hoisted that validation so a level-only SUSPENSION→PROBATION edit
enforces it. Mutation-verified: re-nesting the call under `if expires_at is not
None` returns 200 and persists the permanent-probation hole.

**Only the DQ *state flip* is route logic; the zeroing math is the engine's.**
Standings zero a player off `player.state=="Disqualified"` OR an active DQ
sanction (Rust `update_standings`, engine-tested). The route's part-2 contribution
is just detecting `was_active_dq != is_active_dq` and flipping player.state via
`_apply_sanction_to_tournament(dq_state=...)`. A faithful "lift un-zeroes VP" test
needs a heavy engine-valid finished-tournament fixture (VP vectors, tables) that
largely re-proves the engine — not worth it; verify manually. See
[[project_engine_test_fixture_traps]].
