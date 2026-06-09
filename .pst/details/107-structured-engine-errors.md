# Structured engine error codes → localized frontend mapping

Goal: replace free-text English engine errors with a stable `{ code, params }` contract so the
frontend can render localized, audience-appropriate messages, and so user-facing domain
rejections are distinguished from internal errors.

## Problem

Every WASM/PyO3 export is `Result<String, String>` with errors built via `.to_string()`
(`engine/src/lib.rs`, `engine/src/cards.rs`, `engine/src/league.rs`). Consequences:
- English-only; invisible to paraglide i18n.
- Mixes **domain rejections** a TO needs verbatim ("table needs 4 or 5 players") with **internal
  errors** that are alarming noise ("JSON parse error: …").
- Thrown as a JS string, so the frontend's `e instanceof Error` catch shape drops it (see #101 / #102).

## Proposed design

### Rust core
- Define `EngineError { code: &'static str, params: BTreeMap<String, String> }` (stable codes, e.g.
  `tournament.round.bad_table_size`, `deck.invalid_card_id`, `actor.not_organizer`).
- Split internal failures (parse/serialize/invariant) from domain rejections — internal ones map to
  a single `internal` code (logged with detail server-side, generic to the user).
- Serialize `EngineError` to JSON on the `Err` arm. WASM: throw the JSON (or a typed object). PyO3:
  raise a typed exception carrying code+params.

### Backend
- Map the PyO3 engine exception into the HTTP error body so `detail` carries `{ code, params }`
  (keep a human `message` for non-i18n clients / logs). SSE/action endpoints included.

### Frontend
- `ApiError` gains `code?: string` and `params?: Record<string,string>`.
- `errorCodeToMessage(code, params)` maps to paraglide keys in all 5 locales; fallback order:
  code → existing `detail` text → generic `m.error_unexpected()`.
- The #102 mapper prefers code-based localization when present; the `typeof e === 'string'`
  passthrough becomes the legacy path until all surfaces emit codes.

### i18n
- One paraglide key per public error code, in `frontend/messages/{en,es,fr,it,pt}.json`,
  with `{param}` interpolation. Internal/`internal` code → generic localized string.

## Sequencing
- #102 ships the string-passthrough stopgap first (precision now, English).
- This ticket supersedes the passthrough as codes land; can be rolled out surface-by-surface
  (tournament actions first — highest traffic — then deck validation, league, sanction).

## Review
Cross-stack: Rust core + WASM + PyO3 + backend HTTP + frontend + i18n. Needs principal-engineer
sign-off on the error taxonomy and the backend error-body shape before implementation.
