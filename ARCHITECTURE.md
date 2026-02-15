# Architecture

## Overview

This project is an offline-first Progressive Web App (PWA) with a client-server architecture designed to work seamlessly whether online or offline. The system uses a shared Rust core for business logic across both frontend and backend.

## Technology Stack

### Frontend
- **Framework**: Svelte
- **Build Tool**: Vite
- **Local Storage**: IndexedDB
- **PWA**: Service workers for offline capabilities
- **Language**: TypeScript

### Backend
- **Framework**: FastAPI (Python)
- **Database**: PostgreSQL (latest)
- **Database Access**: psycopg3 (async mode, no ORM)
- **Serialization**: msgspec (high-performance JSON)
- **Language**: Python 3.11+
- **Tooling**: uv (package installer), ruff (linter/formatter), ty (type checker)

### Shared Core
- **Language**: Rust
- **Purpose**: Business logic and event handling
- **Compiled to**: WebAssembly (frontend) and native library (backend via PyO3)

## Data Model

### Object Structure

All objects in the system share a common structure (via `BaseObject`):

- **`uid`**: UUID v7 (time-ordered, indexed)
- **`modified`**: Timestamp (indexed)
- **`deleted_at`**: Soft-delete timestamp (nullable)

All other fields are model specific.

### Database Schema

Objects are stored in PostgreSQL with a minimal schema:

```sql
CREATE TABLE objects (
    uid UUID PRIMARY KEY,
    modified TIMESTAMP NOT NULL,
    data JSONB NOT NULL
);

CREATE INDEX idx_modified ON objects(modified);
```

The entire object is serialized as JSONB in the `data` column. This approach prioritizes:

- **Simplicity**: Single table, no migrations for schema changes
- **Performance**: msgspec for fast serialization, JSONB for PostgreSQL optimization
- **Flexibility**: Schema-less design for rapid iteration

## Event System

The system uses two types of events:

### 1. Business Events
- **Purpose**: Represent domain actions (e.g., "Member.New", "Tournament.RoundStart")
- **Processing**: Handled by shared Rust engine
- **Effect**: Transform objects according to business rules
- **Flow**: User action → Business event → Rust engine → Object mutation
- **Routing**: **ALL business events go through `POST /{uid}/action`**. There must be no separate REST endpoints for individual event types. The backend's only role is to deserialize the event JSON and pass it to the Rust engine. This ensures identical processing online (server) and offline (WASM), and keeps the engine as the single source of truth for all state transitions.

See [TOURNAMENTS.md](TOURNAMENTS.md) for a complete example of business event processing.

### 2. CRUD Events
- **Purpose**: Synchronize database state between client and server
- **Types**: Create, Update, Delete
- **Payload**: Contains full object data, including `uid` and `modified` fields
- **Flow**: Database change → CRUD event → SSE/reconciliation → IndexedDB sync

## Online Mode

```
┌───────────┐         SSE        ┌────────────┐
│  Svelte   │◄───────────────────│  FastAPI   │              ┌───────────────┐
│    PWA    │                    │  Backend   │ Rust Engine  │ Object/Event  │
│           │  Business Events   │            │─────────────►│    Logic      │
│           ├───────────────────►│            │              └───────────────┘
└─────┬─────┘                    └──────┬─────┘               
      │                                 │
      │                                 │
 ┌────▼─────┐                      ┌───▼─────┐
 │ IndexedDB│                      │ Postgres│
 │ (Local)  │                      │   DB    │
 └──────────┘                      └─────────┘
```

### Workflow
1. User performs action in PWA
2. PWA sends business event to backend
3. Backend's Rust engine processes event and updates PostgreSQL
4. Backend generates CRUD event
5. Backend broadcasts CRUD event via SSE
6. PWA receives CRUD event and updates IndexedDB
7. Svelte UI reactively updates

## Offline Mode

### Going Offline
When the PWA is deliberately taken offline (or loses connection):

1. PWA detects offline state
2. Switches to "offline mode" - takes charge of its data
3. Business events are processed locally by Rust engine (compiled to WASM)
4. Objects in IndexedDB are updated directly
5. All CRUD operations are tracked in a local change log

### Reconciliation on Reconnect

```
┌─────────────┐                      ┌──────────────┐
│   Svelte    │  1. Send change log  │   FastAPI    │
│     PWA     ├─────────────────────►│   Backend    │
│             │                      │              │
│             │  2. Receive fixes    │              │
│             │◄─────────────────────┤              │
│             │                      │              │
│             │  3. Resume SSE       │              │
│             │◄─────────────────────┤              │
└─────────────┘                      └──────────────┘
```

#### Reconciliation Steps
1. **Upload**: PWA sends accumulated CRUD events to server
2. **Conflict Detection**: Server compares against its current state
3. **Resolution**: Server applies changes or detects conflicts
4. **Adjustment**: Server returns correction CRUD events if needed
5. **Sync**: PWA applies adjustments to IndexedDB
6. **Resume**: SSE connection is re-established

### Conflict Resolution Strategy
- Server is the source of truth for conflicts
- Timestamp-based "last write wins" for simple cases
- Custom resolution logic in Rust engine for complex business rules
- Client always accepts server's reconciliation response

## Card/Deck System

**Card Database**: VTES card data loaded from JSON into IndexedDB (`cards` store, keyed by card ID). Rust engine provides card lookup and deck validation.

**Deck Structure**: `Deck { round, name, author, comments, cards: Record<string, number> }`. Embedded in `Tournament.decks` (keyed by player UID). Filtered by `decklists_mode` (Winner/Finalists/All) at member data level.

**Validation**: Rust engine validates deck legality (crypt/library counts, banned cards, multideck rules) before tournament actions that require decks.

## League System

**League Model**: Aggregates tournaments into leagues with standings. Fields: `name`, `kind` (League/Meta-League), `standings_mode` (RTP/Score/GP), `format`, `online`, `country`, `start`/`finish`, `description`, `organizers_uids`, `parent_uid`, `allow_no_finals`.

**Synced Object**: Leagues are streamed via SSE like tournaments/users. Stored in IndexedDB `leagues` store with `by-country` and `by-start` indexes.

**Standings Modes**: RTP (rating points), Score (GW/VP/TP), GP (Grand Prix position-based).

## Serialization

### msgspec
Used throughout the system for high-performance JSON serialization:

**Python (Backend)**:
```python
import msgspec

class MyObject(msgspec.Struct):
    uid: str
    modified: datetime
    name: str
```

**TypeScript (Frontend)**:
```typescript
interface MyObject {
    uid: string;
    modified: string;
    name: string;
}
```

### Rust Integration
The Rust core defines the canonical object schemas and business logic:
- Compiled to native library for Python (via PyO3)
- Compiled to WebAssembly for TypeScript (via wasm-bindgen)
- Ensures business logic consistency across client and server

**Engine Location**: `engine/src/`

**Key Modules**:
- `lib.rs` - Entry point, WASM/PyO3 bindings
- `permissions.rs` - Role-based access control
- `seating.rs` - Tournament seating algorithm
- `tournament.rs` - Tournament event processing

**Build Commands**:
```bash
# Build for backend (Python)
just build-engine-python   # Uses maturin

# Build for frontend (WASM)
just build-engine-wasm     # Uses wasm-pack

# Build both
just build-engine
```

**Frontend Usage** (`frontend/src/lib/engine.ts`):
```typescript
import { initEngine, processTournamentEvent, computeSeating } from '$lib/engine';

// Initialize on app load
await initEngine();

// Process tournament event (offline mode)
const updated = await processTournamentEvent(tournament, event, actor);

// Permission checks (sync, use pre-initialized engine)
const result = canChangeRole(actor, target, 'Prince');
```

**Backend Usage**:
```python
from archon_engine import PyEngine

engine = PyEngine()
result = engine.process_tournament_event(tournament_json, event_json, actor_json)
```

### Development Workflow

**Backend:**
```bash
# Install dependencies
uv sync --dev

# Format code
uv tool run ruff format backend/

# Lint code
uv tool run ruff check backend/

# Type check
uv tool run ty check backend/src/

# Run server
uv run uvicorn src.main:app --app-dir backend --reload
```

**Frontend:**
```bash
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev

# Build for production
npm run build
```

## Benefits

### Performance
- **msgspec**: Faster than standard JSON libraries
- **JSONB**: Native PostgreSQL JSON operations
- **IndexedDB**: Fast local queries
- **Rust**: High-performance business logic

### Offline-First
- Full functionality without network
- Automatic synchronization when online
- Transparent mode switching

### Developer Experience
- Single source of truth for business logic (Rust)
- Simple data model (JSONB, no migrations)
- Type safety across stack (Rust → Python/TypeScript)
- Modern, fast tooling (uv, ruff, ty)

### Scalability
- Stateless backend (FastAPI)
- Efficient SSE for real-time updates
- Client-side computation reduces server load

## API Design Patterns

### Request Body Parsing

Use **Pydantic BaseModel** for request bodies in FastAPI, not msgspec.Struct with raw bytes:

```python
# ✅ Correct - Pydantic handles parsing automatically
class CreateRequest(BaseModel):
    name: str
    expires_at: str | None = None

@router.post("/")
async def create(request: CreateRequest):
    ...

# ❌ Wrong - body: bytes doesn't read request body
@router.post("/")
async def create(body: bytes = b""):
    data = msgspec.json.decode(body)  # body is empty!
```

### Date/Time Handling

**KISS principle**: For date-only fields (expiry dates, event dates), accept simple `YYYY-MM-DD` strings and store as UTC midnight.

```python
# Backend: Accept date-only, store as UTC datetime
from datetime import date, datetime, UTC

if request.expires_at:
    d = date.fromisoformat(request.expires_at)  # "2026-06-15"
    expires_at = datetime(d.year, d.month, d.day, tzinfo=UTC)
```

```svelte
<!-- Frontend: HTML date input sends YYYY-MM-DD -->
<input type="date" bind:value={expiresAt} />
```

Don't over-engineer timezone handling for date-only fields. Full datetime with timezone is only needed for precise timestamps (e.g., `issued_at`, `modified`).

### Response Serialization

Use msgspec for response serialization (faster than Pydantic):

```python
encoder = msgspec.json.Encoder()

return Response(
    content=encoder.encode(obj),
    media_type="application/json",
)
```

### Soft Delete Pattern

For objects that need sync support after deletion:

1. Add `deleted_at: datetime | None` field (part of `BaseObject`)
2. Soft delete: set `deleted_at = now()`
3. SSE broadcasts the deleted object (with `deleted_at` set)
4. Frontend receives update, removes from local IndexedDB
5. Backend cleanup job hard-deletes after 30 days

This ensures clients that were offline during deletion still receive the delete event on reconnect.

## Internationalization (i18n)

**Library**: Paraglide JS (inlang) — client-only, no server-side rendering needed for SPA.

**Locales**: `en` (default), `fr`, `es`, `pt`, `it` — all message files in `frontend/messages/*.json`.

**Detection**: Browser locale auto-detection via `preferredLanguage` strategy + cookie persistence.

**Integration**: Vite plugin compiles messages to TypeScript. Import from `$lib/paraglide/messages` in components.

**Locale Switcher**: Desktop sidebar component (`LocaleSwitcher.svelte`) allows manual locale selection.
