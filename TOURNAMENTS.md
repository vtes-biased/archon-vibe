# Tournament System

This document describes the tournament management system implementation.

## Overview

The tournament system enables organizing VEKN-sanctioned tournaments with full offline support. Tournament state mutations are processed by the shared Rust engine, ensuring identical behavior in browser (WASM) and server (PyO3).

## Architecture

Online: Frontend → Backend (FastAPI) → Rust engine (PyO3) → updated state → SSE → Frontend. Offline: Frontend ↔ Rust engine (WASM), applied directly to IndexedDB. Same engine code both paths — see ARCHITECTURE.md (Mutation Pipeline, Offline Mode).

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
| `Playing` | Round in progress | SetScore (players + organizers), Override, FinishRound, CancelRound, seating edits |
| `Finished` | Tournament complete | ReopenTournament, SetScore/Override (organizers only), deck uploads, view results |

Seating edits (SwapSeats, AlterSeating, SeatPlayer, UnseatPlayer, AddTable, RemoveTable) are available in Playing state. Payment and raffle actions available in Registration/Waiting/Playing. UpdateConfig available in Planned/Registration and for timer/display settings in later states. SetScore/Override/Unoverride: players only during Playing; organizers may correct any round while Waiting, Playing, or Finished (i.e. whenever rounds exist) — standings recompute after each edit.

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
| `AlterSeating` | `round`, `seating` | Positional prefix match: existing tables matched by index (results preserved same-table, reset cross-table); extra payload tables appended fresh; each table must seat 0/4/5 players (0 = empty draft workspace, dropped after rebuild). Finals: replaces seat order, same player set. |
| `SeatPlayer` | `table`, `player_uid`, `seat` | Add player to a table in the **last** round |
| `UnseatPlayer` | `player_uid` | Remove player from their seat in the **last** round |
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

### Score / Override

- `SetScore`: only VP is submitted per seat (`{player_uid, vp}`); GW and TP are auto-computed by the engine (see Scoring Rules below). Players may submit during Playing only; organizers may correct any round while Waiting, Playing, or Finished — stored standings recompute after each correction.
- `Override` (organizer-only): forces a table to **Finished** regardless of score validity; requires a `comment`. Available while Waiting/Playing/Finished (same organizer-anytime rule as SetScore). `Unoverride` reverts.

## Scoring Rules (VEKN 3.7.3)

Implemented in `engine/src/tournament/scoring.rs` (oust-order validation in the same module).

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

## Sanctions and Standings

Sanctions are a separate object type (see SYNC.md). The tournament-relevant sanction type is `standings_adjustment` (SA).

### Standings Adjustment (SA)

- **Penalty**: −1 VP applied to the target player's standings total for a specific round (Judges' Guide v2 §1.1.3).
- **Per-seat VP is untouched**: raw `seat.result.vp` stays valid (VP sum = table size, oust order preserved). The penalty lives only on the standings total.
- **GW and TP cascade**: because GW requires strictly highest VP at the table, −1 VP can flip a GW to a different player; TP re-ranks accordingly.
- **Round targeting** (per §1.1.3):
  - SA issued *during a game* → applies to that round.
  - SA issued *between rounds* or before finals → applies to the next round the player plays.
  - SA issued *after the last prelim round* → applies to the previous round they played.
  - SA issued *before round 1 pairings* → applies to round 1.
  - SA on a not-yet-scored round → deferred (penalty applies when that round is scored).
- **Engine is the single source of truth**: `compute_preliminary_standings` / `sa_vp_penalty` in `engine/src/tournament/standings.rs` applies the SA when computing standings. Both backend and frontend consume `tournament.standings` rather than re-deriving SA from raw seat results.
- **Mutation side-effect**: issuing, lifting, editing, or deleting an SA sanction tied to a tournament immediately triggers a standings recompute (`_recompute_tournament_standings()` in `backend/src/routes/sanctions.py`: load tournament → `PyEngine.update_standings` → save → broadcast). The updated tournament object is broadcast via SSE to all clients.
- **`PyEngine.update_standings`** is Python-only (like `compute_rating_vp_gw`); it is NOT exposed to WASM because sanctions have no offline-creation path.

## Data Model

Canonical shapes live in `frontend/src/lib/types.ts` (`Tournament`, `TournamentConfig`, `Player`, `Table`, `Seat`, `Score`) and `backend/src/models.py`. Non-obvious structure:

- `rounds: Table[][]` — outer index = round, inner = tables in that round; `finals` is a separate field (not a round).
- `Table` carries `seating: Seat[]`, a derived `state` (`In Progress`/`Finished`/`Invalid`), and an optional `override`.
- `Score = {gw, vp, tp}` per seat — only `vp` is user-submitted; `gw`/`tp` are engine-computed.
- Player `state` (`Registered`/`Checked-in`/`Playing`/`Finished`) and `payment_status` (`Pending`/`Paid`/`Refunded`/`Cancelled`); `toss` for finals tie-breaking.

## API Endpoints

### CRUD Operations

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/tournaments/` | Create tournament |
| `GET` | `/api/tournaments/{uid}` | Get tournament |
| `PUT` | `/api/tournaments/{uid}` | Update config |
| `DELETE` | `/api/tournaments/{uid}` | Delete (Planned only) |

### Action Endpoint (Rust Engine)

`POST /api/tournaments/{uid}/action` — body is `{type, ...payload}` for one of the events catalogued above (unused fields null/omitted).

### Other Tournament Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/{uid}/organizers` | Add organizer |
| `DELETE` | `/{uid}/organizers/{organizer_uid}` | Remove organizer |
| `POST` | `/{uid}/qr-checkin` | Player self-check-in via QR code |
| `POST` | `/{uid}/archon-import` | Import from legacy Archon Excel |
| `GET` | `/{uid}/report` | Download tournament report (text/JSON) |
| `POST` | `/{uid}/timer/*` | Timer controls (start/pause/reset/add-time) |
| `POST` | `/{uid}/call-judge` | Player requests judge at table |
| `POST` | `/{uid}/go-offline` | Lock tournament for offline mode |
| `POST` | `/{uid}/go-online` | Submit offline changes and unlock |
| `POST` | `/{uid}/force-takeover` | Force take over offline lock |
| `POST` | `/{uid}/force-unlock` | Force-unlock without syncing |

## Seating Algorithm

The engine uses simulated annealing to compute optimal seating:

1. **Constraints**: Tables of 4-5 players, impossible counts (6, 7, 11) rejected
2. **Optimization**: Minimize repeated opponents across rounds, considering previous-round history

Frontend entry point: `computeSeating(playerUids, roundCount, previousRounds)` in `engine.ts` → player UIDs per table per round.

## Frontend Integration

- **Offline mode**: `frontend/src/lib/engine.ts` wraps the WASM engine — `processTournamentEvent(tournament, event, actor, sanctions, decks)` and `computeSeating(players, rounds, previousRounds)`.
- **Online mode**: `tournamentAction()` in `frontend/src/lib/api.ts` POSTs the event to the backend (which runs the same engine via PyO3) and applies the optimistic update. See ARCHITECTURE.md (Mutation Pipeline).

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
| Set Score | Players at the table (Playing only); organizers (Waiting/Playing/Finished) |
| Override/Unoverride | Organizers (Waiting/Playing/Finished) |
| Seating edits (Swap, Alter, Seat, Unseat, AddTable, RemoveTable) | Organizers |
| Set Toss / Random Toss | Organizers |
| Start/Finish Finals | Organizers |
| Finish/Reopen Tournament | Organizers |
| Payment Status | Organizers |
| Raffle | Organizers |
| Deck Upload | Players (own deck) and Organizers (any deck) |

## SSE Streaming

Tournament updates ride the unified SSE stream with access-level projections pre-computed at write time. The per-level field visibility for tournaments (and the personal `full` overlay for own/organized tournaments) is canonically documented in **SYNC.md** (Data Levels + Tournament Field Visibility).

## Offline Support

Offline uses a device-lock model (no CRUD log / conflict resolution): the organizer locks the tournament to one device, the WASM engine applies events directly to the `tournaments` IndexedDB store (same Rust code as the backend), and full state is pushed to the server on go-online. See ARCHITECTURE.md (Offline Mode) and SYNC.md for the lock lifecycle and temp-UID remapping.

## Files

### Rust Engine
- `engine/src/tournament/` - Event processing, state machine, scoring, standings, raffle (entry point `process_tournament_event(tournament, event, actor, sanctions, decks)` → `{tournament, deck_ops}`)
- `engine/src/seating/` - Seating algorithm
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

`just build-engine` (both targets), or `build-engine-wasm` / `build-engine-python` individually. See ARCHITECTURE.md / engine/README.md.
