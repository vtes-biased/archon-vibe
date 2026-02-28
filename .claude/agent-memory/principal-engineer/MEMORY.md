# Principal Engineer Agent Memory

## Project Structure
- Backend: `/backend/src/` (FastAPI, Python 3.11+, msgspec, psycopg3 async)
- Frontend: `/frontend/src/` (Svelte 5 runes, Vite, TypeScript, IndexedDB)
- Engine: `/engine/src/` (Rust, WASM via wasm-pack, PyO3 via maturin)
- Build: `justfile` at project root

## Key Files
- `backend/src/main.py` - SSE endpoint, data-level filtering functions, broadcast injection
- `backend/src/models.py` - All domain models (msgspec.Struct)
- `backend/src/db.py` - PostgreSQL operations, streaming, CRUD (~1400 lines)
- `backend/src/routes/auth.py` - Auth flows (email, Discord, WebAuthn, magic link) (~1450 lines)
- `backend/src/routes/tournaments.py` - Tournament CRUD + action endpoint (~1150 lines)
- `frontend/src/lib/sync.ts` - SSE SyncManager singleton, spec-based buffering
- `frontend/src/lib/db.ts` - IndexedDB v14, batch operations, sanctions by-tournament index
- `frontend/src/lib/api.ts` - API client with optimistic updates for tournament actions
- `frontend/src/lib/engine.ts` - WASM engine wrapper
- `frontend/src/lib/stores/auth.svelte.ts` - Auth state (Svelte 5 $state runes)

## Known Architectural Issues (2026-02)
- See `architecture-review.md` for full details
- `sync.ts:disconnect()` calls async `flushAllBuffers()` without await - data loss risk
- `api.ts` has GET calls (fetchUser, fetchTournament) violating offline-first
- `sanctions.py` GET `/sanctions/user/{user_uid}` has no auth — publicly exposes sanctions
- Deck management (upload/update/delete) is in Python, not Rust engine - breaks offline capability
- Tournament uses hard-delete, not soft-delete pattern like other objects
- `engine.ts` TournamentEventType is missing events vs Rust enum
- WASM/PyO3 bindings duplicated (~300 lines each) in `engine/src/lib.rs`
- In-memory auth stores in `auth.py` won't survive restarts
- Test coverage is minimal (4 backend tests, 5 Rust tests)
- `ratings.py:recompute_all_ratings()` N+1 queries: loads all tournaments into memory, per-user DB calls in loop
- `ratings.py:recompute_ratings_for_players()` falls back to `existing.wins` which preserves stale wins
- `db.py:get_all_finished_tournaments()` loads full Tournament objects (rounds/decks/players) into memory
- `tournaments.py` imports `_rating_category_for_tournament` (private name, cross-module use)

## SSE Streaming Performance (2026-02, resolved)
- Original analysis in `sse-performance.md` (now partially obsolete)
- **FIXED**: Double serialization — `stream_objects_new()` returns raw JSON via `SELECT col::text`, no parse/reserialize
- **FIXED**: `_filter_tournament()` Struct-per-item — function removed entirely
- **FIXED**: Pool `max_size=20` (was 10)
- **FIXED**: SSE connection duplication — +layout.svelte owns connect/disconnect, components only listen
- Snapshot path loads directly into IDB (no buffering); SSE catch-up buffer is small
- Batch saves use single IDB transactions (data already in memory, chunking adds overhead for no benefit)

## Conventions
- All objects: uid (UUID v7), modified timestamp, deleted_at (soft-delete)
- Single JSONB column storage in PostgreSQL
- Business events through POST /{uid}/action only
- SSE data levels: public, member, full (filtered per-viewer)
- Broadcast injection: main.py sets module-level vars on route modules
- Pydantic for request parsing, msgspec for response serialization
- Frontend reads from IndexedDB only, mutations via API

## i18n Architecture Decision (2026-02)
- See `i18n-plan.md` for full details
- Library: Paraglide JS (compile-time, tree-shakeable, typed message functions)
- 5 languages: en (British), fr, pt (Brazilian), es, it
- Translations bundled in JS build output (NOT in IndexedDB, NOT fetched at runtime)
- Locale preference stored in localStorage (not cookies, not URL routing)
- Flat key naming: `namespace_key` (e.g., `nav_tournaments`, `login_sign_in`)
- Rust engine errors need migration to structured error codes for i18n
- Translator agent: `.claude/agents/i18n-translator.md` handles translation updates
- VTES game terms: card/clan/discipline names stay English; game mechanics terms translated per official rulebook

## Deck Architecture Patterns

### SSE Broadcast for Decks
- `BroadcastData.org_uids` is NOT auto-populated for DeckObjects by `save_object()` (decks don't have `organizers_uids` field)
- `_process_deck_ops()` manually stamps `bd.org_uids` after save — this is the correct pattern
- `broadcast_precomputed()` uses `org_uids` on BroadcastData to decide full-level access for SSE viewers

### SSE Personal Overlay for Organizers
- On initial connect, overlay queries `objects` table for tournaments where viewer is in `organizers_uids` (JSONB `?` operator)
- Then fetches ALL decks for those tournaments (`tournament_uid IN (...)`)

### Deck Visibility Model
- `public` column: always NULL for decks (never visible to non-members)
- `member` column: non-NULL only when `deck.public == True` (engine sets this)
- `full` column: always present
- Personal overlay: own decks always sent at full level
- Organizer overlay: all decks for organized tournaments sent at full level
- NC/Prince same-country: NOT given deck access (only user/tournament overlays)

### Deck Delete Flow
- All deck mutations go through `POST /{uid}/action` (engine `deck_ops` side-effects)
- `DeleteDeck` engine action → `tournamentAction()` on frontend
- `_process_deck_ops()` delete: filters by `deck_index` when multideck, deletes all player decks otherwise

### Data Dedup
- `saveDeck()` in db.ts deduplicates on `(tournament_uid, user_uid, round)`
- `_process_deck_ops()` upsert also matches on `(tournament, player, round)` — consistent

## Recurring Bug Pattern: Sanction reconstruction
- `main.py:run_sanction_cleanup()` reconstructs Sanction manually — must include ALL fields
- Same pattern in `sanctions.py` delete endpoint — also manual reconstruction
- When new fields are added to Sanction model, search ALL manual Sanction() constructors
- Svelte 5 `$props()` destructuring: props must be listed in the destructure, not just the type annotation
