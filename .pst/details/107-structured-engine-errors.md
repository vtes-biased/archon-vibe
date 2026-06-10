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

## Design (concrete — for principal-engineer sign-off)

### Rust core: `engine/src/error.rs`

`EngineError` is an **enum with typed payloads** (not a code+map struct): params are checked at
construction, and the three projections (code string, params map, English message) live in one
file as exhaustive matches — the taxonomy is a single greppable artifact.

```rust
pub enum EngineError {
    // tournament.* — domain rejections (user-facing, localized by frontend)
    NotOrganizer,
    AlreadyRegistered,
    WrongState { expected: String, current: String },
    InvalidTableSize { size: usize },
    TablesNotFinished { tables: String },   // pre-joined, 1-based: "2, 4"
    // …
    // internal — anything the user can't act on (parse/serialize/invariant/enum drift)
    Internal { detail: String },
}

impl EngineError {
    pub fn code(&self) -> &'static str { /* "tournament.not_organizer" | … | "internal" */ }
    pub fn params(&self) -> Vec<(&'static str, String)>;
    pub fn to_json(&self) -> String;  // {"code":…,"params":{…},"message":"<English>"}
    pub fn internal(detail: impl std::fmt::Display) -> Self;
}
impl Display for EngineError { /* canonical English, byte-identical to messages/en.json */ }
impl From<json::Error> for EngineError { /* -> Internal */ }
```

All core signatures change `Result<T, String>` → `Result<T, EngineError>` (tournament, helpers,
parsing, raffle, seating, deck, cards, league, permissions `from_json`, lib.rs `shared`).
`json::parse(x).map_err(|e| e.to_string())?` collapses to `json::parse(x)?` via the `From` impl.
Engine tests keep their `.contains(…)` assertions via `.unwrap_err().to_string()`.

### Binding surfaces (ABI unchanged: still `Result<String, String>` / `PyResult<String>`)

- **WASM** shim: `.map_err(|e| e.to_json())` — JS still receives a thrown string, now JSON.
- **PyO3** `py_str`: becomes `py_str(r: Result<String, EngineError>)` with
  `.map_err(|e| PyValueError::new_err(e.to_json()))` — still `ValueError`, message is now JSON.
  Note this is the **shared helper**: every PyO3 method (permissions, seating, deck, league)
  now emits JSON ValueErrors, not just the action one. Existing `except ValueError` sites keep
  working.
- Domain validation of *already-parsed* JSON must construct an explicit `EngineError` variant —
  never lean on `From<json::Error>` (that impl exists only for genuine deserialization failures,
  which are `internal` by definition).

### Backend HTTP error body

Body stays backwards-compatible: `detail` remains the human English string (bot's
`_extract_error` and all existing frontend handling unchanged); `code`/`params` are **added at
top level**:

```json
{ "detail": "Already registered", "code": "tournament.already_registered", "params": {} }
```

Mechanics: `backend/src/engine_errors.py` (new) parses the ValueError message
(JSON → code/params/message; non-JSON → legacy passthrough as detail-only) and raises a small
`EngineRejection` exception; an `@app.exception_handler(EngineRejection)` in main.py emits the
400 JSONResponse above. The action route's `except ValueError` (routes/tournaments.py:903)
switches to this. Other engine call sites (permissions, ratings, users) don't catch — engine
errors there are `internal`-class and keep surfacing as 500s with the JSON detail in logs.

### Frontend

- `ApiError` gains `code?: string`, `params?: Record<string, string>`, wired at the **single**
  `apiRequest` body-parse site (api.ts:79-87). `importArchonFile`'s self-built ApiError is left
  alone (not engine-rejection-class).
- New `EngineError extends Error` class with `code`/`params`. `engine.ts` wraps the **raw**
  `engine.*` WASM calls in try/catch (i.e. around the call itself, distinct from `JSON.parse` of
  the *success* result): a thrown string that parses as `{code,…}` JSON re-throws as
  `EngineError` (message = English from the payload). Non-JSON strings keep the #102 legacy
  passthrough.
- The JS pre-checks in `tournament-actions.ts` (`checkPlayerBarred`) throw **coded**
  `EngineError`s (`tournament.player_suspended` / `tournament.player_disqualified`) instead of
  plain English `Error`s, so the offline path is localized end-to-end — same condition, same
  message as the WASM/server path.
- `errors.ts`: `errorCodeToMessage(code, params): string | undefined` — a
  `Record<code, (p) => string>` registry over paraglide `err_*` keys (code dots → underscores:
  `tournament.already_registered` → `m.err_tournament_already_registered()`). Lookup is
  `registry[code]?.(params)` — a missing key (incl. *future* codes from a newer backend under
  version skew) falls through safely, never throws.
  `toUserMessage` order: **`EngineError`/`ApiError` with code → code-mapped localization first**,
  then `detail`/`message` English fallback → legacy string → network → generic. Code `internal`
  (or unknown code with no usable message) → log + generic `m.error_unexpected()`-class message,
  NOT the raw detail.

### i18n

One `err_*` key per public code in `frontend/messages/{en,es,fr,it,pt}.json`, `{param}`
interpolation (params are **strings end-to-end** — Rust `params()` stringifies, HTTP carries
strings, no `usize`-as-number leaks). **en.json values byte-identical to the Rust `Display`
English** so the bot and any text expectations see the same strings. Where the taxonomy merges
sites, the canonical English intentionally changes at the merged sites (see test touch-points).

## Error-code taxonomy (full inventory, ~50 public codes)

Sites merged where the user-meaning is identical (register/check-in variants of VEKN-id,
suspended, disqualified; upload/delete variants of deck locks). `{…}` = params.

**Authorization**
| code | English |
|---|---|
| tournament.not_organizer | Only organizers can perform this action |
| tournament.create_forbidden | Only IC, NC, or Prince can create tournaments |
| tournament.unregister_only_self | You can only unregister yourself |
| tournament.drop_out_forbidden | Only organizers or the player themselves can drop out |
| tournament.check_in_forbidden | Only organizers or the player themselves can check in |
| tournament.deck_upload_forbidden | Only organizers or the player can upload a deck |
| tournament.deck_delete_forbidden | Only organizers or the player can delete a deck |
| tournament.score_forbidden | Not authorized to score this table |
| tournament.score_locked | Table score is locked by judge |
| tournament.score_set_by_organizer | Score has been set by organiser |
| tournament.league_link_forbidden | Only league organizers can link tournaments to this league |

**Registration / eligibility**
| code | English |
|---|---|
| tournament.vekn_id_required | Player must have a VEKN ID |
| tournament.already_registered | Already registered |
| tournament.not_registered | Player is not registered in this tournament |
| tournament.player_disqualified | Player is disqualified and cannot participate |
| tournament.player_suspended | Player is suspended and cannot participate |
| tournament.player_not_found | Player not found |
| tournament.player_not_checked_in | Player is not checked in |
| tournament.player_already_finished | Player already finished |
| tournament.player_wrong_state {current} | Player must be Registered (currently {current}) |

**State machine**
| code | English |
|---|---|
| tournament.wrong_state {expected, current} | Tournament must be in {expected} state (currently {current}) |
| tournament.cannot_add_players | Cannot add players in this state |
| tournament.cannot_remove_players | Cannot remove players in this state |
| tournament.use_drop_out | Use DropOut for players who have played |
| tournament.cannot_drop_out | Cannot drop out in this state |
| tournament.cannot_finish | Cannot finish from this state |
| tournament.cannot_alter_seating | Cannot alter seating in this state |

**Rounds / seating**
| code | English |
|---|---|
| tournament.no_round_in_progress | No rounds in progress |
| tournament.no_round_to_finish | No rounds to finish |
| tournament.no_round_to_cancel | No rounds to cancel |
| tournament.only_last_round_cancellable | Can only cancel the last round |
| tournament.tables_not_finished {tables} | Tables {tables} not finished yet (1-based now) |
| tournament.prelim_after_finals | Cannot start a preliminary round after finals |
| tournament.max_rounds_reached | Maximum rounds reached |
| tournament.not_enough_players | Need at least 4 checked-in players |
| tournament.invalid_table_size {size} | Invalid table size: {size} |
| tournament.player_not_in_subset {player} | Player not in selected subset |
| tournament.duplicate_player | Duplicate player in seating |
| tournament.seating_incomplete | Submitted seating does not include all selected players |
| tournament.invalid_round | Invalid round number |
| tournament.invalid_table | Invalid table number |
| tournament.invalid_seat | Invalid seat number |
| tournament.finals_one_table | Finals expects exactly one table |
| tournament.finals_player_count | Finals player count mismatch |
| tournament.finals_player_set | Finals player set mismatch |
| tournament.table_count_mismatch | Table count mismatch |
| tournament.player_count_mismatch | Player count mismatch |
| tournament.seating_violates_r1 | Seating violates R1 (predator-prey repeat) |
| tournament.player_not_in_round {player} | Player not found in current round seating |
| tournament.table_full | Table already has 5 players |
| tournament.table_not_empty | Cannot remove a table with players seated |

**Scoring / finals / toss**
| code | English |
|---|---|
| tournament.invalid_score | Invalid score: impossible VP combination for this table |
| tournament.finals_min_rounds | Need at least 2 rounds before finals |
| tournament.finals_already_started | Finals already started |
| tournament.finals_not_enough_players | Need at least 5 eligible players with results for finals |
| tournament.finals_unresolved_ties | Resolve all ties in top 5 before starting finals |
| tournament.no_finals_in_progress | No finals in progress |
| tournament.finals_table_unfinished | Finals table must be Finished first |
| tournament.toss_min_rounds | Need at least 2 rounds before setting toss |

**Decks / raffle / config**
| code | English |
|---|---|
| tournament.deck_locked_finished | Cannot modify deck after tournament is finished |
| tournament.deck_locked_playing | Cannot modify deck while tournament is in progress |
| tournament.deck_locked_round | Cannot modify a deck for a round that has already started |
| tournament.raffle_count_min | Raffle count must be at least 1 |
| tournament.raffle_no_players | No eligible players in pool |
| tournament.raffle_no_draws | No raffle draws to undo |
| tournament.raffle_none_played | No players have played yet |
| tournament.raffle_wrong_state | Raffle requires tournament in Waiting, Playing, or Finished state |
| tournament.name_required | Tournament name cannot be empty |
| tournament.max_rounds_below_completed {max, completed} | max_rounds ({max}) cannot be less than completed rounds ({completed}) |
| deck.no_cards | No cards found in deck list |
| seating.min_players | At least 4 players required |
| seating.min_rounds | At least 1 round required |

**internal** — everything else: JSON parse/serialize, `…required` event-field schema violations
(parsing.rs), unknown enum values (`Unknown role/pool/event type/standings mode`, `Invalid
payment status/format`), `Invalid card ID`, seating build failures, `Invalid tournament/player
state`, `CreateTournament is not a tournament event`. Code `internal`, params `{detail}`.
Frontend shows generic message + console-logs detail; backend 400 keeps detail for logs.

## Explicitly out of scope (follow-ups if wanted)

- `PermissionResult::deny(reason)` strings (permissions.rs) — separate data-shaped surface used
  for UI gating, not thrown errors.
- `deck.rs` `ValidationError { severity, message }` list (deck legality results) — data, not
  errors; localizing it = its own ticket.
- `check_table_vps` `Option<String>` Debug-format output (admin archon import only).

## Intentional English changes + engine-test touch-points

The merges/format changes below alter today's canonical English; engine tests asserting
`.contains(…)` on these exact strings get updated in the same pass:

- deck locks: delete-site wording "Cannot delete deck …" → "Cannot modify deck …" (3 merged
  codes; upload+delete share user meaning).
- `tables_not_finished`: was Rust debug 0-based `Tables [1, 3] not finished yet` → 1-based
  pre-joined `Tables 2, 4 not finished yet`.
- DQ/suspended/vekn-id register/check-in variants collapse to one message each.
- `Invalid payment status: {}` and other enum-drift messages → `internal` (Display becomes
  "Internal error: …" — substring asserts on the detail still pass).
- All other Display strings stay byte-identical to today.

## Sequencing

Single pass across the whole engine (avoids a mixed fleet of JSON and free-text throws), then
backend, then frontend mapping + en.json; es/fr/it/pt via i18n-translator. The #102
string-passthrough stays as the legacy fallback path. `seating.*` / `deck.no_cards` codes are
public (not internal) because the seating preview and deck import UIs call those engine
functions directly over WASM — they're user-facing on that path even though the HTTP action
route never carries them.

## Review

Cross-stack: Rust core + WASM + PyO3 + backend HTTP + frontend + i18n. Needs principal-engineer
sign-off on the error taxonomy and the backend error-body shape before implementation.
**2026-06-10: principal-engineer sign-off obtained — "approve with required changes"; the 7
blocking items are folded into this doc** (EngineError branch first in toUserMessage; raw-call
wrap in engine.ts; coded checkPlayerBarred pre-checks; apiRequest-only ApiError wiring; py_str
shared-helper note; deck-lock English change; test touch-points above).

## Implementation record (2026-06-10)

Landed on main (content inside commit 6dd3c46 due to a concurrent-session index sweep —
verified byte-identical to the intended 28-file change; see also seed fix 7a5d49b).
Gates: cargo 154 ✓, clippy -D warnings all features ✓, ruff ✓, backend pytest ✓,
svelte-check ✓, paraglide 5 locales ✓, docker e2e 26 ✓. senior-qa: zero new tests —
cross-language parity machine-verified (73 codes ↔ registry ↔ 5×73 keys, no drift);
optional follow-up if drift-at-build-time is wanted: a 5-line CI script diffing
engine/src/error.rs codes against en.json err_* keys (fallback-to-English is the
designed mitigation otherwise).
