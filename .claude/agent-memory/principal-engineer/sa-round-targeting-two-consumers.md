---
name: sa-round-targeting-two-consumers
description: SA −1 VP has two engine consumers (per-table GW/TP cascade, VP total); both now route through resolve_sa_effective_rounds — do not re-derive the effective round independently in either consumer.
metadata:
  type: project
---

The SA (standings_adjustment) −1 VP penalty feeds two engine consumers in `engine/src/tournament/sanctions.rs`:
- `table_sa_adjustments(seating, round_index, sanctions)` — per-seat −1.0 vector for the GW/TP cascade, applied per table. Also called from **SetScore score-time scoring** — grep all callers before changing its signature.
- `sa_vp_penalty(sanctions, user_uid)` — VP-total penalty.

Both consume `resolve_sa_effective_rounds(tournament, sanctions)` (same file), which resolves each active SA to its effective round once. This shared resolver is the fix for the old divergence hazard — do NOT re-derive the effective round independently in either consumer.

**Effective round rule (JG v2 §1.1.3):** the round the player is **currently seated in** if a game is in progress, else the **highest round index they are seated in** (most recently played). Never a future round. An SA whose stored `round_number` the player wasn't seated in (drop/sit-out/import) is redirected to their most-recently-seated round. A player not seated in any round contributes nothing — do NOT fall back to round 0.

**Invariants:**
- Two SAs on one player stack to −2 (don't dedup to a per-player set).
- VP can go negative — intended, no clamp.
- Finals is never an SA target; the resolver only scans `tournament["rounds"]`, not the finals table.
- The UI auto-computes and shows the target round read-only — there is no free round picker for SA.
- `round_number` on the sanction is the **fixed issue-time record** of the game the judge ruled on; the engine may redirect it, but never stores the redirected value back.

See [[sa-standings-recompute-on-sanction-mutation]] (recompute trigger) and [[sa-penalty-duplicated-in-python]] (single-sourced in Rust).
