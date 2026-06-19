---
name: sa-penalty-duplicated-in-python
description: SA (standings_adjustment) scoring is now single-sourced in Rust (engine.compute_rating_vp_gw); ratings.py/vekn_push.py delegate. Do NOT re-derive the SA penalty in Python again.
metadata:
  type: project
---

The standings_adjustment (SA) VP penalty / GW-flip / TP-rerank rule is **single-sourced in the Rust engine**. Do not re-implement it in Python.

- **Authoritative (Rust):** `engine/src/tournament/standings.rs` — `compute_preliminary_standings` (prelim-only, SA-adjusted standings) and `compute_rating_vp_gw` (finals-inclusive, for rating/VEKN). Both route per-table adjustments through `sanctions::table_sa_adjustments` → `scoring::compute_gw`/`compute_tp`, sum raw VP, then subtract `sanctions::sa_vp_penalty` (flat -1.0 per played-round SA, JG v2 §1.1.3; may go negative).
- **`backend/src/ratings.py`:** `_compute_entry_sync` calls `engine.compute_rating_vp_gw(t_json, sanctions_json, user_uid)`. The old `_sa_overflow_penalty` / `_player_stats` are DELETED.
- **`backend/src/vekn_push.py`:** `generate_archondata` / `_compute_entry_sync` thread real `sanctions` through, so pushed rating points (`{rtp}`) include SA. `{gw}/{vp}` fields read the (engine-SA-adjusted) `standing.gw`/`standing.vp`; `{vpf}` is finals VP read separately.

**Why:** the earlier 3-impl divergence (engine vs ratings.py overflow model vs vekn_push SA-blind) silently desynced official ratings from engine standings; a later cleanup collapsed it.

**How to apply:** when reviewing SA / VP-penalty scoring changes, confirm Python still delegates to `engine.compute_rating_vp_gw` and never re-derives the penalty from raw seats. The remaining latent gap is the Python archon importer hand-building standings — see [[standings-prelim-only-contract]]. Same single-source-in-Rust principle as [[authz-single-source-rust]].
