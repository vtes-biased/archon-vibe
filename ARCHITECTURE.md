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

### Discord Bot
- **Framework**: hikari + lightbulb + miru
- **Storage**: SQLite (token/guild state)
- **Process**: Separate from backend; pure OAuth client
- **Language**: Python

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
    "full" JSONB NOT NULL,
    calendar_token TEXT  -- owner-only secret; never in any projection (would
                         -- leak via SSE since "full" reaches IC/same-country NC)
);

CREATE INDEX idx_objects_type_modified ON objects(type, modified_at, uid);
```

Access-level projections (`public`/`member`/`full`) are computed by `access_levels.py` at **write time** and stored as separate JSONB columns. SSE streaming reads the appropriate column directly — no per-request filtering. This approach prioritizes:

- **Simplicity**: Single table, no migrations for schema changes
- **Performance**: Pre-computed projections, zero per-viewer filtering at read time
- **Flexibility**: Schema-less design for rapid iteration

`calendar_token` is the single non-projected column: a per-user `.ics` feed secret that must never be broadcast (every projection is, and `full` reaches non-owners). It's a column rather than a separate table — unlike `auth_methods`/`oauth_*` (N:1) or `avatars` (large blobs), it's 1:1 with the row with no independent lifecycle, so a column avoids a join on the hot `get_user_by_uid` path. `save_object` COALESCEs it so writes that don't carry the token preserve it; `clear_calendar_token()` is the explicit drop path.

### Database Access & Connection Model

psycopg3 async, no ORM. The pool is small (`max_size=20`, autocommit) — sized for a ~2GB VPS — so connections must cycle quickly: helpers check one out, run a query, release. The one place a connection is held across multiple operations is a transaction.

**`tournament_transaction(uid)`** is the unit of work for any tournament mutation (the action handler and every offline-lifecycle endpoint). It `SELECT ... FOR UPDATE`s the row — serializing concurrent writes to one tournament — and yields `(tournament, tx_conn)`. The caller saves through `tx_conn` so the read-modify-write is atomic.

**Connection discipline.** A request must never check out a *second* pooled connection while holding `tx_conn`: with 20 concurrent in-flight actions pinning all connections via their locks, any further acquire blocks → deadlock. So while a transaction is open, **reads transparently reuse its connection** via an ambient `ContextVar` (`_tx_conn`, read by `_acquire`): every read helper called on that task runs on `tx_conn`, seeing the transaction's snapshot, with no extra checkout. An action therefore consumes exactly one connection start to finish.

- **Reads** route through `_acquire` (explicit `conn=` → ambient `tx_conn` → pool). Inside a transaction they reuse automatically; no need to thread `conn` by hand.
- **Writes** route through `get_connection` and pool **independently** by default — they do *not* ride the ambient connection. This is deliberate: go-online creates users in a loop where each `save_user` must commit and be visible to the next `allocate_next_vekn_id` (which runs its own advisory-locked transaction); folding those inserts into the outer transaction would hide them and reissue duplicate VEKN IDs. A write joins the transaction only when passed `conn=tx_conn` explicitly (e.g. the action handler's single tournament save), keeping the read/write transaction boundary visible at the call site.
- **Invariant:** never start a DB-touching `asyncio.create_task`/`gather` inside a transaction — the child task inherits the ContextVar and would interleave operations on the shared connection (single-threaded, but one `await execute` yields mid-flight) or outlive the `with` block. `_acquire` records the owner task and **raises** if the ambient connection is reached from another task, so this fails loudly. All spawned DB tasks today (Discord role sync, VEKN sync) fire post-commit, outside any transaction.

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
- **Flow**: Database change → CRUD event → SSE → IndexedDB sync

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

### Device-Lock Model

Offline mode uses primary device ownership — no CRUD log or conflict resolution needed:

1. Organizer takes tournament offline via `go-offline` → tournament locked to their device
2. Other devices see "offline" message — no mutations available
3. Business events processed locally by WASM Rust engine → IndexedDB updated directly
4. Offline-created players get temp UIDs (remapped to real UIDs on sync)

### Going Back Online

```
┌─────────────┐                           ┌──────────────┐
│   Svelte    │  1. Send full tournament  │   FastAPI    │
│     PWA     │     state + offline data  │   Backend    │
│  (primary)  ├──────────────────────────►│              │
│             │                           │              │
│             │  2. Server overwrites,    │              │
│             │     remaps temp UIDs      │              │
│             │◄──────────────────────────┤              │
│             │                           │              │
│             │  3. Resume SSE            │              │
│             │◄──────────────────────────┤              │
└─────────────┘                           └──────────────┘
```

### Ownership & Transfer
- **Primary device** is authoritative — server accepts its full state on go-online
- **Force-takeover**: another organizer can claim the lock (warned about losing primary's unsaved data)
- **Opportunistic sync**: primary device can background-sync without unlocking (`sync-offline`)
- **IC force-unlock**: emergency unlock without syncing offline data (first-party IC sessions only — OAuth tokens rejected). UI: crimson button in the "locked by another device" banner.
- **Lock-loss reconciliation**: when a force-unlock or takeover reaches the previously isolated device via SSE/snapshot, it clears local offline state and warns the user their unsynced changes are discarded. `go-online` returns 410 if the server is no longer in offline mode, preventing a stale snapshot from clobbering authoritative state. See SYNC.md (Offline Mode) for the full mechanics.

go-online resolves/creates offline players (`save_user`/`allocate_next_vekn_id`) **before** taking the `FOR UPDATE` lock: an unlocked pre-check gates side effects (organizer + device lock), then the lock only re-verifies authoritatively, remaps temp UIDs, and saves — so no per-player connection is checked out while the row is locked. Benign race: if organizer rights are revoked between the pre-check and the lock, the re-check 403s after the users were already created (orphaned, harmless).

## Mutation Pipeline

Tournament actions use optimistic updates via WASM:
1. WASM processes locally → returns `{tournament, deck_ops}` → IndexedDB updated → UI reacts immediately
2. Server POST sent async → on success SSE delivers authoritative state → overwrites if different
3. On rejection (no SSE follows, `modified_at` unchanged) → roll back to the pre-action snapshot held in memory + surface error. See SYNC.md (Optimistic Updates, Sync Cursor) for the cursor (`since`/`ts` over `modified_at`) and queue-overflow stream-close behavior.

### StartRound Seating Forwarding

`StartRound` accepts optional `seating: Vec<Vec<String>>` (table → ordered player UIDs). When provided, the engine validates it and uses it directly instead of computing seating.

**Determinism**: seating computation is seeded — `seating::seed_for_round(tournament_uid, round_index)` feeds a `ChaCha8Rng` (value-stable across platforms), so WASM (offline), PyO3 (backend/bot), and the browser all compute byte-identical seating for the same tournament + round. The forwarding below is therefore a safety net (guaranteeing agreement even if engine builds drift), not a correctness requirement.

**Forwarding** (`tournamentAction()` in `api.ts`): after WASM processes `StartRound`, extract the computed seating from the result and inject it into the server POST:

```typescript
if (action === 'StartRound' && newRoundAdded) {
  const newRound = result.tournament.rounds[result.tournament.rounds.length - 1]!;
  serverEvent = { ...event, seating: newRound.map(t => t.seating.map(s => s.player_uid)) };
}
```

**Validation** (engine, `tournament/mod.rs`):
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

**Standings Modes**: RTP (rating points), Score (GW/VP/TP), GP (Grand Prix position-based). GP and RTP scoring use `compute_final_standings` to derive final placement (winner=1, other finalists=2).

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
- `permissions.rs` - **Single source for all authorization predicates** (see below)
- `seating/` - Tournament seating algorithm (simulated annealing + staggered seatings)
- `tournament.rs` - Tournament event processing (state machine, scoring, finals)
- `deck.rs` - Deck parsing, validation, enrichment, TWDA export
- `ratings.rs` - Rating points computation
- `league.rs` - League standings computation (RTP/Score/GP); GP/RTP scoring delegates to `compute_final_standings` for final placement
- `tournament/standings.rs` - `compute_preliminary_standings` (GW/VP/TP/toss sort). GW and TP are **recomputed** per table from raw VPs + current sanctions (`sanctions::table_sa_adjustments` → `compute_gw`/`compute_tp`), so an SA issued *after* a round was scored still re-decides the GW and re-ranks/re-averages TP — the frozen seat `result.gw`/`result.tp` would otherwise go stale. VP sums raw per-seat VP then subtracts the full SA penalty (`-1` per played-round SA, `sa_vp_penalty`), which may go negative; per-seat `result.vp` stays raw for display. `compute_rating_vp_gw` (single source for the backend rating/VEKN-push paths) applies the same rule and additionally includes finals VP/GW. `compute_final_standings` (winner=rank 1; other finalists share rank 2 per VEKN §3.7.5; non-finalists competition-ranked from finalist_count+1). Whether a final happened is read from the per-player `finalist` flag, not from finals seating data.
- `cards.rs` - Card database (lookup by ID/name, normalization)

**Engine Error Contract**: `engine/src/error.rs` is the single taxonomy for all engine rejections — it defines the `EngineError` enum (~70 variants) with stable `code()` strings (e.g. `"tournament.already_registered"`) and `params()` for i18n interpolation. `Display` renders canonical English kept byte-identical to `frontend/messages/en.json` `err_*` values. New error sites must use an explicit variant; `From<&str>`/`From<String>` exist only for genuine deserialization failures and `.ok_or("x required")?`-style internal notes — they collapse to `Internal { detail }`.

**Wire shapes per surface**:

| Surface | Shape | Notes |
|---------|-------|-------|
| WASM (frontend) | JS string thrown: `{"code","params","message"}` | `callEngine()` in `engine.ts` wraps raw WASM calls, re-throws as typed `EngineError` |
| PyO3 (backend) | `ValueError` with same JSON body | `EngineRejection.from_engine()` in `engine_errors.py` parses it |
| HTTP 400 (backend→frontend) | `{"detail": "<English>", "code": "...", "params": {...}}` | `detail` stays a string for Discord bot + legacy clients; handler in `main.py` |

**Frontend fallback order** (`toUserMessage` in `errors.ts`; the same mapping localizes `apiRequest` toasts):
1. `code` present → `errorCodeToMessage(code, params)` → paraglide `err_*` key (5 locales)
2. No code or unknown code → server `detail` string (English)
3. Neither → `"Request failed: <statusText>"`
- `internal` code → generic localized message + `console.error` of raw detail (parse/invariant noise never shown to user)
- Unknown future code (version skew) → falls through silently to step 2

App-level checks that mirror engine rules reuse engine codes so the same condition localizes identically on every path: the backend `_check_player_barred` raises `EngineRejection` directly, and its frontend twin `checkPlayerBarred` (tournament-actions.ts) throws a coded `EngineError` — keeping the offline path localized too.

**Authorization (single source of truth)**: All role/country/uid/ownership predicates live in `engine/src/permissions.rs` and are consumed by both stacks — backend via PyO3, frontend via WASM. `backend/src/permissions.py` is a thin marshalling adapter (no logic); each route keeps its own `HTTPException(403, ...)` detail. The frontend wrappers (`isOrganizer()`, `canEditLeague()`, `canMarkDeceased()` in `engine.ts`) are UX-only and fail closed (`false`) until WASM loads — the backend remains the authoritative enforcement point. See `.pst/details/72-authz-rust-single-source.md` for the full design.

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

// Permission checks (sync, fail-closed on cold WASM engine)
const result = canChangeRole(actor, target, 'Prince');
const allowed = isOrganizer(user, tournament);  // false until WASM loads
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
```

**Tournament fields** (timer state):
- `timer: TimerState` — global round timer
- `table_extra_time: dict[str, int]` — table_idx → extra seconds

**TournamentConfig fields**:
- `round_time: int` — round duration in seconds (0 = no timer)
- `finals_time: int` — finals override (0 = use round_time)

### Sync Pattern

Server updates `tournament.timer` / `table_extra_time` and broadcasts the full Tournament CRUD event via SSE. Clients receive the state update and recompute the countdown from `started_at` + `elapsed_before_pause` using a local `setInterval(1000)`. No streaming of individual tick values.

### Endpoints (organizer-only, online-only, tournament must be in Playing state)

| Method | Path | Effect |
|--------|------|--------|
| POST | `/{uid}/timer/start` | Resume/start global timer |
| POST | `/{uid}/timer/pause` | Pause global timer |
| POST | `/{uid}/timer/reset` | Reset timer + clear all table extensions |
| POST | `/{uid}/timer/add-time` | Add extra seconds to one table (max 600s total) |

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
- `VITE_VEKN_PUSH=true` — frontend env, restricts `max_rounds` UI to 2–4, shows VEKN link badge and pending-sync badges

**Two-phase push** (both are fire-and-forget `asyncio.create_task` — never block user requests):
- **Phase 1** (on create): `push_tournament_event()` — creates VEKN calendar entry, stores returned event ID in `tournament.external_ids["vekn"]`
- **Phase 2** (on finish): `push_tournament_results()` — uploads archondata; sets `tournament.vekn_pushed_at`

Each phase SSE-broadcasts the updated object after saving, so clients reflect changes immediately without reconnecting.

Failures are log-only. The object is saved with the flag unset (`external_ids.vekn` absent or `vekn_pushed_at IS NULL`) before the background task runs, so the hourly batch retries automatically.

**Member push**: `push_member_background()` — `asyncio.create_task` on sponsor (`POST /vekn/sponsor`) and member create. Failures are log-only; `vekn_synced=false` flag queues the member for hourly batch retry.

**Batch push** (`batch_push()` in `vekn_push.py`): Hourly scheduled job catches all missed real-time pushes:
- Members: `vekn_synced=false`
- Tournament events: `external_ids.vekn` absent
- Tournament results: `vekn_pushed_at IS NULL` AND `rounds` array non-empty (guards VEKN-imported and archon-merged tournaments — both stamp `vekn_pushed_at` so results are never re-uploaded)

Outage-resilient: `batch_push` fails fast on the first connection/auth error (aborts, reruns next cycle) instead of re-timing-out every item; push functions re-fetch before writing the vekn flags so backlog drains don't clobber interim edits; job health is exposed at `GET /admin/vekn-status`. Detail in VEKN_SYNC.md.

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

## Community Links

Member-contributed links to external community resources (social channels, content, etc.), with moderator oversight.

### Data Model

```python
class CommunityLinkType(StrEnum):
    DISCORD | TELEGRAM | WHATSAPP | FORUM | FACEBOOK | WEBSITE | TWITCH | YOUTUBE
    | REDDIT | INSTAGRAM | BLOG | OTHER

class LinkModeration(msgspec.Struct):
    status: str        # "hidden" | "promoted"
    by: str            # moderator user_uid
    at: datetime
    scope: str | None  # promoted only: "global" (IC) | "national" (NC)

class CommunityLink(msgspec.Struct):
    type: CommunityLinkType
    url: str
    label: str = ""
    languages: list[str] = []   # ISO 639-1 codes, cap 5. Empty = shows under every filter.
    moderation: LinkModeration | None = None
```

`community_links: list[CommunityLink]` is a field on `User` (default `[]`).

Language validation: backend enforces two-letter shape only. The curated selectable list lives in `frontend/src/lib/data/languages.ts` (single source of truth for the UI).

### Access Control

- **Who can add links**: any user with `vekn_id` (VEKN member)
- **Link limit**: 5 for regular members; 10 for IC/NC/Prince
- **Moderation state preserved**: when a user updates their links, existing moderation is re-applied by URL match

**Moderation actions** via `PATCH /api/users/{user_uid}/community-link-moderation` (`{ url, action }`):

| Action | IC | NC (same country) | Prince (same country) |
|--------|----|-------------------|-----------------------|
| `hide` | yes | yes | yes |
| `clear` | yes | yes | yes |
| `promote_national` | yes | yes | — |
| `promote_global` | yes | — | — |

Self-moderation allowed: officials pin their own links.

### Access-Level Projection

| Level | community_links visibility |
|-------|---------------------------|
| public | NC/Prince users: included. IC: included (no contact). Others: hidden. |
| member | NC/Prince/IC: included. Any other user with non-empty links: included. |
| full | always included |

Handled by `compute_user_public()` and `compute_user_member()` in `access_levels.py`.

### Frontend Display

`CommunityTab.svelte` renders 3 sections:
- **Global Resources** — only links with `scope="global"` (IC global pin), from any owner
- **Communities** (`CommunitySocialSection.svelte`) — social links grouped by country; pinned (any scope) sort first within each country group
- **Content** (`CommunityContentSection.svelte`) — content links; language filter defaults to "All"; within each language group sorted: global pin → national pin → promoted → officials → rest
- **Officials Directory** — NC/Prince/IC contact info

`CommunityModerationActions.svelte` — inline hide/promote/clear controls for moderators.

Profile link editing (add/edit/delete) available to any member with `vekn_id`.

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

**Magic Link**: Used for signup, password reset, and invite flows. Link remains valid until the password is actually set (not just until verified). Frontend: `/verify-email` route handles the landing page.

**Passkeys**: Four endpoints — `register/options` + `register/verify` (authenticated, add passkey to existing account), `create/options` + `create/verify` (unauthenticated, create new user with passkey).

**Discord OAuth**: `GET /auth/discord/authorize` initiates flow (with `mode` param: `login` or `link`). Callback at `GET /auth/discord/callback`. On login, matches by Discord ID or creates new user. On link, attaches Discord ID to authenticated user.

### Discord Linked Roles

Pushes VEKN role metadata to Discord so server admins can gate roles based on Archon standing.

**OAuth scope**: `identify email role_connections.write` (added to existing Discord flow).

**Metadata fields** (registered via `PUT` to Discord API on startup):
| Field | Integer levels |
|-------|---------------|
| `organization` | 0=non-member, 1=VEKN member, 2=Prince, 3=NC, 4=IC |
| `judge` | 0=none, 1=Judgekin, 2=Judge, 3=Rulemonger |
| `playtest` | 0=none, 1=PT, 2=PTC |

**Token storage**: `discord_rc:{user_uid}` key in `transient_tokens` table, data `{access_token, refresh_token}`, 365-day expiry. No schema changes.

**Push triggers** (fire-and-forget `asyncio.create_task`):
- Discord login or link (OAuth callback)
- Role changes (`routes/users.py`)
- VEKN ID changes: claim, abandon, sponsor, link, force-abandon (`routes/vekn.py`)
- Periodic VEKN sync (`vekn_sync.py`)

**High-level flow** (`sync_user_discord_roles(user_uid)` in `roles_hook/__init__.py`): fetch stored token → refresh if expired → push metadata. No-op if user has no stored token.

**Constraint**: Discord's Linked Roles API requires the **target user's own OAuth token** — the backend cannot push metadata on behalf of a user who has never logged in via Discord OAuth. Metadata is only pushed when a stored token exists (`discord_rc:{user_uid}` key).

**Platform display**: `("Archon", vekn_id_or_name)` → shown in Discord as "Connected as 1234567 on Archon".

**Startup**: `register_metadata()` called if `DISCORD_CLIENTID` is set — idempotent PUT to Discord API requiring `DISCORD_BOT_TOKEN`.

**Key file**: `backend/src/roles_hook/__init__.py`

**Env vars**: `DISCORD_BOT_TOKEN` (new, for metadata registration) + existing `DISCORD_CLIENTID`, `DISCORD_SECRET`, `DISCORD_REDIRECT_URI`.

### JWT Structure

- Access token: short-lived, used for API auth
- Refresh token: longer-lived, used to obtain new access tokens
- OAuth tokens: separate `oauth_access` type with scope restrictions

## OAuth2 Provider

Full RFC 6749 / RFC 7636 (PKCE) implementation for third-party API access.

**Endpoints**: `/oauth/authorize` (GET+POST), `/oauth/token`, `/oauth/userinfo`

**Client Management** (DEV role): `/oauth/clients` CRUD + secret regeneration

**Scopes**: `profile:read` (limited to /oauth/* endpoints), `user:impersonate` (full API access)

**Security**: PKCE S256 required, Argon2-hashed client secrets, refresh token rotation with revocation chain, single-use auth codes, consent persistence.

**Frontend**: `/consent` page, `DeveloperSection.svelte` in profile for client management.

**Key files**: `routes/oauth.py`, `db_oauth.py`, `models.py` (OAuth models), `middleware/auth.py` (token validation)

## Discord Tournament Bot

> **Status:** the bot is **pre-production — not live and not yet tested** — but in scope for prod prep. Keep the relevant pst tickets updated when changing the bot.

Standalone process (`bot/`) — manages online VTES tournaments inside Discord servers. Pure OAuth client to the Archon backend; no direct DB access, no business logic. All mutations go through `POST /{uid}/action` via `user:impersonate` tokens on behalf of real users.

**Stack**: hikari + lightbulb + miru, SQLite for persistent token/state storage.

**Process isolation**: single process only (module-level state in `sse_listener.py`); communicates only via the Archon OAuth, REST APIs, and SSE stream.

### Commands

| Command | Description | Who |
|---------|-------------|-----|
| `/setup <url>` | Link an Archon tournament URL to the Discord guild; creates category + announcement/lobby/judges channels | NC/Prince/IC only |
| `/teardown` | Remove all bot-created channels and unlink tournament | Organizer |
| `/announce <message>` | Post to the announcement channel | Setup organizer, NC/Prince/IC |
| `/register` | Self-register for the tournament (VEKN ID claim or sponsorship request flow) | Any guild member |
| `/checkin` | Check in for current round | Any guild member |
| `/report <vp>` | Submit VP score via `SetScore` action | Seated player |
| `/judge` | Fire a `judge_call` event to organizers | Seated player |
| `/sanction` | Multi-step sanction flow (category → subcategory → details) | Organizer/judge |

### Architecture

| Module | Role |
|--------|------|
| `token_store.py` | SQLite: `tokens` (OAuth), `guild_tournaments` (links), `pending_oauth` (15-min TTL) |
| `archon_api.py` | HTTP client wrapping Archon REST; uses stored OAuth tokens |
| `sse_listener.py` | SSE subscription per active (guild, tournament) pair; drives Discord channel/announcement updates |
| `channel_manager.py` | Creates/syncs voice channels with per-player CONNECT+SPEAK permissions |
| `oauth_callback.py` | Local HTTP server handling PKCE OAuth redirect for user login |
| `commands/setup.py` | `/setup`, `/teardown`, `/announce` |
| `commands/player.py` | `/register`, `/checkin`, `/report`, `/judge` |
| `commands/judge.py` | `/sanction` |

### SSE Listener

Subscribes to a **tournament-scoped** SSE stream (`/stream?tournament=<uid>`) using the organizer's `user:impersonate` token — one connection per active (guild, tournament) pair. The scoped stream delivers only that tournament + its sanctions + judge calls; the bot never streams the whole corpus. Reacts to tournament lifecycle events:

- **Open/CheckIn state**: posts registration/check-in announcements to #announcement
- **RoundStart**: posts seating; creates per-table voice channels; syncs per-player CONNECT+SPEAK permissions; warns unlinked players
- **RoundFinish/Finals**: posts standings; deletes table voice channels; opens check-in for next round
- **Finish**: posts final standings; prompts `/teardown`
- **Mid-round seating changes** (SwapSeats, AlterSeating, etc.): detected via `_last_seating` diff → re-syncs voice channel permissions
- **`judge_call` ephemeral event**: posts to #judges channel
- **Catch-up on (re)connect**: the bot sends no `since` cursor, so the backend replays full current tournament state. Events seed state silently until a `sync_complete` message flips `synced`; only after that do events post announcements — so a restart/reconnect doesn't re-post past announcements. A `resync` message triggers a fresh reconnect.

Uses a shared `aiohttp` session across SSE reconnects. State tracked in module-level dicts (`_sse_tasks`, `_last_state`, `_last_round_count`, `_last_tournament`, `_last_seating`, `_table_channels`). All state cleaned up on `stop_sse` and teardown.

### Channel Permissions

- **#announcement**: @everyone DENY SEND_MESSAGES; bot has SEND_MESSAGES
- **Table voice channels**: @everyone DENY CONNECT; per-player + organizers ALLOW CONNECT+SPEAK
- Organizers can join any table voice channel for judging
- Permissions synced idempotently via `sync_table_permissions()`

### OAuth Flow

1. Organizer runs `/setup <url>` → bot initiates PKCE flow via `/oauth/token`
2. User authorizes `user:impersonate` scope → redirect to local callback server
3. Bot stores token in SQLite → uses it for all API calls and SSE subscriptions

### Player `display_name`

Register, AddPlayer, and CheckIn events accept an optional `display_name` field (Discord guild nickname). Stored on the `Player` model (`display_name: str | None`). Shown in `playerInfo` and `seatDisplay` in the frontend when present.

### Frontend `login_hint`

`/auth?login_hint=discord` auto-redirects to Discord OAuth, used by bot-generated links to streamline player login.

**Key directory**: `bot/src/`

**Constraints**: Only NC/Prince/IC can run `/setup`. Bot never holds privileged backend credentials.

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
- Updates identity (name, country, city/state) for existing members
- Never writes roles: seeded once by the ETL/legacy-archon sync, app-managed thereafter
- Infers `coopted_by` relationships
- Non-destructive: locally-modified fields (tracked in `local_modifications`) are never overwritten

### Tournament Sync (`vekn_tournament_sync.py`)

`sync_all_tournaments()` imports historical tournaments from VEKN API:
- Creates Tournament objects for past events
- Seeds venue autocomplete data from imported venue information
- Stamps `vekn_pushed_at=now` on finished imported tournaments — results came FROM vekn.net and must never be re-uploaded (importer folds finals into standings; archondata assumes prelim-only, so a re-push would send wrong numbers)
- Part of the periodic `run_vekn_sync` job

**Error handling**: each sync phase (member, tournament, TWDA) is wrapped independently; an exception or timeout in one phase logs an error and skips that phase for the current cycle without aborting the others.

**Triggered by**: Scheduled background task + manual `POST /admin/sync-vekn` and `POST /admin/sync-vekn-tournaments`

## TWDA Outbound (Export)

Auto-submits winner's decklists to the [Tournament Winning Deck Archive](https://github.com/GiottoVerducci/TWD).

**Trigger**: On the transition into `Finished` (if the winner has a deck), `twda.py` creates a GitHub PR against the TWDA repository. It also re-fires when the **winner's deck is upserted on an already-finished tournament** (organizer-only — players are deck-locked post-finish, `DeckLockedFinished`), so post-event edits and late uploads reach the archive.

**Features**:
- Idempotent PR (branch `archon/{vekn_event_id}` + file `decks/{id}.txt`, create-or-update): a re-fire updates the open PR rather than duplicating
- Post-finish organizer edits to the winning deck (e.g. an added strategy writeup) propagate to the PR

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

## Legacy-Archon Sync (`migrate_from_archon.py`)

`backend/scripts/migrate_from_archon.py` — two modes, same mapping code:

- **Insert-only ETL** (default): initial population of an empty new DB (`--truncate` wipes first). Used for beta rebuilds and as a disaster fallback.
- **Idempotent merge** (`--merge`): daily run on the new stack during the parallel-run period, old archon being a read-only second upstream until decommission. Cutover is freeze + final merge + vhost swap (no Phase-2 wipe).

**Single writer per field** (prevents daily flip-flop between syncs):

| Data | Writer |
|------|--------|
| identity (name/country/city/state) | VEKN sync |
| contact / nickname / discord / coopted_by / community links | archon sync |
| roles | nobody — seeded once by ETL, app-managed thereafter |
| sanctions, leagues | archon sync (upsert by source uid) |
| rich play data (rounds/seatings/decks/finals) | archon sync |
| `local_modifications` fields | nobody — local user edits trump both syncs |

**Tournament matching** (merge mode, at most one live tournament per vekn event id):
1. Match by uid (previously merged/ETL-imported) → idempotent update.
2. Else match by `external_ids.archon` (set when a prior run merged into a vekn-created copy) or `external_ids.vekn` → merge rich data INTO the vekn-created copy (its uid survives). Echo guard: round-less incoming copy never overwrites a rich original.
3. Else insert under old-archon uid.

Both-rich conflict (one-app-per-event violation) → logged loudly, skipped.

**Other invariants**: deterministic deck uids (uuid5 of tournament+user+round); pre-run `pg_dump` of the new DB (restore-fix-rerun recovery); merge writes are NOT live-broadcast over SSE (standalone process — clients catch up on next SSE reconnect); `vekn_pushed_at` stamped on merged finished tournaments so `batch_push` never re-uploads them.

**Runner**: systemd timer invoking the script directly (not an in-app scheduled job). Env: `OLD_DATABASE_URL`, `NEW_DATABASE_URL`.

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

## User Account Surgery

### Deceased Members

`User` carries two fields: `deceased_at: datetime | None` (the in-memoriam flag + date) and `deceased_by_uid: str | None` (audit, full-only). This is **not** a soft-delete — tournament history, ratings, and rankings are preserved; the record stays active in the system.

- **Set/cleared** via `PATCH /api/users/{uid}/deceased` (`{ deceased: bool }`). Reversible.
- **Permission**: IC (any country) or NC (same country only); Prince excluded. Engine: `can_mark_deceased` / WASM: `canMarkDeceased`.
- **VEKN sync**: never pushed to VEKN; `"deceased_at"` tracked in `local_modifications` to prevent VEKN-sync overwrite.
- **Access levels**: `deceased_at` visible at member+; `deceased_by_uid` full-only.

**Immovable-uid invariant**: a uid that carries a `vekn_id` is never re-keyed and never soft-deleted. Everything keyed to it — sanctions, decks, tournament results, ratings, wins, cooptation — stays attached. Only the account WITHOUT the `vekn_id` ever moves. See `.pst/details/59-vekn-detach.md` for the full rule.

### Merge (`POST /admin/users/merge`)

IC/NC/Prince only; same-country constraint. The VEKN-bearing uid is always the survivor (`keep_uid`). Migrates auth methods, sanctions, decks, and `coopted_by` references from the dying uid, then soft-deletes it. Consolidates ratings, wins, roles, and `local_modifications` (union). Implemented in `accounts.merge_users()`.

### Detach (`detach_user_from_vekn`)

Splits one account into two: the VEKN record keeps its uid and all keyed data (sanctions, decks, ratings, wins, cooptation, `community_links`); a fresh uid walks away with auth methods and personal/contact PII only. Two callers:

- **Self-abandon** (`POST /vekn/me/abandon`): user drops their own VEKN ID. Blocked while an active suspension or probation is held — the sanction stays with the VEKN record and cannot be escaped this way. Admin force-abandon is exempt.
- **Admin displace** (inside `POST /vekn/link`): frees a VEKN ID from its current holder before re-linking it to a new owner; the new owner account is then merged into the freed VEKN record.

## Scheduled Background Tasks

| Job | Schedule | Module | Description |
|-----|----------|--------|-------------|
| VEKN sync | Every 6h (configurable) | `vekn_sync.py`, `vekn_tournament_sync.py`, `twda_import.py` | Pull members + historical tournaments from VEKN; import TWDA winner decks |
| Legacy-archon merge | Daily (systemd timer) | `scripts/migrate_from_archon.py --merge` | Idempotent daily merge from old archon DB during the parallel-run period (parallel run only; decommissioned at cutover). See single-writer-per-field contract in [Legacy-Archon Sync](#legacy-archon-sync-migrate_from_archonpy) |
| VEKN push | Every 1h (configurable) | `vekn_push.py` | Batch push missed tournament events/results/members |
| Sanction cleanup | Daily | `db.py` | Soft-delete expired (>18mo), hard-delete soft-deleted (>30d) |
| Rating recompute | Daily | `ratings.py` | Full recompute of all player ratings and wins |
| OAuth cleanup | Hourly | `db_oauth.py` | Clean expired authorization codes and revoked tokens |
| Snapshot generation | Every 15 min | `snapshots.py` | Regenerate gzip snapshots (public/member/full) for initial sync |
| Deleted objects purge | Daily | `db.py` | Hard-delete soft-deleted objects older than 30 days |
