# #284 — Disqualified players: rank last + no RTP

## Spec (owner-confirmed)

"Removed from standings" (JG v2 §1.1.4) means, for this app: a DQ'd player **still
appears**, sorted **last**, flagged **disqualified** — not given a competitive place
among the others.

- **Standings:** their own VP / GW / TP show as **0** (they forfeit their score). They
  are **not** given a numeric rank (UI shows "—" + the existing Disqualified badge).
- **Opponents keep VPs earned against them:** the DQ'd player's *seat* is untouched, so
  per-table GW/TP for everyone else is computed exactly as before. Only the DQ'd
  player's aggregated standings row is zeroed.
- **RTP:** the DQ'd player earns **no rating points at all** — not even the 5-point
  participation base, no finalist bonus, no rating-history entry for that tournament.
- **Player count stays inclusive:** the DQ'd player still counts toward `player_count`
  for everyone else's finalist coefficient (tournament-rules.md A.2 line 783 — "the
  players count includes disqualified players … as long as they played ≥1 round").

## DQ signal

Two signals, both set together by the backend on a DQ sanction (routes/sanctions.py):
player `state == "Disqualified"` **and** an active `disqualification` sanction. Engine
standings/rating treat either as DQ (`state || has_dq_sanction`), matching the
check-in skip logic; the finals filter (mod.rs) already keys off state.

## Touch points

- `engine/src/tournament/standings.rs` — `Standing { disqualified }`, zero + sort-last in
  `compute_preliminary_standings`, serialize in `update_standings`, DQ bucket in
  `compute_final_standings`, `(0,0)` early-return in `compute_rating_vp_gw`.
- `backend/src/ratings.py` — skip the rating entry for a DQ'd player (no RTP); keep
  `_player_count` inclusive.
- `backend/src/routes/sanctions.py` — recompute standings on DQ **create** (lift/delete
  already do), so the zeroing takes effect immediately, not on the next event.
- `frontend` — `StandingEntry { disqualified }`, derive DQ set + zero + sort-last in
  `computeStandings`, `getRatingPts` → 0 for DQ, suppress rank number (show "—") in
  `PlayersTab`.

Out of scope: mid-game game-state adjustment (§1.1.4 predator/prey), finals-DQ restart
(§3.7), prize reclamation — unchanged.
