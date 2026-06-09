# Principal Engineer Agent Memory

## Project Structure
- Backend: `backend/src/` (FastAPI, Python 3.11+, msgspec, psycopg3 async)
- Frontend: `frontend/src/` (Svelte 5 runes, Vite, TypeScript, IndexedDB)
- Engine: `engine/src/` (Rust, WASM via wasm-pack, PyO3 via maturin)
- Build: `justfile` at project root

## Key Files
- `backend/src/main.py` — SSE endpoint, personal/organizer overlays, broadcast wiring
- `backend/src/broadcast.py` — `BroadcastData` + `broadcast_precomputed` (broadcast injection lives here, not main.py)
- `backend/src/access_levels.py` — write-time public/member/full projections
- `backend/src/models.py` — domain models (msgspec.Struct)
- `backend/src/db.py` — PostgreSQL ops, streaming, CRUD, account-surgery (merge/detach)
- `backend/src/permissions.py` — thin PyO3 wrapper over engine authz (decision lives in Rust)
- `backend/src/routes/auth/` — auth flows split into a package (email_password, discord, passkeys, magic_link, profile, _tokens)
- `backend/src/routes/tournaments.py` — tournament create/action/delete + go_online
- `frontend/src/lib/sync.ts` — SSE SyncManager singleton, spec-based buffering
- `frontend/src/lib/db.ts` — IndexedDB wrapper, batch ops, by-tournament indexes
- `frontend/src/lib/api.ts` — API client, optimistic updates + rollback for tournament actions
- `frontend/src/lib/engine.ts` — WASM engine wrapper
- `frontend/src/lib/stores/auth.svelte.ts` — auth state ($state runes)

## Conventions
- All objects: `uid` (UUID v7), `modified`, `deleted_at` (soft-delete) in one unified `objects` JSONB table.
- Access is **pre-computed at write time** into three columns (public/member/full); SSE reads the matching column. No per-viewer filtering at read time.
- Business mutations only via `POST /{uid}/action` → Rust engine → CRUD → SSE. No per-event REST routes.
- **SSE serves raw JSON via `SELECT col::text`** — never reintroduce a parse→Struct→reserialize cycle (that was the original perf sink; design intent is zero re-serialization on the stream path).
- Optimistic updates: WASM applies locally first, server confirms via SSE, frontend rolls back on rejection. Reads stay offline-first (IndexedDB only) — no API GET for display.
- Pydantic for request parsing, msgspec for response serialization.
- Authz decisions are single-sourced in Rust (`engine/src/permissions.rs`), exposed via PyO3 + WASM — see [Authz single source](project_authz_single_source_rust.md).

## Open items (verified residual, 2026-06)
- `engine.ts` `TournamentEventType` is missing `CheckOut` vs the Rust enum (optimistic update silently falls back to server-only for that event).
- `jwt_config.py` `JWT_SECRET` still falls back to a dev default string — should hard-fail in production.
- i18n: leftover hardcoded English in some pages (e.g. `leagues/[uid]/+page.svelte`). Rust engine error-code i18n is the one deferred i18n phase (errors still emit English strings).

## Deck Architecture Patterns
- All deck mutations go through `POST /{uid}/action` (engine `deck_ops` side-effects); `DeleteDeck` engine action → `tournamentAction()` on frontend.
- `BroadcastData.org_uids` is NOT auto-populated for DeckObjects (no `organizers_uids` field). `_process_deck_ops()` manually stamps `bd.org_uids` after save — the correct pattern. `broadcast_precomputed()` uses `org_uids` to decide full-level SSE access.
- Visibility: `public` column always NULL for decks; `member` non-NULL only when `deck.public == True`; `full` always present. Own decks + organizer's tournament decks sent at full via personal/organizer overlay. NC/Prince same-country get NO deck access.
- Dedup is consistent across stack: `saveDeck()` (db.ts) and `_process_deck_ops()` upsert both key on `(tournament_uid, user_uid, round)`.

## Recurring trap: manual object reconstruction
- Several call sites hand-rebuild a `Sanction(...)` / `User(...)` from fields (sanction cleanup in `main.py`, sanctions delete endpoint, merge/detach in `db.py`). When a model gains a field, grep ALL manual constructors — prefer `msgspec.structs.replace` over hand-listing fields (hand-listing silently drops new fields, e.g. `resync_after`).
- Reassigning object refs (sanctions/decks/coopted_by on merge/detach) MUST return `BroadcastData` and broadcast, or other clients stay stale until snapshot resync. This is the established pattern as of pst #78 — preserve it in any new merge-like flow.
- Svelte 5 `$props()`: props must be listed in the destructure, not just the type annotation.

## Sync-correctness traps
- [Destructive store-wipe offline rescue](destructive-store-wipe-offline-rescue.md) — db.ts upgrade AND sync.ts clearAllStores both wipe stores; must rescue the FULL offline set (tournament + sanctions + decks + player-stubs).
- [Sync cursor timestamp trap](sync-cursor-timestamp-trap.md) — objects table has TWO modified timestamps (column `modified_at` vs JSONB `modified`); diverge in value AND format; never mix in a since-cursor.
- [tournament_transaction nested pool](tournament-transaction-nested-pool.md) — reads join the txn (ambient `_tx_conn`), writes acquire the pool independently; the asymmetry is load-bearing (go_online VEKN-id collision).
- [finals.seed_order is a UID field](finals-seed-order-uid-field.md) — holds player user_uids; easily missed in any per-player UID remap.
- [User delete SSE](user-delete-sse-noop.md) — soft-deleted users are SAVED (not removed) so by-uid refs resolve; filtered only from listing queries.

## Scoring & Standings
- [Final standings helper](project_final_standings_helper.md) — `compute_final_standings` is the shared VEKN placement fn (winner=1, finalists tie 2nd).
- [SA penalty single-sourced in Rust](sa-penalty-duplicated-in-python.md) — SA scoring lives only in `engine.compute_rating_vp_gw`; never re-derive in Python.
- [Standings are prelim-only](standings-prelim-only-contract.md) — `tournament.standings` = SA-adjusted prelim, finals excluded; the Python archon importer violates this (stores finals-inclusive) → league double-counts finals.

## Authorization (cross-stack)
- [Authz single source = Rust](project_authz_single_source_rust.md) — predicates live in `engine/src/permissions.rs` (PyO3 + WASM), the agreed cross-stack-DRY exception.
