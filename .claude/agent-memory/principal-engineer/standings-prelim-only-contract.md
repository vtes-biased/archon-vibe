---
name: standings-prelim-only-contract
description: tournament.standings is prelim-only (SA-adjusted, finals excluded); the Python archon importer violates this by storing finals-inclusive standings → league double-counts finals
metadata:
  type: project
---

`tournament.standings` is **preliminary-only and SA-adjusted** — finals GW/VP/TP are NOT included. The engine codifies this: `engine/src/tournament/standings.rs::compute_preliminary_standings` recomputes GW/TP per table from raw seat VPs + current sanctions (via `sanctions::table_sa_adjustments` → `scoring::compute_gw`/`compute_tp`), sums raw VP, then subtracts the full `sa_vp_penalty`. Stored seat `result.gw`/`result.tp` are frozen "as scored" for display and are deliberately ignored by standings/rating (so a late standings_adjustment still flips the GW and re-ranks TP, JG v2 §1.1.3). `compute_rating_vp_gw` is the finals-INCLUSIVE sibling (reads stored finals GW, which is provably SA-free since `sanctions.py:202` rejects SA `round_number >= len(rounds)` and finals isn't in `rounds`).

Consumers that rely on prelim-only standings + add finals separately: `engine/src/league.rs` RTP/GP modes (re-add `tournament["finals"]` seats on top), frontend `leagues/[uid]/+page.svelte` via `computeLeagueStandings`.

**Violation (pre-#67, surfaced by #67):** `backend/src/archon_import.py` (~lines 401-403, 438-447) hand-sums finals gw/vp/tp INTO `tournament.standings`. An imported tournament in a league therefore **double-counts finals** in RTP/GP, and its standings GW won't match a prelim recompute.

**Why:** pst #67 single-sourced the SA scoring rule into Rust and made "standings = SA-adjusted prelim" the explicit engine contract; the Python importer builds state by hand instead of routing through the engine, so it drifted.

**How to apply:** any change touching imported-tournament standings, league scoring, or the standings shape must keep stored standings prelim-only. Prefer routing imports through `engine.update_standings` over hand-summing in Python. See [[sa-penalty-duplicated-in-python]] and [[final-standings-helper]].
