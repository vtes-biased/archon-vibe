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

All synced objects share a single table with pre-computed access-level columns:

```sql
CREATE TABLE objects (
    uid TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    modified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,
    "public" JSONB,   -- NULL if not visible at this level
    "member" JSONB,   -- NULL if not visible at this level
    "full" JSONB NOT NULL
);

CREATE INDEX idx_objects_type_modified ON objects(type, modified_at, uid);
```

Access-level projections (`public`/`member`/`full`) are computed by `access_levels.py` at **write time** and stored as separate JSONB columns. SSE streaming reads the appropriate column directly — no per-request filtering. This approach prioritizes:

- **Simplicity**: Single table, no migrations for schema changes
- **Performance**: Pre-computed projections, zero per-viewer filtering at read time
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

### 3. Ephemeral SSE Events
- **Purpose**: Real-time notifications not requiring persistent storage
- **NOT stored in DB; NOT written to IndexedDB**
- **`judge_call`**: Player requests judge assistance. Broadcast to organizers and IC users only.
  - Payload: `{ tournament_uid, table, table_label, player_name }`
  - Auto-dismissed client-side after 120s; plays audio chime on receipt
  - Available online-only (`offline_mode` and non-playing tournaments rejected)

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

## Mutation Pipeline

Tournament actions use optimistic updates via WASM:
1. WASM processes locally → returns `{tournament, deck_ops}` → IndexedDB updated → UI reacts immediately
2. Server POST sent async → SSE delivers authoritative state → overwrites if different

### StartRound Seating Forwarding

`StartRound` accepts optional `seating: Vec<Vec<String>>` (table → ordered player UIDs). When provided, the engine validates it and uses it directly instead of computing random seating.

**Problem solved**: WASM (`rand::thread_rng`) and PyO3 use separate RNG states, so an unconstrained `StartRound` produces different seatings on client and server — breaking the optimistic update.

**Solution** (`tournamentAction()` in `api.ts`): after WASM processes `StartRound`, extract the computed seating from the result and inject it into the server POST:

```typescript
if (action === 'StartRound' && newRoundAdded) {
  const newRound = result.tournament.rounds[result.tournament.rounds.length - 1]!;
  serverEvent = { ...event, seating: newRound.map(t => t.seating.map(s => s.player_uid)) };
}
```

**Validation** (engine, `tournament.rs`):
- Each table must have 4–5 players
- All checked-in players must appear exactly once
- No duplicate player UIDs across tables

The frontend is the seating source; the server validates and stores it deterministically.

## Card/Deck System

**Card Database**: VTES card data loaded from JSON into IndexedDB (`cards` store, keyed by card ID). Rust engine provides card lookup and deck validation.

**DeckObject**: Standalone synced object (not embedded in Tournament). Fields: `tournament_uid`, `user_uid`, `round`, `name`, `author`, `comments`, `cards` (dict card_id→count), `attribution`, `public` (bool).
- `public` flag set by engine based on `decklists_mode` + tournament state (Winner/Finalists/All).
- No REST endpoints for decks. All mutations via `POST /{uid}/action` → engine `deck_ops` side-effects.
- `deck_ops` ops: `upsert` (create/update), `delete`, `set_public` (flip existing deck by uid).
- Client-side deck URL fetching; backend provides CORS proxy fallback.
- **SSE reactivity**: tournament `+page.svelte` listens for `type === "deck"` sync events → re-queries `getDecksByTournamentGrouped()` → updates `decksByUser` state → passed as prop to `PlayersTab` / `PlayerView` / `DecksTab`. Decks are not bundled into the tournament SSE event.

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
- `seating.rs` - Tournament seating algorithm (simulated annealing + staggered seatings)
- `tournament.rs` - Tournament event processing (state machine, scoring, finals)
- `deck.rs` - Deck parsing, validation, enrichment, TWDA export
- `ratings.rs` - Rating points computation
- `league.rs` - League standings computation (RTP/Score/GP)
- `cards.rs` - Card database (lookup by ID/name, normalization)

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
# Returns JSON string: {"tournament": {...}, "deck_ops": [...]}
result = engine.process_tournament_event(
    tournament_json, event_json, actor_json, sanctions_json, decks_json
)
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

## Shared Timer

Online-only feature. State stored on the `Tournament` object and synced via normal SSE (CRUD event on save). Clients compute the countdown locally — no per-second server broadcasts.

### Data Model

```python
class TimerState(msgspec.Struct):
    started_at: datetime | None = None        # UTC, when timer was started/resumed
    elapsed_before_pause: float = 0.0         # seconds accumulated before last pause
    paused: bool = True

class TimeExtensionPolicy(StrEnum):
    ADDITIONS  = "additions"   # +N min per table
    CLOCK_STOP = "clock_stop"  # per-table clock pause/resume
    BOTH       = "both"        # both mechanisms available
```

**Tournament fields** (timer state):
- `timer: TimerState` — global round timer
- `table_extra_time: dict[str, int]` — table_idx → extra seconds
- `table_paused_at: dict[str, str]` — table_idx → ISO datetime of clock-stop

**TournamentConfig fields**:
- `round_time: int` — round duration in seconds (0 = no timer)
- `finals_time: int` — finals override (0 = use round_time)
- `time_extension_policy: TimeExtensionPolicy`

### Sync Pattern

Server updates `tournament.timer` / `table_extra_time` / `table_paused_at` and broadcasts the full Tournament CRUD event via SSE. Clients receive the state update and recompute the countdown from `started_at` + `elapsed_before_pause` using a local `setInterval(1000)`. No streaming of individual tick values.

### Endpoints (organizer-only, online-only, tournament must be in Playing state)

| Method | Path | Effect |
|--------|------|--------|
| POST | `/{uid}/timer/start` | Resume/start global timer |
| POST | `/{uid}/timer/pause` | Pause global timer |
| POST | `/{uid}/timer/reset` | Reset timer + clear all table extensions |
| POST | `/{uid}/timer/add-time` | Add extra seconds to one table (max 600s total, policy must allow) |
| POST | `/{uid}/timer/clock-stop` | Pause a table's clock (clock-stop) |
| POST | `/{uid}/timer/clock-resume` | Resume table clock (converts pause duration → extra_time) |

All timer endpoints save-and-broadcast the updated tournament object.

### Frontend Components

- `TimerDisplay.svelte` — renders countdown, warning (<5 min), expired state; includes organizer controls for global and per-table actions
- `JudgeCallBanner.svelte` — receives `judge_call` SSE events; stacks dismissible alert banners with audio chime

## Call for Judge

Player-initiated request for judge assistance at their table. Online-only.

**Endpoint**: `POST /{uid}/call-judge` — `{ table: int }`

**Constraints**: Player must be authenticated and seated at the specified table in the current round. Tournament must be in Playing state and not in offline mode.

**Broadcast**: Ephemeral `judge_call` SSE event to organizers and IC users only (not stored, not IndexedDB-synced). See [Ephemeral SSE Events](#3-ephemeral-sse-events).

## VEKN Push Sync

Outbound integration: pushes tournament data and members TO vekn.net. Controlled by feature flags.

**Feature flags**:
- `VEKN_PUSH=true` — backend env, enables all push operations
- `VITE_VEKN_PUSH=true` — frontend env, restricts `max_rounds` UI to 2–4, shows VEKN link badge

**Two-phase push** (both are fire-and-forget — never block user actions):
- **Phase 1** (on create): `push_tournament_event()` — creates VEKN calendar entry, stores returned event ID in `tournament.external_ids["vekn"]`
- **Phase 2** (on finish): `push_tournament_results()` — uploads archondata; sets `tournament.vekn_pushed_at`

**Member push**: `push_member()` — called on sponsor action (`POST /vekn/sponsor`). Pushes locally-coopted members to VEKN registry.

**Batch push** (`batch_push()` in `vekn_push.py`): Hourly scheduled job catches missed real-time pushes. Queries DB for tournaments without `external_ids.vekn` or with `vekn_pushed_at IS NULL`.

**archondata format** (VEKN API for result upload):
```
{nrounds}¤{rank}§{first}§{last}§{city}§{vekn}§{gw}§{vp}§{vpf}§{tp}§{toss}§{rtp}§...
```
Generated by `generate_archondata()` in `vekn_push.py`. GW is prelim-only (finals GW removed for winner).

**Format → VEKN event type mapping** (`FORMAT_RANK_TO_VEKN_TYPE`):
| Format | Rank | VEKN type ID |
|--------|------|--------------|
| Standard | Basic | 2 |
| Standard | NC | 8 |
| Standard | CC | 6 |
| Limited | Basic | 3 |
| V5 | Basic | 16 |

**Constraints**:
- `max_rounds` is immutable once pushed to VEKN (enforced backend + frontend)
- VEKN requires: name 3–120 chars, rounds 2–4, organizer must have `vekn_id`
- All players must have `vekn_id` before results can be pushed
- Organizer impersonated via `Vekn-Id` header on `create_event`

**Env vars required**: `VEKN_API_BASE_URL`, `VEKN_API_USERNAME`, `VEKN_API_PASSWORD`

**Key files**: `backend/src/vekn_push.py`, `backend/src/vekn_api.py`

## Calendar System

**iCal Feed Endpoint**: `GET /api/calendar/tournaments.ics` — generates iCal format for calendar client subscriptions.

**Feed Types**:
- **Personal**: `?token=<calendar_token>` — agenda matching (same country, online, NC/CC on continent, organizer, participant)
- **Country**: `?country=XX` — all tournaments in specified country
- **Global**: no params — all upcoming tournaments
- **Toggle**: `?online=false` — exclude online events from any feed

**Calendar Token**:
- `calendar_token` field on User model (nullable, generated on demand)
- Generated via `POST /auth/me/calendar-token` (returns `{ calendar_token, calendar_url }`)
- Stripped from SSE stream via `_filter_user()` — only visible via `/auth/me` endpoint
- DB: partial index on `calendar_token` (WHERE NOT NULL) for fast lookup

**Agenda Matching Logic** (`_matches_agenda()` in calendar.py):
1. User organizes (any state)
2. User participates (any state)
3. For non-finished only: same country, online, or NC/CC on user's continent

**Frontend Integration**:
- `getAgendaTournaments()` in db.ts — IndexedDB query matching backend agenda logic
- `getFilteredTournaments()` in db.ts — simplified filters (ongoing toggle, include online toggle, country/format/search)
- `generateCalendarToken()` in auth.svelte.ts — API call to generate token
- `getContinent()` / `getCountriesOnContinent()` in geonames.ts — continent matching for agenda

**Tournament List Rework**: Removed sort dropdown and state dropdown. Replaced with "My Agenda" toggle for logged-in members and "Include online" toggle. Both views use the same simplified filters.

## Internationalization (i18n)

**Library**: Paraglide JS (inlang) — client-only, no server-side rendering needed for SPA.

**Locales**: `en` (default), `fr`, `es`, `pt`, `it` — all message files in `frontend/messages/*.json`.

**Detection**: Browser locale auto-detection via `preferredLanguage` strategy + cookie persistence.

**Integration**: Vite plugin compiles messages to TypeScript. Import from `$lib/paraglide/messages` in components.

**Locale Switcher**: Desktop sidebar component (`LocaleSwitcher.svelte`) allows manual locale selection.

## Authentication

Multiple authentication methods, all producing JWT access/refresh token pairs.

### Methods

| Method | Flow | Key Files |
|--------|------|-----------|
| Email + Password | Register or login with email/password | `routes/auth.py` |
| Magic Link | Request link via email → verify token → set password | `email_service.py` |
| WebAuthn / Passkeys | FIDO2 registration + login (both new and existing users) | `routes/auth.py`, `passkeys.svelte.ts` |
| Discord OAuth | Login or link Discord account | `routes/auth.py` (discord authorize/callback) |

**Magic Link**: Used for signup, password reset, and invite flows. Link remains valid until the password is actually set (not just until verified). Frontend: `/auth/email/verify` route handles the landing page.

**Passkeys**: Four endpoints — `register/options` + `register/verify` (authenticated, add passkey to existing account), `create/options` + `create/verify` (unauthenticated, create new user with passkey).

**Discord OAuth**: `GET /auth/discord/authorize` initiates flow (with `mode` param: `login` or `link`). Callback at `GET /auth/discord/callback`. On login, matches by Discord ID or creates new user. On link, attaches Discord ID to authenticated user.

### JWT Structure

- Access token: short-lived, used for API auth
- Refresh token: longer-lived, used to obtain new access tokens
- OAuth tokens: separate `oauth_access` type with scope restrictions

## OAuth2 Provider

Full RFC 6749 / RFC 7636 (PKCE) implementation for third-party API access.

**Endpoints**: `/oauth/authorize` (GET+POST), `/oauth/token`, `/oauth/revoke`, `/oauth/userinfo`

**Client Management** (DEV role): `/oauth/clients` CRUD + secret regeneration

**Scopes**: `profile:read` (limited to /oauth/* endpoints), `user:impersonate` (full API access)

**Security**: PKCE S256 required, Argon2-hashed client secrets, refresh token rotation with revocation chain, single-use auth codes, consent persistence.

**Frontend**: `/oauth/consent` page, `DeveloperSection.svelte` in profile for client management.

**Key files**: `routes/oauth.py`, `db_oauth.py`, `models.py` (OAuth models), `middleware/auth.py` (token validation)

## Avatar System

User profile images with client-side cropping and server-side compression.

**Endpoints**: `POST /api/users/{uid}/avatar` (upload), `GET /api/users/{uid}/avatar` (serve), `DELETE /api/users/{uid}/avatar`

**Frontend**: `AvatarCropper.svelte` — client-side image cropping before upload.

**Storage**: Server-side file storage with compression on upload.

## VEKN Inbound Sync

Pulls data FROM vekn.net into Archon. Runs periodically (default every 6h).

### Member Sync (`vekn_sync.py`)

`VEKNSyncService` pulls the full VEKN member roster and reconciles with local users:
- Creates new User objects for unknown VEKN IDs
- Updates names, countries, roles for existing members
- Infers `coopted_by` relationships

### Tournament Sync (`vekn_tournament_sync.py`)

`sync_all_tournaments()` imports historical tournaments from VEKN API:
- Creates Tournament objects for past events
- Seeds venue autocomplete data from imported venue information
- Part of the periodic `run_vekn_sync` job

**Triggered by**: Scheduled background task + manual `POST /admin/sync-vekn` and `POST /admin/sync-vekn-tournaments`

## TWDA Outbound (Export)

Auto-submits winner's decklists to the [Tournament Winning Deck Archive](https://github.com/GiottoVerducci/TWD).

**Trigger**: On `FinishTournament`, if winner has a deck, `twda.py` creates a GitHub PR against the TWDA repository.

**Features**:
- TWDA-format text export per player (`GET /{uid}/decks/{player_uid}/twda`)
- Updates PR if decklist is modified after finish
- Late uploads (winner adds deck post-tournament) trigger PR at that point

**Key files**: `backend/src/twda.py`, `engine/src/deck.rs` (`export_twda`)

## TWDA Inbound (Import)

Pulls winner decklists from [static.krcg.org/data/twda.json](https://static.krcg.org/data/twda.json) and creates `DeckObject`s for matched tournaments.

**Trigger**: Runs as part of `run_vekn_sync()` (after tournament sync, before rating recompute). Manual trigger: `POST /admin/sync-twda-decks`.

**Matching logic**:
- Recent TWDA entries: numeric `id` matches `tournament.external_ids["vekn"]`
- Older entries: VEKN ID extracted from `event_link` URL
- Only creates a deck if the winner has no existing deck for that tournament

**DeckObject created**: `attribution="twda"`, `public=True`, cards flattened from nested crypt/library structure into `{card_id_str: count}`.

**ETag caching**: In-memory only (no persistent cache). `~12MB` JSON released via `del raw_entries` after parsing.

**Key file**: `backend/src/twda_import.py`

## Archon Import

Import tournament results from legacy Archon Excel files.

**Endpoints**:
- `GET /api/tournaments/archon-template` — download blank Excel template
- `POST /api/tournaments/{uid}/archon-import` — upload and process Excel file

**Parser** (`archon_import.py`): Extracts rounds, tables, seating, scores, and player data from the Excel format. Matches players by VEKN ID.

## Tournament Reports

**Endpoint**: `GET /api/tournaments/{uid}/report` — organizer-only download

**Formats**: Text (human-readable standings + results) and JSON (machine-readable full tournament data).

## Social Sharing

Canvas-rendered PNG card and plain text generator for sharing finished tournament results.

**Frontend files**: `social-card.ts` (PNG canvas), `social-text.ts` (text with deck info)

**UI**: Share button on `OverviewTab.svelte` for finished tournaments.

## User Account Merging

`POST /admin/users/merge` — merges two user accounts (IC/NC/Prince, same-country constraint).

Consolidates all associated data: sanctions, tournament participation, deck ownership, league organizer roles, ratings, and wins.

## Scheduled Background Tasks

| Job | Schedule | Module | Description |
|-----|----------|--------|-------------|
| VEKN sync | Every 6h (configurable) | `vekn_sync.py`, `vekn_tournament_sync.py`, `twda_import.py` | Pull members + historical tournaments from VEKN; import TWDA winner decks |
| VEKN push | Every 1h (configurable) | `vekn_push.py` | Batch push missed tournament events/results/members |
| Sanction cleanup | Daily | `db.py` | Soft-delete expired (>18mo), hard-delete soft-deleted (>30d) |
| Rating recompute | Daily | `ratings.py` | Full recompute of all player ratings and wins |
| OAuth cleanup | Hourly | `db_oauth.py` | Clean expired authorization codes and revoked tokens |
| Snapshot generation | Every 15 min | `snapshots.py` | Regenerate gzip snapshots (public/member/full) for initial sync |
| Deleted objects purge | Daily | `db.py` | Hard-delete soft-deleted objects older than 30 days |
