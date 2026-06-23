---
name: open-rounds-non-vekn
description: open_rounds/self_organized_rounds are the non-VEKN house flag; where the "never push / never rate" invariant is enforced + tested.
metadata:
  type: project
---

`open_rounds` (and its sub-option `self_organized_rounds`) is a persisted Tournament bool marking a house event that is NOT reported to VEKN and does NOT count toward ratings/RTP. Engine carries it inertly (JSON config flag, no PyO3/WASM signature change — same pattern as `self_organized_rounds`, commit 55fb51d); `max_rounds` still drives the per-player cap. Supersedes the older `self_organized`-only push guard (pst #297).

**Why:** organizers needed a house open-rounds format that is byte-identical to a standard VEKN event except for the flag (same `max_rounds=3`, rounds, vekn id) — so the flag is the ONLY thing keeping its results out of the public VEKN registry and out of rankings.

**How to apply (test surface):**
- The "never push to VEKN" invariant lives in the SHIPPED queries `UNPUSHED_RESULTS_QUERY` / `UNCREATED_EVENTS_QUERY` in `vekn_push.py` (clauses `("full"->>'open_rounds') IS DISTINCT FROM 'true'`, same for self_organized_rounds) + a belt-and-suspenders early-return in `push_tournament_event`. `IS DISTINCT FROM` (not `!= 'true'`) is deliberate: legacy rows predating the flag have `->>` = NULL and must STAY in the push set. Covered by `test_vekn_push_batch.py::test_push_queries_exclude_open_and_self_organized_rounds` — extends the existing `_tournament` factory + real-DB-save + imported-query structure. Mutation-verified (removing the guard leaks open/self-org events into the selection).
- The full projection (`compute_tournament_full` = `dict(d)`) passes the bool straight into the `full` JSONB column the queries read — no explicit access_levels wiring needed.
- The "never rate" half is an in-Python list filter in `ratings.py` (`recompute_ratings_for_players` ~line 192, `recompute_all_ratings` pass-1 ~line 255: skip `t.open_rounds or t.self_organized_rounds`). Deliberately NOT given its own test: it's a one-line `if` over the implementation, exercising it needs a heavy engine-valid finished-tournament seed, and the user-visible third-party consequence is the push path. [[project_seating_determinism]]-style in-code skips don't clear the interface bar.
