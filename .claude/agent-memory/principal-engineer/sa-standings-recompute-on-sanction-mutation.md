---
name: sa-standings-recompute-on-sanction-mutation
description: SA sanction create/lift/delete/modify recomputes tournament.standings via the python-only update_standings_json engine entrypoint + _recompute_tournament_standings. Frontend reads standings, not raw seats.
metadata:
  type: project
---

Issuing / lifting / deleting / editing a `standings_adjustment` (SA) sanction tied to a tournament recomputes `tournament.standings` — `_recompute_tournament_standings()` in `backend/src/routes/sanctions.py` (load tournament → `_engine.update_standings` → save → broadcast), called from the create/update/delete endpoints whenever the new or prior level is SA. Mirrors the long-standing DQ path (`_set_player_dq_state`). Without it the SA −1 VP penalty only materialized on the NEXT tournament action (SetScore/FinishRound), leaving the "score the round, then dock a player" flow stale.

Engine entrypoint: `tournament::update_standings_json(tournament_json, sanctions_json) -> tournament_json` (`engine/src/tournament/mod.rs`), a thin wrapper over the internal `update_standings` (`engine/src/tournament/standings.rs`, `pub(super)`). Exposed **PyO3-only** (`PyEngine.update_standings`), NOT WASM — mirroring `compute_rating_vp_gw`, because sanctions have no offline-creation path (`createSanction` is a pure backend API call; offline, `processTournamentEvent` already recomputes standings with the IndexedDB sanctions). `update_standings` early-returns on rounds-less tournaments, so the recompute is a safe no-op for VEKN-synced data.

**Why:** SA penalty is single-sourced in Rust (see [[sa-penalty-duplicated-in-python]]) and lives only on the standings *total* (per-seat `result.vp` stays raw so the physical game state stays valid). Frontend `computeStandings` (`tournament-utils.ts`) seeds prelim totals from `tournament.standings`, not raw seats — trusting the engine. Both stacks consume the engine total; never re-derive SA in Python or TS.

**How to apply:** Any new sanction-route flow that changes an SA (or a new sanction-mutation path) must call `_recompute_tournament_standings(tournament_uid)` after the save — don't reintroduce the assumption that sanction writes skip the tournament recompute.

**Verified (2026-06):** `tournament.standings` survives the member/full access projection (`compute_tournament_member` is exclude-list `{checkin_code, vekn_pushed_at}`; only `compute_tournament_public` whitelist drops it). Organizer reads member/full, so reading standings is sound. `SetScore` calls `update_standings` on every score write (even mid-round In Progress).
