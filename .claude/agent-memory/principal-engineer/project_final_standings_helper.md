---
name: final-standings-helper
description: compute_final_standings is the single source of truth for VEKN final placement (winner=1, finalists tie 2nd); shared by league GP/RTP and frontend post-finals display
metadata:
  type: project
---

`engine/src/tournament/standings.rs::compute_final_standings(standings, winner) -> Vec<JsonValue>` is the shared "who placed where" computation. Reordered + `rank`-tagged: winner→1, other flagged finalists→shared 2, non-finalists→competition ranking (shared+skip) from finalist_count+1.

**Why:** Introduced fixing GP league-scoring bug #43 — prior GP/RTP ranked on prelim array order, so the prelim leader (not the finals winner) scored rank 1. Extracted so league scoring (league.rs GP+RTP) and the upcoming frontend post-finals results display share one implementation instead of duplicating placement logic.

**How to apply:** Any new consumer of "final placement" (display, exports, awards) must call this via WASM `computeFinalStandings` / PyO3 `compute_final_standings`, not re-derive from prelim order or array index. It assumes the input `standings` is already deterministically sorted (compute_standings ranks on the 3-field gw/vp/tp key with a terminal `user_uid` tiebreak for array order). The "finalist flag present ⇒ finals happened" heuristic means imported finals data lacking finalist flags degrades to prelim ranking with only the winner pulled to 1st.
