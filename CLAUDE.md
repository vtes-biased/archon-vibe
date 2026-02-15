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

**DB Storage**: Single JSONB column in PostgreSQL. Full object serialized with msgspec.
```sql
CREATE TABLE objects (uid UUID PRIMARY KEY, modified TIMESTAMP, data JSONB);
```

**Card/Deck Support**: VTES card database loaded into IndexedDB (`cards` store). Deck validation in Rust engine, integrated into tournament player workflow.

**Object Types**: User, Sanction, Tournament, Rating, League (all synced via SSE). VtesCard (static data, loaded into IndexedDB).

## Events

### Business Events
- Domain actions (e.g., `Member.New`, `Tournament.RoundStart`)
- Processed by Rust engine (shared client/server)
- Transform objects per business rules

### CRUD Events
- Sync database state (Create/Update/Delete)
- Payload: full object with `uid` + `modified`
- Used for SSE streaming and reconciliation

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

Three SSE data levels applied to ALL object types (see SYNC.md for details):

- **public**: no token or no vekn_id. Only Prince/NC users, minimal tournaments, no sanctions
- **member**: has vekn_id. All users (no contact info), sanctions, tournaments with standings/my_tables/filtered decks
- **full**: IC, NC/Prince (same country), or organizer. Everything

## Mutation Pipeline

Tournament actions use optimistic updates via WASM engine:
1. WASM processes locally → IndexedDB updated → UI reacts immediately
2. Server request sent async → SSE delivers authoritative state → overwrites if different

Resync triggered when roles or vekn_id change (`resync_after` on User).

## Key Constraints
- Server always wins conflicts
- Each PWA maintains full dataset in IndexedDB
- SSE for real-time sync when online
- Rust ensures consistent business logic across stack
