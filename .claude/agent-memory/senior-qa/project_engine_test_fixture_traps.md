---
name: engine-test-fixture-traps
description: Engine tournament test fixtures (tournament_with_round, waiting_after_round) carry engine-impossible stored VP vectors — safe only because standings code never re-validates them.
metadata:
  type: project
---

Several engine tournament-test fixtures in `engine/src/tournament/tests.rs` contain
**engine-impossible stored table states** that are inert only by luck of which code path reads them.

- `tournament_with_round()` (~line 1008): table 0 stored result is `[vp 2, 1, 0.5, 0.5]`
  → ceil-sum = 5 ≠ table size 4. An impossible scored table. Tests that overwrite all
  four seats (e.g. AlterSeating swap tests, the new Waiting-correction test) never feed
  this vector to `check_table_vps`, so it stays harmless. Table 1 starts "In Progress"
  with all-zero VPs (a legitimately *unscored* table).
- `waiting_after_round()` (added with the out-of-round-correction fix): builds on
  `tournament_with_round()` but **overwrites both tables to a valid finished vector**
  `[2,1,1,0]` (ceil-sum 4, valid oust, p1/p5 win) before flipping state to Waiting — so
  this fixture is clean. (Its first draft left table 1's all-zero VPs while marking it
  "Finished" → an impossible *finished* table; that was the trap, now fixed.) Such a
  stored table would have been inert anyway: `update_standings` /
  `compute_preliminary_standings` (standings.rs) only **sum raw VP and recompute GW/TP**
  via `compute_gw`/`compute_tp`; they never call `check_table_vps`. An impossible stored
  table doesn't reject — it just contributes its (raw) VP.

**Why:** `check_table_vps` (scoring.rs) is the *only* validator and runs solely inside
the `SetScore` handler on the freshly-submitted vector — never on already-stored seat
results during standings recompute. So a fixture can hold an impossible stored table and
every existing test still passes.

**How to apply:** When reviewing or writing a NEW engine test that asserts a
*full-tournament standing* (not just one edited table), do NOT build on these fixtures'
untouched tables — overwrite every table you depend on with a valid vector (ceil-sum ==
table size, valid oust order, or all-`0.5` timeout). Otherwise the impossible stored
table silently skews the baseline. Single edited-table tests are fine as-is.
See [[engine-test-topology]] for how to run these suites.
