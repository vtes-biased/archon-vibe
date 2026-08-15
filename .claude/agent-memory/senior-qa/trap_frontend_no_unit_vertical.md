---
name: trap-frontend-no-unit-vertical
description: The frontend has NO unit-test runner (no vitest anywhere) and tournament-utils.ts "pure" helpers secretly call the WASM engine — a Node unit test would only exercise the degrade fallback.
metadata:
  type: project
---

Two compounding reasons a "just add a small unit test for this frontend helper"
request should almost always come back as **no test**:

1. **There is no unit-test vertical.** `frontend/package.json` has only
   `check` (svelte-check), `test:e2e` / `test:e2e:ui` / `test:e2e:headed`
   (Playwright) and `test:smoke`. `vitest` appears **nowhere** in the repo —
   the only grep hits are `.claude/agents/senior-qa.md` (this agent's own
   anti-pattern list) and its worktree copy. Requests sometimes assert
   "there are vitest unit tests"; verify before believing it. Adding one means
   standing up a whole runner + config + CI wiring for a single test, which the
   agent brief explicitly forbids.

2. **`tournament-utils.ts` is not pure.** It imports from `./engine`
   (`computeFinalStandings`, `computeRatingPoints`, `computeRatingVpGw`,
   `rankingEligibility`). `computeFinalStandings` does
   `const engine = getEngineReactive(); if (!engine) return [];` then calls
   into WASM. Outside a browser the engine is null, so `computeStandings`
   always takes its `if (!ranked.length)` "degrade to preliminary order"
   safety-net branch. A Node-side test therefore asserts the **fallback sort**,
   never the engine's real placement logic (winner 1st / finalists tied 2nd /
   non-finalists 6+) — it would verify the absence of the engine.

**How to apply:** ranking/placement semantics belong in Rust
(`engine/src/**` `#[cfg(test)]`, where `compute_final_standings` already
lives); rendering belongs in Playwright E2E. The TS layer in between is
marshalling, and svelte-check plus the E2E lifecycle spec is the coverage it
gets. See [[project_engine_test_topology]].
