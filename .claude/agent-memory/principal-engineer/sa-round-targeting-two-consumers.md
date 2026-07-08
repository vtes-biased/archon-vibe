---
name: sa-round-targeting-two-consumers
description: SA −1 VP has THREE engine consumers (prelim-standings + rating GW/TP cascades, VP total, SetScore); all route through resolve_sa_effective_rounds — do not re-derive the effective round independently in any of them.
metadata:
  type: project
---

The SA (standings_adjustment) −1 VP penalty resolves via `resolve_sa_effective_rounds(tournament, sanctions)` in `engine/src/tournament/sanctions.rs`. THREE call sites consume that resolver (grep before changing the resolver or `table_sa_adjustments`/`sa_vp_penalty` signatures):
- `compute_preliminary_standings` (standings.rs) — GW/TP cascade via `table_sa_adjustments`, VP total via `sa_vp_penalty`.
- `compute_rating_vp_gw` (standings.rs) — same pair, prelim rounds only (finals VP/GW read from the finals seat's stored `result`, where SA never lands).
- **SetScore** (mod.rs ~1636/1715) — score-time `table_sa_adjustments` for the frozen `result.gw`/`result.tp`. Those frozen values are display-only; standings/rating always RECOMPUTE from raw VP, so a later cancel/round-add that staleifies them is harmless.

The shared resolver is the fix for the old divergence hazard — do NOT re-derive the effective round independently in any consumer.

**Effective round rule (JG v2 §1.1.3):** the round the player is **currently seated in a NON-cancelled table** if a game is in progress, else the **highest round index they are seated in non-cancelled** (most recently played). Never a future round. A seat in a soft-cancelled table does NOT anchor an SA — `seated_in` filters `state == "Cancelled"` so the effective round is provably one both cascades visit (they `continue` past Cancelled), keeping VP and GW/TP on the same round. `None`/state-less tables count (not Cancelled). An SA whose stored `round_number` the player wasn't seated non-cancelled in (drop/sit-out/import/soft-cancel) redirects to their most-recently-seated non-cancelled round — which for a soft-cancelled MIDDLE round (#295) can be LATER than the stored round; that is rule-correct, not a bug. A player with NO non-cancelled seat contributes nothing — do NOT fall back to round 0.

**Invariants:**
- Two SAs on one player stack to −2 (don't dedup to a per-player set).
- VP can go negative — intended, no clamp.
- Finals is never an SA target; the resolver only scans `tournament["rounds"]`, not the finals table.
- The UI auto-computes and shows the target round read-only — there is no free round picker for SA.
- `round_number` on the sanction is the **fixed issue-time record** of the game the judge ruled on; the engine may redirect it, but never stores the redirected value back.

See [[sa-standings-recompute-on-sanction-mutation]] (recompute trigger) and [[sa-penalty-duplicated-in-python]] (single-sourced in Rust).
