---
name: error-codes-contract
description: Structured engine error-code contract — code/params wire format spanning Rust, WASM, PyO3, HTTP, frontend i18n
metadata:
  type: project
---

`EngineError` (engine/src/error.rs) is the single greppable error taxonomy: enum variants with typed payloads; `code()` returns stable `tournament.*`/`deck.*`/`seating.*`/`internal` strings that map 1:1 to paraglide `err_*` keys (dots→underscores). `Display` English is byte-identical to `frontend/messages/en.json`. Wire format on the Err arm = `{"code","params","message"}` JSON, identical across WASM (`js_str`) and PyO3 (`py_str`) shims in lib.rs.

**Why:** errors were free-text English strings, invisible to i18n and mixing domain rejections with internal noise.

**How to apply:**
- New fallible engine fn returns `Result<T, EngineError>`. Domain rejections MUST construct an explicit variant — never `.ok_or("msg")?` / `Err("msg".into())`, because `From<&str>/From<String>/From<json::Error>` ALL collapse to `Internal{detail}` (silent demotion to a generic logged message). Those From impls exist only for genuine parse failures and `…required` schema-validation notes (parsing.rs), which are correctly internal-class.
- Adding a public variant requires: enum arm + `code()` + `params()` (if parametrized) + `Display` arm, plus an `err_*` key in ALL 5 locales and a `ENGINE_MESSAGES` registry entry in frontend/src/lib/error-codes.ts. Params are stringified end-to-end (`size.to_string()`), no numeric leak.
- Backend: engine `ValueError` → `EngineRejection.from_engine(e)` (engine_errors.py) → `@app.exception_handler(EngineRejection)` in main.py emits `{"detail","code","params"}` (detail stays English for the Discord bot / legacy clients). App-level checks that mirror engine rules (`_check_player_barred`) raise `EngineRejection` directly with the engine's own codes.
- Raising `EngineRejection` inside `tournament_transaction` (routes/tournaments.py action route) is sound: it propagates through `conn.transaction()` which rolls back the SELECT FOR UPDATE before the handler emits the 400. The custom-exception + registered-handler pattern is idiomatic FastAPI; the rollback is the context manager's job, not the handler's.
- Frontend: `toUserMessage` (errors.ts) order = EngineError/coded-ApiError → code-mapped localization FIRST, then English detail/message fallback, then legacy string, then network, then generic. `internal` code → log detail + generic message, never raw detail. `callEngine` (engine.ts) wraps the RAW WASM call (not the success `JSON.parse`); ApiError code/params wired only at the single apiRequest body-parse site (importArchonFile's self-built ApiError is intentionally untouched). JS pre-checks (`checkPlayerBarred`) throw coded EngineErrors so the offline path localizes identically — see [[error-localization-offline-path-trap]].
