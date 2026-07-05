# Engine dead-code sweep — full list

From the 2026-07-04 codebase audit. All items verified zero-callers by grep across
engine/, frontend/, backend/, bot/ (bindings included). Adjust or remove tests that
exercised deleted paths; expect a net deletion of ~600+ lines.

## The abandoned "compute-all-rounds-upfront" seating surface

Production always enters via `compute_next_round` with `rounds_count = prev+1`, so the
`!has_previous && rounds_count == 3` branch (seating/mod.rs:101) never fires outside tests.

- WASM binding `computeSeating` — lib.rs:511
- PyO3 binding `compute_seating` — lib.rs:725
- `shared::compute_seating_json` — lib.rs:167-216
- `precomputed.rs` — entire file (311 lines), incl. `get_precomputed_seating`
- Multi-round body of `get_staggered_rounds` — stagger.rs:9 (keep the single-round path used by production)

## enrich_deck, end to end

No caller of WASM `enrichDeck` or PyO3 `enrich_deck` anywhere (frontend does its own
deck display from IndexedDB card data).

- Both bindings in lib.rs (WASM ~:286 area + PyO3 twin)
- `shared::enrich_deck_json`
- `deck::enrich_deck` — deck.rs:564-626

## Smaller items

- `TableState` enum + `from_str`/`as_str` + re-export — types.rs:78, mod.rs:24. All table-state
  logic compares string literals; zero uses.
- `OnlyLastRoundCancellable` error variant — error.rs:55 (never constructed since CancelRound
  gained soft-cancel of non-last rounds, mod.rs:1019-1031). Delete with its `code()`/`Display`
  arms **plus** the live tail: frontend mapping `error-codes.ts:76` and the
  `err_tournament_only_last_round_cancellable` string in all 5 `frontend/messages/*.json`.
- `TournamentEvent::CreateTournament` tombstone — parsing.rs:279 parse arm + the
  unconditional-reject arm at mod.rs:2402; the unknown-event fallback (parsing.rs:286)
  yields an equally clear internal error.
- `Deck.attribution` field — deck.rs:17 + the `to_json` branch at deck.rs:62. No engine path
  ever sets it; attribution lives on the backend `DeckObject`.
- 3-player TP base arm — scoring.rs:143 (`3 => &[60.0, 36.0, 12.0]`): engine-impossible table
  size (`check_table_vps` + seating enforce 4–5 seats). Drop the arm; KEEP the
  `_ => vec![0.0; ...]` fallback but comment it as malformed-import defense.

## Deliberately excluded

- `measure_round_with_hints` (measure.rs:124) — reexamined in ticket 396 (wire or delete,
  decided on inspection, not swept blind).
