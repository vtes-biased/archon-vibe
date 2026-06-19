---
name: error-localization-offline-path-trap
description: Engine-error localization covers all three throw surfaces (HTTP, offline WASM, JS pre-checks); wired — preserve when changing error presentation
metadata:
  type: project
---

Offline-first makes the optimistic WASM write locally authoritative — the server never sees a rejected action — so the message a user sees offline comes from WASM/JS, not the backend. Engine-error localization therefore must reach THREE throw surfaces, and currently does:

1. **Backend HTTP** — `routes/tournaments.py` rejection → `ApiError.code`.
2. **Offline WASM** — `engine.ts` wraps `processTournamentEvent` and re-throws a typed `EngineError`; `errors.ts` `toUserMessage` has an `EngineError`-first branch (`errorCodeToMessage(code, params)`) before the English fallback.
3. **JS pre-checks** — `checkPlayerBarred` throws (suspended/league-DQ) before WASM runs.

**How to apply:** this is implemented — when changing error presentation, KEEP all three code-mapped. Localizing only the HTTP body silently leaves the whole offline path English.
