---
name: error-localization-offline-path-trap
description: Localizing engine errors must cover the offline WASM path AND the JS pre-checks, or the offline-first scenario stays English
metadata:
  type: project
---

When mapping engine error codes → localized frontend messages (pst #107 design), the localization
must reach THREE throw surfaces, not just the backend HTTP one:

1. Backend HTTP rejection (`routes/tournaments.py` `except ValueError`) → `ApiError.detail`/`code`.
2. **Offline WASM path** — `tournament-actions.ts:173` re-throws the raw WASM value to the caller,
   which renders via `errors.ts` `toUserMessage`. `toUserMessage` has NO `EngineError` branch
   (only ApiError/string/TypeError/Error), so a wrapped `EngineError extends Error` falls through
   to the generic `.message` branch = English, never code-mapped. The offline-first scenario is
   exactly where localization matters most, so this is load-bearing.
3. **JS pre-checks** — `checkPlayerBarred` (`tournament-actions.ts:62/72`) throws plain English
   `new Error(...)` for suspended/league-DQ BEFORE WASM runs. These never carry a code.

**Why:** Offline-first means the optimistic WASM write is authoritative locally; the server never
sees a rejected action. So the message the user sees offline comes from WASM/JS, not the backend.
Localizing only the HTTP body silently leaves the whole offline path English.

**How to apply:** Any error-presentation change must (a) add an `EngineError`-first branch to
`toUserMessage` that runs `errorCodeToMessage(code, params)` before the English fallback, (b) make
`engine.ts` wrap the raw `engine.processTournamentEvent` call (catch thrown JSON string → re-throw
typed `EngineError`), distinct from parsing the success result, and (c) decide whether JS pre-checks
emit coded errors or are documented English-exempt. See [[project_authz_single_source_rust.md]] for
the related cross-stack single-source principle.
