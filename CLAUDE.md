# Agent Workflow (PROACTIVE — do not wait for user to ask)

When implementing features or making significant changes, follow this pipeline using the Task tool:

1. **Before implementing**: Consult `product-manager` for VEKN rules, feature specs, UX requirements, or prioritization decisions. Always consult when domain context is needed.
2. **Before/during frontend work**: Consult `staff-frontend-engineer` for UX/UI review, component design, dependency evaluation, or mobile-first guidance.
3. **After significant code changes**: Launch `principal-engineer` to review architectural alignment — especially for changes touching sync, data model, Rust/WASM pipeline, or cross-module refactors.
4. **After any UI text change**: Launch `i18n-translator` to update all 5 locale files. Any new or modified user-facing string triggers this.
5. **After meaningful code changes**: Launch `documentalist` to update CLAUDE.md, ARCHITECTURE.md, SYNC.md, or other docs that are now stale.
6. **After major features or significant changes**: Launch `senior-qa` to run the test suite and assess whether new tests are warranted. Trigger for: new features touching core logic (tournament lifecycle, pairings, scoring), cross-stack changes (Rust/backend/frontend), refactors of critical paths (sync, reconciliation, access control). Skip for UI-only tweaks, copy changes, or styling.

Steps 3-6 should run in parallel when applicable. Skip agents only for trivial changes (typo fixes, single-line tweaks with no architectural or UI text impact).

# Project Guidelines

- Keep answers short and token efficient
- Prefer compact code and minimal changes
- Check assumptions in project code or web docs
- Use codanna MCP tools for codebase search and project documentation
- Use context7 MCP tools for external library/framework documentation (see CONTEXT7.md for library IDs)
- Challenge instructions when needed
- Follow frontend/DESIGN.md for UI styling guidelines
- **Component splitting**: When a Svelte page file exceeds ~1000 lines, extract logical sections into child components (e.g., `PlayerList.svelte`, `StandingsTable.svelte`). Pass data via props; keep state ownership in the parent. This keeps files navigable and editable by both humans and AI agents.
- **Offline-first reads**: All UI reads come from IndexedDB. The backend API is only for mutations (actions). SSE pushes data changes to IndexedDB per-user with role-appropriate data. No API GET calls for data display.

# Architecture

Core architecture reference for offline-first PWA. See ARCHITECTURE.md for details.

**Sync implementation**: See SYNC.md for streaming patterns, IndexedDB optimization, and how to add new object types.

## Stack
- **Frontend**: Svelte + Vite + TypeScript, PWA (service workers), IndexedDB local storage
- **Backend**: Python FastAPI, PostgreSQL (JSONB), msgspec serialization
- **Shared**: Rust core (business logic) → WASM (frontend) + PyO3 (backend)

## Data Model
All objects have (via `BaseObject`):
- `uid`: UUID v7 (indexed, time-ordered)
- `modified`: timestamp (indexed)
- `deleted_at`: soft-delete timestamp (nullable)
- Model-specific fields

**DB Storage**: Unified `objects` table with pre-computed access-level columns:
```sql
CREATE TABLE objects (
    uid TEXT PRIMARY KEY, type TEXT NOT NULL,
    modified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    "public" JSONB, "member" JSONB, "full" JSONB NOT NULL
);
```
Access projections computed by `access_levels.py` at write time. No per-viewer filtering at read time.

**Card/Deck Support**: VTES card database loaded into IndexedDB (`cards` store). Deck validation in Rust engine, integrated into tournament player workflow.

**Object Types**: User, Sanction, Tournament, DeckObject, League (all synced via SSE). VtesCard (static data, loaded into IndexedDB).

**DeckObject fields**: `tournament_uid`, `user_uid`, `round`, `name`, `author`, `comments`, `cards` (dict card_id→count), `attribution`, `public` (bool — engine-managed, drives member-level visibility).
- No deck REST endpoints. All mutations go through `POST /{uid}/action` (engine `deck_ops` side-effects).
- `deck_ops` ops: `upsert` (create/update deck), `delete` (remove deck), `set_public` (flip public flag on existing deck by uid).
- Engine `process_tournament_event` signature: `(tournament_json, event_json, actor_json, sanctions_json, decks_json) → {"tournament": {...}, "deck_ops": [...]}`

**Tournament extra fields**: `external_ids` (dict, e.g. `{"vekn": "<event_id>"}`), `vekn_pushed_at` (datetime|None — set when results uploaded to VEKN).

**Timer fields** (on Tournament, online-only):
- `timer`: `TimerState` — `{started_at, elapsed_before_pause, paused}`. Clients compute countdown locally.
- `table_extra_time`: `dict[str, int]` — table index → extra seconds granted
- `table_paused_at`: `dict[str, str]` — table index → ISO datetime of clock-stop start

**TournamentConfig timer fields**: `round_time` (int, seconds), `finals_time` (int, seconds, 0 = use round_time), `time_extension_policy` (`additions` | `clock_stop` | `both`).

## Events

### Business Events
- Domain actions (e.g., `Member.New`, `Tournament.RoundStart`)
- Processed by Rust engine (shared client/server)
- Transform objects per business rules

### CRUD Events
- Sync database state (Create/Update/Delete)
- Payload: full object with `uid` + `modified`
- Used for SSE streaming and reconciliation

### Ephemeral SSE Events
- Not stored in DB; no IndexedDB update
- `judge_call`: broadcast to organizers + IC only; payload `{tournament_uid, table, table_label, player_name}`

## Modes

### Online
1. User action → business event → backend
2. Backend Rust engine processes → updates PostgreSQL
3. Backend generates CRUD event → broadcasts via SSE
4. Frontend receives CRUD → updates IndexedDB → UI reacts

### Offline
1. PWA detects offline → switches to local mode
2. Business events processed by WASM Rust engine
3. IndexedDB updated directly, CRUD log tracked
4. On reconnect: send CRUD log → server reconciles → apply fixes → resume SSE

**Reconciliation**: Server is source of truth. Returns adjustment CRUD events if conflicts detected.

## Access Model (Data Levels)

Three pre-computed JSONB columns per object (see SYNC.md for field details):

- **public**: no token or no vekn_id. Only Prince/NC users, minimal tournaments, no sanctions, no decks
- **member**: has vekn_id. All users (no contact info), sanctions, most tournament fields, decks where `public=true` (own decks via personal overlay)
- **full**: base level for all viewers; personal overlay sends full data for own objects + role-based access (IC, NC/Prince same country, organizer)

Projections computed by `access_levels.py` at write time. SSE reads the matching column directly.

## Mutation Pipeline

Tournament actions use optimistic updates via WASM engine:
1. WASM processes locally → returns `{tournament, deck_ops}` → IndexedDB updated → UI reacts immediately
2. Server request sent async → SSE delivers authoritative state (tournament + deck objects) → overwrites if different

Resync triggered when roles or vekn_id change (`resync_after` on User).

## Key Constraints
- Server always wins conflicts
- Each PWA maintains full dataset in IndexedDB
- SSE for real-time sync when online
- Rust ensures consistent business logic across stack
