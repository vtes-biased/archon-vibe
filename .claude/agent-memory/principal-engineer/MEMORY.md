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
- Authz decisions are single-sourced in Rust (`engine/src/permissions.rs`), exposed via PyO3 + WASM — see ARCHITECTURE.md (Authorization).

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
- Reassigning object refs (sanctions/decks/coopted_by on merge/detach) MUST return `BroadcastData` and broadcast, or other clients stay stale until snapshot resync — the established pattern; preserve it in any new merge-like flow.
- Svelte 5 `$props()`: props must be listed in the destructure, not just the type annotation.

## Sync-correctness traps
- [Destructive store-wipe offline rescue](destructive-store-wipe-offline-rescue.md) — db.ts upgrade AND sync.ts clearAllStores both wipe stores; must rescue the FULL offline set (tournament + sanctions + decks + player-stubs).
- objects has two timestamps (column modified_at vs JSONB modified); never mix in the since-cursor — see SYNC.md (Sync Cursor).
- tournament_transaction connection discipline (reads join txn; writes acquire pool independently; never a 2nd conn under lock) — see ARCHITECTURE.md (Database Access & Connection Model).
- [finals.seed_order is a UID field](finals-seed-order-uid-field.md) — holds player user_uids; easily missed in any per-player UID remap.
- [Error localization across throw surfaces](error-localization-offline-path-trap.md) — engine-error localization covers HTTP + offline WASM + JS pre-checks (wired); preserve all three when changing error presentation.
- [Resync branch zero-delay loop](sync-resync-branch-zero-delay-loop.md) — sync.ts resync onmessage branch reconnects with NO delay; cold-start trigger fixed, branch unguarded for any other persistent resync cause; route resync reconnects through backoff.
- [go-online self-echo + 409 gap](go-online-self-echo-409-gap.md) — FIXED: broadcast_precomputed exclude_device_id self-excludes the initiating device + goingOnlineUids guard (HTTP response is sole authority in-flight) + 409→clearOfflineState. Residual: bounded in-flight reconciliation window.

## Scoring & Standings
- compute_final_standings = shared VEKN placement (winner=1, finalists tie 2nd) — see ARCHITECTURE.md (engine modules / League System).
- [SA penalty single-sourced in Rust](sa-penalty-duplicated-in-python.md) — SA scoring lives only in `engine.compute_rating_vp_gw`; never re-derive in Python.
- [Standings are prelim-only](standings-prelim-only-contract.md) — `tournament.standings` = SA-adjusted prelim, finals excluded; the Python archon importer violates this (stores finals-inclusive) → league double-counts finals.
- [Rounds⇔standings coupling](rounds-standings-coupling-engine.md) — engine invariant: standings non-empty iff rounds non-empty; makes the VEKN `batch_push` `rounds>0` guard safe (excludes imports, keeps in-app tournaments).

## Authorization (cross-stack)
- Authz predicates single-sourced in engine/src/permissions.rs (PyO3+WASM); frontend fail-closed, UX-only — see ARCHITECTURE.md (Authorization).

## Error handling (cross-stack)
- [Error-codes contract](error-codes-contract.md) — `EngineError` enum = single error taxonomy; `{code,params,message}` wire JSON across WASM/PyO3/HTTP; domain rejection MUST be an explicit variant (From-impls silently demote to internal); EngineRejection-in-transaction is sound FastAPI.

## Migration / legacy-archon merge (residual hazards)
- [Archon-merge cross-sync flip-flop](archon-merge-cross-sync-flipflop.md) — daily `--merge` shares fields with both VEKN syncs; tournament meta + officials' contact_email oscillate daily unless single-writer enforced (member side is, tournament side isn't).
- [Vekn-less drop is NOT ref-free (measured)](migration-veknless-orphan-measured.md) — dropping the 142 vekn-less members orphans 9 refs (4 players + 5 seats) in 3 Finished tournaments; old archon never enforced vekn at registration. Reusable probe recipe in file.
- [vekn_id unique index spans tombstones](vekn-unique-index-spans-tombstones.md) — index has no deleted_at exclusion; soft-deleted user reserves its vekn_id; deleted_at-filtered lookups disagree → seed-insert can crash on a reserved number. UNFIXED, reachable on steady-state nightly merges (admin user-delete keeps vekn_id).
- The vekn-id-matching redesign (member matching, no tombstone, vekn-less shells, `member_uid_map` remap of all member-uid refs) shipped; full impl + ref surface in `.pst/details/169-vekn-id-matching-merge.md`.
