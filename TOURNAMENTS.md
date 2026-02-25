# Tournament System

This document describes the tournament management system implementation.

## Overview

The tournament system enables organizing VEKN-sanctioned tournaments with full offline support. Tournament state mutations are processed by the shared Rust engine, ensuring identical behavior in browser (WASM) and server (PyO3).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Tournament Event Flow                       │
└─────────────────────────────────────────────────────────────────┘

Online Mode:
┌──────────┐  Event   ┌──────────┐  Rust    ┌──────────┐
│ Frontend │─────────►│ Backend  │─────────►│ Engine   │
│ (Svelte) │          │ (FastAPI)│◄─────────│ (PyO3)   │
│          │◄─────────│          │ Updated  │          │
│          │   SSE    │          │ State    │          │
└──────────┘          └──────────┘          └──────────┘

Offline Mode:
┌──────────┐  Event   ┌──────────┐
│ Frontend │─────────►│ Engine   │
│ (Svelte) │◄─────────│ (WASM)   │
│          │ Updated  │          │
│          │ State    │          │
└──────────┘          └──────────┘
```

## Tournament State Machine

```
┌─────────┐     open      ┌──────────────┐    close     ┌─────────┐
│ Planned │──────────────►│ Registration │─────────────►│ Waiting │
└─────────┘               └──────────────┘              └────┬────┘
                                                              │
    ┌─────────────────────────────────────────────────────────┘
    │                                        ▲
    │ start round                            │ end round
    ▼                                        │
┌─────────┐                             ┌────┴────┐
│ Playing │────────────────────────────►│ Waiting │
└────┬────┘                             └────┬────┘
     │                                       │
     │ finish (no more rounds)               │ finish (no more rounds)
     ▼                                       ▼
┌──────────┐                           ┌──────────┐
│ Finished │                           │ Finished │
└──────────┘                           └──────────┘
```

### States

| State | Description | Key Actions |
|-------|-------------|-------------|
| `Planned` | Initial state, config editable | OpenRegistration, UpdateConfig, Delete |
| `Registration` | Players can register/unregister | Register, AddPlayer, CloseRegistration, CancelRegistration |
| `Waiting` | Between rounds, check-in active | CheckIn, CheckInAll, StartRound, StartFinals, FinishTournament, ReopenRegistration |
| `Playing` | Round in progress | SetScore, Override, FinishRound, CancelRound, seating edits |
| `Finished` | Tournament complete | ReopenTournament, deck uploads, view results |

Seating edits (SwapSeats, AlterSeating, SeatPlayer, UnseatPlayer, AddTable, RemoveTable) are available in Playing state. Payment and raffle actions available in Registration/Waiting/Playing. UpdateConfig available in Planned/Registration and for timer/display settings in later states.

## Business Events

Events are processed by the Rust engine. Each event includes:
- Tournament state (JSON)
- Event type and payload (JSON)
- Actor context: user UID, roles, organizer status (JSON)

### Event Types

#### State Transitions

| Event | Required Fields | Description |
|-------|-----------------|-------------|
| `OpenRegistration` | - | Planned → Registration |
| `CloseRegistration` | - | Registration → Waiting |
| `CancelRegistration` | - | Registration → Planned |
| `ReopenRegistration` | - | Waiting → Registration |
| `ReopenTournament` | - | Finished → Waiting |
| `FinishTournament` | - | Waiting/Playing → Finished |

#### Player Management

| Event | Required Fields | Description |
|-------|-----------------|-------------|
| `Register` | `user_uid` | Player self-registration |
| `Unregister` | `user_uid` | Player self-unregistration |
| `AddPlayer` | `user_uid` | Organizer adds player |
| `RemovePlayer` | `user_uid` | Organizer removes unplayed player (use DropOut if they have played) |
| `DropOut` | `player_uid` | Drop a player who has played (preserves their scores) |
| `CheckIn` | `player_uid` | Single player check-in |
| `CheckInAll` | - | All registered → checked-in |
| `ResetCheckIn` | - | All checked-in → registered |
| `SetPaymentStatus` | `player_uid`, `payment_status` | Toggle payment status (Pending/Paid/Refunded/Cancelled) |
| `MarkAllPaid` | - | Set all registered players to Paid |

#### Rounds & Seating

| Event | Required Fields | Description |
|-------|-----------------|-------------|
| `StartRound` | `seating?` | Creates round with seating (optional seating for deterministic forwarding) |
| `FinishRound` | - | Ends current round |
| `CancelRound` | - | Cancels current round, players return to Checked-in |
| `SwapSeats` | `round`, `table`, `seat_a`, `seat_b` | Swap two players within a table |
| `AlterSeating` | `round`, `seating` | Replace entire round or finals seating |
| `SeatPlayer` | `round`, `table`, `player_uid` | Add player to a specific table |
| `UnseatPlayer` | `player_uid` | Remove player from their current table |
| `AddTable` | - | Add empty table to current round |
| `RemoveTable` | `table` | Remove a table from current round |

#### Scoring

| Event | Required Fields | Description |
|-------|-----------------|-------------|
| `SetScore` | `round`, `table`, `scores[]` | Set table VP results (GW/TP auto-computed) |
| `Override` | `round`, `table`, `comment` | Judge forces table to Finished (requires comment) |
| `Unoverride` | `round`, `table` | Remove judge override |

#### Finals

| Event | Required Fields | Description |
|-------|-----------------|-------------|
| `SetToss` | `player_uid`, `toss` | Manually set toss value for finals qualification tie-breaking |
| `RandomToss` | - | Randomly assign toss values to tied players |
| `StartFinals` | - | Start finals round with top 5 qualifiers |
| `FinishFinals` | - | End finals (requires valid scores) |

#### Decks

| Event | Required Fields | Description |
|-------|-----------------|-------------|
| `UpsertDeck` | `player_uid`, deck fields | Create or update a player's deck |
| `DeleteDeck` | deck uid | Remove a deck |

#### Raffle

| Event | Required Fields | Description |
|-------|-----------------|-------------|
| `RaffleDraw` | `pool` | Draw from pool: AllPlayers, NonFinalists, GameWinners, NoGameWin, NoVictoryPoint |
| `RaffleUndo` | - | Undo last raffle draw |
| `RaffleClear` | - | Clear all raffle results |

#### Configuration

| Event | Required Fields | Description |
|-------|-----------------|-------------|
| `UpdateConfig` | `config` | Update tournament settings (timer, standings/decklists modes, table rooms, etc.) |

### Score Format

```json
{
  "type": "SetScore",
  "round": 0,
  "table": 0,
  "scores": [
    { "player_uid": "p1", "vp": 3.0 },
    { "player_uid": "p2", "vp": 1.5 }
  ]
}
```

Only VP is submitted. GW and TP are auto-computed by the engine (see Scoring Rules below).

### Override / Unoverride

```json
{ "type": "Override", "round": 0, "table": 0, "comment": "Player left early" }
{ "type": "Unoverride", "round": 0, "table": 0 }
```

Organizer-only. Override forces a table to "Finished" state regardless of score validity.
Requires a `comment` explaining the judge decision.

## Scoring Rules (VEKN 3.7.3)

Reference implementation: `archon/src/archon/scoring.py`

### VP (Victory Points)

- Range: 0 to `table_size` in 0.5 increments
- Value `table_size - 0.5` is impossible (e.g., 4.5 on a 5-player table)
- Total `ceil(vp)` for all seats must equal `table_size` for a complete game

### GW (Game Win)

- 1 if VP >= 2.0 AND strictly highest VP at the table (no tie), else 0
- Finals exception: winner gets GW even with < 2 VP (handled separately)

### TP (Table Points)

Position-based, ties average. Base values by table size:
- 5-player: `[60, 48, 36, 24, 12]` (highest VP first)
- 4-player: `[60, 48, 24, 12]`
- 3-player: `[60, 36, 12]`

Tied VP players share (average) the TP values for the positions they cover.

### Table State Determination

The engine determines table state as follows:

1. If `override` is set → **Finished** (judge forced it)
2. Run `check_table_vps` validation:
   - `InsufficientTotal` (sum of ceil'd VPs < table_size) → **In Progress** (scores incomplete)
   - Other validation error → **Invalid**
   - No error → **Finished**

### Oust Order Validation (`check_table_vps`)

This is the clever part from archon. VP combinations must match a physically possible oust order around the table. The algorithm simulates ousts:

1. Check table size is 4 or 5
2. Check total: `sum(ceil(vp) for each seat) == table_size`. Less = insufficient (in progress), more = excessive (invalid)
3. Simulate oust order around the table (seating order matters):
   - Find a seat with VP = 0 (an ousted player)
   - Transfer -1 VP to their predator (the seat before them) to "account" for the oust
   - Remove the ousted seat from the ring
   - Repeat until no more zero-VP seats
4. Remaining seats should all be at 0.5 (timeout survivors) or exactly one seat with 1.0 VP
5. Invalid states detected:
   - **MissingVP**: A fractional VP appears where an oust should have given a full point (e.g., `[0.5, 0]` sequence — the 0.5 player should have gotten a full VP for the oust)
   - **MissingHalfVP**: Multiple non-0.5 seats remain after processing all ousts, meaning the VP distribution doesn't match any possible game outcome
   - **ExcessiveTotal**: More total (ceil'd) VPs than players
   - **InvalidTableSize**: Not 4 or 5 players

Example: On a 5-player table `[2, 1, 0, 0.5, 1.5]` in seating order:
- Seat 3 (VP=0) is ousted → predator (seat 2) gets -1: seat 2 becomes 0
- Seat 2 (VP=0) is ousted → predator (seat 1) gets -1: seat 1 becomes 1
- Seat 1 (VP=0, after -1) is ousted → predator (seat 5) gets -1: seat 5 becomes 0.5
- Remaining: seat 4 (0.5), seat 5 (0.5) — valid timeout

## Data Model

### Tournament Structure

```typescript
interface Tournament {
  // Base
  uid: string;
  modified: string;
  
  // Config
  name: string;
  format: "Standard" | "V5" | "Limited";
  rank: "" | "National Championship" | "Continental Championship";
  online: boolean;
  start: string | null;
  finish: string | null;
  timezone: string;
  country: string | null;
  venue: string;
  description: string;
  max_rounds: number;
  
  // State
  state: "Planned" | "Registration" | "Waiting" | "Playing" | "Finished";
  organizers_uids: string[];
  players: Player[];
  rounds: Table[][];
  finals: FinalsTable | null;
  winner: string;
  
  // Privacy
  standings_mode: "Private" | "Cutoff" | "Top 10" | "Public";
  decklists_mode: "Winner" | "Finalists" | "All";
}

interface Player {
  user_uid: string | null;
  state: "Registered" | "Checked-in" | "Playing" | "Finished";
  payment_status: "Pending" | "Paid" | "Refunded" | "Cancelled";
  toss: number;
}

interface Table {
  seating: Seat[];
  state: "In Progress" | "Finished" | "Invalid";
  override: ScoreOverride | null;
}

interface Seat {
  player_uid: string;
  result: Score;
  judge_uid: string;
}

interface Score {
  gw: number;   // Game Wins (0 or 1)
  vp: number;   // Victory Points (0-5)
  tp: number;   // Table Points (0+)
}
```

## API Endpoints

### CRUD Operations

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/tournaments/` | Create tournament |
| `GET` | `/api/tournaments/{uid}` | Get tournament |
| `PUT` | `/api/tournaments/{uid}` | Update config |
| `DELETE` | `/api/tournaments/{uid}` | Delete (Planned only) |

### Action Endpoint (Rust Engine)

```
POST /api/tournaments/{uid}/action
```

Request body:
```json
{
  "type": "StartRound",
  "player_uid": null,
  "round": null,
  "table": null,
  "scores": null
}
```

### Other Tournament Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/{uid}/organizers` | Add organizer |
| `DELETE` | `/{uid}/organizers/{organizer_uid}` | Remove organizer |
| `POST` | `/{uid}/qr-checkin` | Player self-check-in via QR code |
| `POST` | `/{uid}/archon-import` | Import from legacy Archon Excel |
| `GET` | `/{uid}/report` | Download tournament report (text/JSON) |
| `GET` | `/{uid}/decks/{player_uid}/twda` | Export deck in TWDA format |
| `POST` | `/{uid}/timer/*` | Timer controls (start/pause/reset/add-time/clock-stop/clock-resume) |
| `POST` | `/{uid}/call-judge` | Player requests judge at table |
| `POST` | `/{uid}/go-offline` | Lock tournament for offline mode |
| `POST` | `/{uid}/go-online` | Submit offline changes and unlock |
| `POST` | `/{uid}/force-takeover` | Force take over offline lock |
| `POST` | `/{uid}/force-unlock` | Force-unlock without syncing |

## Seating Algorithm

The engine uses simulated annealing to compute optimal seating:

1. **Constraints**: Tables of 4-5 players, impossible counts (6, 7, 11) rejected
2. **Optimization**: Minimize repeated opponents across rounds
3. **Previous Rounds**: Algorithm considers history for better distribution

```typescript
// Frontend usage
const result = await computeSeating(playerUids, roundCount, previousRounds);
// result.rounds: string[][][] - player UIDs per table per round
// result.score: optimization metrics
```

## Frontend Integration

### Engine Wrapper (`frontend/src/lib/engine.ts`)

```typescript
// Initialize engine (called in layout)
await initEngine();

// Process tournament event (offline mode)
const updated = await processTournamentEvent(tournament, event, actor);

// Compute seating
const { rounds, score } = await computeSeating(players, 3, previousRounds);
```

### Tournament Actions

```typescript
// API client (online mode)
import { tournamentAction } from '$lib/api';

// Delegates to backend which uses Rust engine
await tournamentAction(uid, 'rounds/start');
await tournamentAction(uid, 'checkin', { player_uid: 'xxx' });
```

## Permission Model

Actions are validated by the Rust engine:

| Action | Who Can Perform |
|--------|-----------------|
| Create Tournament | IC, NC, Prince |
| Update Config | Organizers (Planned/Registration; timer/display settings in later states) |
| Delete | Organizers (Planned only) |
| Open/Close/Cancel/Reopen Registration | Organizers |
| Register/Unregister | Any authenticated member (Registration state) |
| Add/Remove/Drop Player | Organizers |
| Check In / Check In All / Reset Check-in | Organizers |
| Start/Finish/Cancel Round | Organizers |
| Set Score | Organizers or any player at the table |
| Override/Unoverride | Organizers |
| Seating edits (Swap, Alter, Seat, Unseat, AddTable, RemoveTable) | Organizers |
| Set Toss / Random Toss | Organizers |
| Start/Finish Finals | Organizers |
| Finish/Reopen Tournament | Organizers |
| Payment Status | Organizers |
| Raffle | Organizers |
| Deck Upload | Players (own deck) and Organizers (any deck) |

## SSE Streaming

Tournament updates are delivered via the unified SSE stream (see SYNC.md). Access-level projections are pre-computed at write time.

### Privacy Filtering

| Viewer Level | Data Received |
|--------------|--------------|
| `full` (organizer, IC, NC/Prince same country) | Everything including rounds, finals, checkin_code |
| `member` (has vekn_id) | Config, players (no per-player results), standings per mode, decks per mode |
| `public` (no auth) | Minimal tournament fields only |

Personal overlay additionally sends `full`-level data for own tournaments (organizer or participant).

## Offline Support

1. **IndexedDB Store**: `tournaments` store with `uid` key, `state` index
2. **WASM Engine**: Same Rust code as backend
3. **Sync**: Tournament events sent to backend on reconnect

### Offline Flow

```typescript
// 1. Get tournament from IndexedDB
const tournament = await getTournament(uid);

// 2. Build actor context
const actor = buildActorContext(currentUser, tournament);

// 3. Process event locally
const updated = await processTournamentEvent(tournament, event, actor);

// 4. Save to IndexedDB
await saveTournament(updated);

// 5. Queue for sync (when online)
await queueTournamentSync(updated);
```

## Files

### Rust Engine
- `engine/src/tournament.rs` - Event processing, state machine
- `engine/src/seating.rs` - Seating algorithm
- `engine/src/lib.rs` - WASM/PyO3 bindings

### Backend
- `backend/src/routes/tournaments.py` - API endpoints
- `backend/src/db.py` - Database operations
- `backend/src/models.py` - Data models

### Frontend
- `frontend/src/lib/engine.ts` - WASM wrapper
- `frontend/src/lib/api.ts` - API client
- `frontend/src/lib/db.ts` - IndexedDB store
- `frontend/src/lib/sync.ts` - SSE handling
- `frontend/src/lib/types.ts` - TypeScript types
- `frontend/src/routes/tournaments/+page.svelte` - List page
- `frontend/src/routes/tournaments/new/+page.svelte` - Create page
- `frontend/src/routes/tournaments/[uid]/+page.svelte` - Detail page

## Building

```bash
# Build Rust engine for both targets
just build-engine

# Or individually:
just build-engine-wasm    # WASM for frontend
just build-engine-python  # PyO3 for backend
```
