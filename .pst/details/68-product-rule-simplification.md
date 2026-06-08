# EPIC #68 — Product-rule simplification

**Goal:** hunt for *product rules / decisions* whose existence forces complex code or UI
acrobatics, and simplify, drop, or merge them so the product is easier to build, explain, and
understand.

**Distinct from #47.** `#47` targets *code ceremony* (passthrough wrappers, boilerplate, file
scoping). This epic targets *product rules* — simplifying the rule deletes whole branches of code,
UI states, and edge cases. Different axis, same "discuss-each-child-before-touching-code" model.

## Method

Candidates drawn from PRODUCT.md §3-4 and §7 (Key Domain Edge Cases), then **grounded in code**
and checked against the official rule text (`reference/tournament-rules.md`,
`reference/judges-guide-v2.md`). Each was classified VEKN-mandated (immovable) vs Archon product
choice (negotiable).

## Headline finding

Prose-level "this looks complex" was **wrong 3 of 4 times** once grounded. Most scoring complexity
is VEKN-mandated and load-bearing. The single highest-value discovery was **not** a simplification —
it was a **correctness bug** in Score-Adjustment scoring, surfaced by reading the engine closely.
Lesson: the payoff is in grounding + rule-conformance audits, not prose-level "looks complex."

## Scorecard

| Item | First read | Reality after grounding | Outcome |
|------|-----------|------------------------|---------|
| C/B — standings visibility + member matrix | "simplify the 21-cell matrix" | Matrix isn't enforced at all; `standings_mode` is frontend display chrome | **Doc fix → #70** (no code win) |
| **SA scoring (G)** | "clean, just fix the doc" | **Broken**: TP + standings VP ignore the −1; only GW applies it | **Bug → #67** (fix also simplifies) |
| **Timer (K)** | over-engineered | Confirmed + a latent uncapped-resume bug | **Simplify → #69** |
| M — sanction escalation | "drop the auto-escalation engine" | ~14 lines of faithful, non-binding hints over JG-v2 reference tables; serves non-judge organizers | **Keep** |
| O — raffle pools | trim 5→2 | Pools are one-line read-only predicates, zero coupling, genuinely useful | **Keep** (#71 closed after discussion) |
| J — multideck 2 finals methods | "soften / hide" | Two-method code **doesn't exist**; doc already describes a manual procedure | **Leave** (phantom) |

## Per-item verdicts

### C/B — Standings visibility & the member matrix → #70 (docs)
- `compute_tournament_member` (`access_levels.py:147`) ships everything except `checkin_code` +
  `vekn_pushed_at` to **all** members. Full `rounds`/`finals`/per-player results are in every
  member's IndexedDB during ongoing events.
- `standings_mode` (Private/Cutoff/Top 10/Public) is enforced **only in the frontend**
  (`+page.svelte:268-291`).
- **Structural root cause:** "my tables" visibility is *viewer-specific*, but access is *per-row
  pre-computed columns* — physically can't filter per-viewer. So the backend ships all tables to all
  members and the frontend hides the rest. The §4 matrix is a promise the architecture can't keep.
- **Decision:** accept it (frontend hiding suits the threat model — nobody cracks IndexedDB to
  kingmake at a local event). Fix PRODUCT.md §4 to say member visibility is a *display default*, not
  an access boundary. **Keep all 4 modes** (cheap; `Cutoff` uniquely shows the 5th-place finals
  threshold). Making it "real" would need a per-player overlay = *more* acrobatics; rejected.
- **Reusable lesson:** viewer-specific visibility fights pre-computed per-row columns — weigh this
  before any new "only X can see Y" feature.

### SA scoring → #67 (bug, filed standalone)
- Not part of this epic (it's a correctness bug, not a simplification) but **found during this
  hunt** and the fix *also* simplifies (delete the bespoke overflow carve-out). See #67.
- Short version: the −1 VP penalty reaches GW correctly but is **ignored by TP** (`compute_tp` uses
  raw VP, `mod.rs:1339`) and **under-applied to standings VP** (`standings.rs:59-61` only subtracts
  `1.0 − raw_vp`, and only when `raw < 1.0`). Diverges from JG v2 §1.1.3 + its worked examples.

### Timer → #69
- Collapse `time_extension_policy` to additions-only. See ticket for the deletion list + the latent
  uncapped-`clock_resume` bug. Online-only, zero compliance risk.
- **Meta-lens:** the *entire* timer serves only **online** events; the product headline is
  offline-first (offline tournaments have no timer). Good test for any candidate: *is the corner
  we're complicating even on the main road?*

### M — Sanction escalation → KEEP (no ticket)
- The "auto-escalation engine" is ~30 lines of `$derived` state +
  `BASELINE_PENALTIES`/`ESCALATION_SEQUENCE` (`types.ts:112-147`) — both **transcribed from JG v2**
  (the sequence is verbatim §1.2.1). Hints are **non-binding**; the organizer still picks freely.
- PM premise ("judges are certified, don't hand-hold") is wrong here: judge certs are *profile
  titles, not permissions* (PRODUCT.md §2.1); events are often run by a Prince who isn't a certified
  judge. The hint helps exactly that non-expert. Removing it saves ~14 lines and *removes* value.

### O — Raffle pools → KEEP (#71 closed after discussion)
- Reversed on discussion. Each pool is **one declarative read-only predicate** over data that
  already exists (`played`, `standings.gw/vp`, `finalists`). Marginal cost of the 3 "extra" pools
  beyond All+NonFinalists ≈ 3 Rust arms + 3 TS cases + 3 i18n labels. No mutation, no schema, no
  migration risk, zero coupling to fragile subsystems. The 5 pools map to real prize-draw intents.
- Trimming removes useful options for a rounding-error of code → worse product. **Keep all 5.**
- The Rust↔frontend duplication (`get_raffle_pool` ↔ `eligibleForPool`, `raffle.rs:25`) is
  **eliminable, not inherent**: `get_raffle_pool` is `pub(super)` and simply not exported in
  `lib.rs`. The WASM engine is available to the frontend (same one used for offline
  `processTournamentEvent`), with precedent for read-only exports (`compute_final_standings_json`,
  `compute_player_issues_json`, …). A `computeRafflePools` export would delete `eligibleForPool` and
  make the engine the single source of truth. It was kept in TS as a **locality tradeoff**: the WASM
  boundary is stateless JSON-in/out (serialize the whole tournament per call), whereas the TS filter
  works over data already in hand and needs all 5 counts reactively. Leave it (5 trivial predicates,
  `feedback_locality_over_dry`); if the copies ever drift into a bug, export the fn rather than trim
  pools.

### J — Multideck → LEAVE (no ticket)
- No multideck-finals-method enum exists; `multideck` is a `bool` + per-round deck indexing. The
  "Best-Performing / Free Choice" methods are a **manually-announced procedure** (app records decks,
  like finals seating) and PRODUCT.md already frames them that way. No code complexity to remove.

## Cross-references
- #67 — SA scoring bug (related; found here; fix simplifies)
- #69 — timer additions-only
- #70 — PRODUCT.md §4 visibility doc-fix
- #71 — raffle pools 5→2 (CLOSED — discussed, decided keep all 5)
- #47 — code-quality epic (sibling axis; raffle Rust↔frontend dup belongs there)
- #19 — seating.rs refactor (candidates E/F were examined: stagger is one algorithm not 288 lines;
  the 9 priorities are the measurement tables — both load-bearing, no product-rule simplification)
