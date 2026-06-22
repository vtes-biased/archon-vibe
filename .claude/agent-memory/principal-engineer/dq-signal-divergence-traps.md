---
name: dq-signal-divergence-traps
description: DQ status is a dual signal (player.state || active DQ sanction); audit every consumer for it, and recompute standings on any DQ sanction mutation
metadata:
  type: project
---

DQ status is a **dual signal**: `player.state == "Disqualified"` OR an active disqualification sanction (`has_dq_sanction`). The in-app flow sets both together (`_set_player_dq_state` + the sanction), but consumers have diverged on which they read — standings/rating/check-in use the combined signal while the finals-eligibility filter was once **state-only**, so a DQ'd-by-sanction player could slip through. Standings now carry a `disqualified` flag (the resolved dual signal) that downstream code should key off rather than re-deriving.

**Why:** found during #284. A state-only check silently disagrees with a sanction-only DQ, and `CancelFinals` flips `finalist` players back to Checked-in without clearing `finalist` — so a state-only finals filter could resurrect a DQ'd finalist.

**How to apply:** when touching any DQ-gated path, grep for BOTH `has_dq_sanction` and `"Disqualified"` and make the new path use the same combined signal (or the persisted `disqualified` flag). Don't trust `player.state` alone.

Related trap, same area: a sanction is **not a TournamentEvent**, so stored standings only refresh when `routes/sanctions.py` explicitly calls `_recompute_tournament_standings` (`save_tournament`/`_set_player_dq_state` do NOT recompute). Every DQ path that changes who's disqualified — create, lift, AND delete — must pair the state change with a recompute, or stored standings go stale (e.g. lifted-DQ scores stay zeroed). See [[sa-standings-recompute-on-sanction-mutation]].
