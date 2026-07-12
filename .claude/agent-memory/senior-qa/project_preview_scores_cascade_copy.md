---
name: preview-scores-cascade-copy
description: preview_scores_json (WASM previewScores) is a second copy of the SetScore GW/TP cascade — drift hazard, pinned by one equality test
metadata:
  type: project
---

`engine/src/tournament/mod.rs` holds TWO copies of the GW/TP scoring cascade
(`resolve_sa_effective_rounds` → `table_sa_adjustments` → `compute_gw`/
`compute_gw_finals` + `compute_tp`): the `SetScore` event handler (persisted
path) and `preview_scores_json` (the WASM `previewScores` binding, live UI
preview). They must stay byte-identical in output.

**Why:** duplicated scoring logic drifts; the ticket that added preview fixed a
UI preview silently diverging from the persisted score. Consequence of drift:
organizer sees one GW/TP while typing, a different one lands.

**How to apply:** when a QA pass touches SetScore scoring OR preview, treat them
as one invariant — a change to one path needs the other. The guard already
exists: `test_preview_scores_match_setscore_including_sa_cascade` in
`tests.rs` drives both shipped entry points on one table + candidate VPs with an
SA landing on the round (SA is load-bearing — it flips p2's GW) and asserts
`preview.gw/tp == SetScore-persisted gw/tp`. Don't add a second preview test;
extend this one if a new cascade branch appears. Preview is WASM-only (frontend
reads), no backend caller — no Python contract test needed, unlike the
[[project_engine_model_state_drift]] enum surface. `preview_scores_json`'s
finals sentinel is `round >= rounds.len()` (table ignored); SetScore's is
`round == rounds_len && finals present && table == 0` — same scoring output, the
divergence is only in which arg selects the finals table.
