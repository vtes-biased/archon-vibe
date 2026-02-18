# Principal Engineer Agent Memory

## Architecture Patterns

### Mutation Pipeline
- `tournamentAction()` in `frontend/src/lib/api.ts` handles the full optimistic update flow:
  WASM processes locally -> IndexedDB updated -> UI reacts -> server POST queued (serialized per tournament via `enqueueServerAction`) -> SSE delivers authoritative state
- `doAction()` in `+page.svelte` is the UI-level wrapper that calls `tournamentAction()` and manages loading state
- All `TournamentEvent` variants are defined in `engine/src/tournament.rs` and parsed from JSON via `from_json()`
- WASM binding: `TournamentEngine.computePlayerIssues()` -> `shared::compute_player_issues_json()` -> `seating::compute_player_issues()`
- PyO3 binding mirrors WASM exactly: same `compute_player_issues()` method on `TournamentEngine` struct

### Seating System (`engine/src/seating.rs`)
- `Measure` is a 3D matrix (N x N x 8) storing opponent relationships and position data
- `LexScore` is a 9-rule lexicographic scoring system for seating quality (R1-R9)
- `compute_player_issues()` returns per-player rule violations for UI display
- Precomputed optimal seatings exist for 4-25 players (except 6, 7, 11 which use staggered rounds)
- SA optimization: `optimize_sa_multi()` with restarts, index-based for performance

### Known Code Issues
- `Measure::set()` method (line 120) is a getter disguised as setter -- returns `i32` but doesn't mutate. Dead code currently (never called). Should be renamed or removed to avoid confusion.

### Component Patterns
- Drag-and-drop uses `@dragdroptouch/drag-drop-touch` polyfill for mobile touch support
- `SeatingSortable.svelte` is a shared component used by both `RoundsTab` and `FinalsTab`
- "Alter mode" pattern: enter edit mode -> local state (`alterTables`) -> save sends batch event -> cancel resets

### Backend Event Routing
- Backend routes don't have event-specific handlers -- all tournament events go through the Rust engine via PyO3
- No backend-specific Python code for `AlterSeating` or any individual event type
