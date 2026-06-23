---
name: player-authorized-engine-event-pattern
description: Non-organizer (player-authorized) tournament events — the existing CheckIn/SetScore pattern and the eligibility predicate landmines (state-set, concurrent-pod, mid-array round removal)
metadata:
  type: project
---

The engine already supports **player-authorized** (non-`require_organizer`) events. Two
exemplars to copy from when adding one:
- `CheckIn` (`engine/src/tournament/mod.rs` ~457): `if !actor.is_organizer && actor.uid != *player_uid { return Err(...) }`
- `SetScore` (~1396): `if !actor.is_organizer && !is_at_table { return Err(ScoreForbidden) }`

The HTTP layer does NOT gate `/action` by organizer (`tournaments.py` ~945 only requires
auth; `_build_actor_context` sets `is_organizer` from `permissions.is_organizer`, false for
a plain player). The engine is the sole authority — consistent with the authz model. So a
player-authorized event needs its full eligibility predicate IN THE ENGINE, fail-closed.

**Landmines a player-authorized round/seating event must respect:**
- **Eligible player-state set:** seat only `Checked-in`/`Completed`. Exclude `Registered`
  (never checked in; online flow self-checks-in via CheckIn) and `Playing` (already at a
  live table — accepting it is the two-concurrent-pods bug). StartRound accepts `Playing`
  for organizer parallel rounds (~697) and withdraws leftover `Registered`→`Finished`
  (~812); a player-authorized path must do NEITHER.
- **Dual DQ signal:** check both `players[idx].state == "Disqualified"` AND
  `has_dq_sanction(sanctions, uid)` (+ `has_active_suspension`). The engine uses the
  combined signal everywhere — see [[dq-signal-divergence-traps]].
- **Per-player cap:** gate on `count_player_rounds_played(...) < max_rounds` (helpers.rs ~10)
  — see [[open-rounds-per-player-cap]].
- **Mid-array round removal is unsafe** (so a "soft cancel non-last round" is NOT a cheap
  MVP): round indices are positional in SetScore/Override/SwapSeats (`round: usize`),
  `count_player_rounds_played` counts seated rounds (shifting it un-caps players), and decks
  are keyed by per-player round index (`is_deck_locked`, helpers.rs ~25). CancelRound
  refuses non-last for exactly this (`OnlyLastRoundCancellable`, ~909). Organizer veto of a
  non-last single-table pod = `Override` (index-safe, organizer-gated), not a round removal.
- **Start≠finish authority:** letting a player *start* a round doesn't let them *finish* it.
  `FinishRound` is `require_organizer` (~821) — don't silently relax it; flag the
  half-autonomy to PM instead.

**Why:** distilled from the #274 (self-organized rounds) trust-boundary review.
**How to apply:** when any new event lets a non-organizer mutate rounds/seating/scores,
walk this list; the state-set and concurrent-pod guards are the easy-to-miss ones.
