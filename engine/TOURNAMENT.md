# Tournament Engine

This document describes the Rust tournament engine implementation in `src/tournament.rs`.

## Overview

The tournament engine processes business events and returns updated tournament state. The same code runs in:
- **Browser** (WASM via wasm-bindgen) for offline mode
- **Server** (Python via PyO3) for online mode

This ensures identical behavior regardless of where events are processed.

**Key principle**: All tournament state mutations are business events processed by this engine. The backend does not have separate REST endpoints for individual event types — everything goes through `POST /{uid}/action` which delegates to the engine. This guarantees online and offline behavior are always identical.

## Entry Point

```rust
pub fn process_tournament_event(
    tournament_json: &str,
    event_json: &str,
    actor_json: &str,
) -> Result<String, String>
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `tournament_json` | Current tournament state (full Tournament object as JSON) |
| `event_json` | Event to process (see Event Types below) |
| `actor_json` | User performing the action (see Actor Context below) |

### Return Value

- **Success**: Updated tournament JSON string
- **Error**: Error message string

## Actor Context

Every action requires an actor context describing who is performing the action.

```json
{
  "uid": "user-uuid-here",
  "roles": ["Prince", "Judge"],
  "is_organizer": true
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | string | User's unique identifier |
| `roles` | string[] | VEKN roles: IC, NC, Prince, Ethics, PTC, PT, Rulemonger, Judge, Judgekin |
| `is_organizer` | bool | Whether user is in tournament's `organizers_uids` list |

### Permission Helper

```rust
impl ActorContext {
    pub fn can_manage_tournaments(&self) -> bool {
        self.roles.iter().any(|r| r == "IC" || r == "NC" || r == "Prince")
    }
}
```

## State Machine

The engine enforces a strict state machine for tournament progression.

```
┌─────────┐
│ Planned │  Initial state after creation
└────┬────┘
     │ OpenRegistration (organizer)
     ▼
┌──────────────┐
│ Registration │  Players can self-register
└──────┬───────┘
       │ CloseRegistration (organizer)
       ▼
┌─────────┐◄─────────────────────────────┐
│ Waiting │  Check-in phase              │
└────┬────┘                              │
     │ StartRound (organizer)            │ FinishRound (organizer)
     ▼                                   │
┌─────────┐──────────────────────────────┘
│ Playing │  Round in progress
└────┬────┘
     │ FinishTournament (organizer)
     ▼
┌──────────┐
│ Finished │  Tournament complete
└──────────┘
```

### State Types

```rust
pub enum TournamentState {
    Planned,      // "Planned"
    Registration, // "Registration"
    Waiting,      // "Waiting"
    Playing,      // "Playing"
    Finished,     // "Finished"
}
```

## Event Types

All events are represented as a single enum with associated data.

```rust
pub enum TournamentEvent {
    // State transitions
    OpenRegistration,
    CloseRegistration,
    FinishTournament,

    // Player management
    Register { user_uid: String },
    AddPlayer { user_uid: String },
    RemovePlayer { user_uid: String },
    CheckIn { player_uid: String },
    CheckInAll,

    // Round management
    StartRound,
    FinishRound,
    SetScore { round: usize, table: usize, scores: Vec<SeatScore> },
    Override { round: usize, table: usize, comment: String },
    Unoverride { round: usize, table: usize },
}
```

### Event JSON Format

Events are parsed from JSON with a `type` field and optional payload fields.

#### State Transition Events

```json
{ "type": "OpenRegistration" }
{ "type": "CloseRegistration" }
{ "type": "FinishTournament" }
```

#### Player Management Events

```json
{ "type": "Register", "user_uid": "player-uuid" }
{ "type": "AddPlayer", "user_uid": "player-uuid" }
{ "type": "RemovePlayer", "user_uid": "player-uuid" }
{ "type": "CheckIn", "player_uid": "player-uuid" }
{ "type": "CheckInAll" }
```

#### Round Management Events

```json
{ "type": "StartRound" }
{ "type": "FinishRound" }
{
  "type": "SetScore",
  "round": 0,
  "table": 0,
  "scores": [
    { "player_uid": "p1", "gw": 1, "vp": 3.0, "tp": 60 },
    { "player_uid": "p2", "gw": 0, "vp": 1.5, "tp": 24 }
  ]
}
```

## Event Processing Logic

### OpenRegistration

**Required state**: Planned
**Required permission**: Organizer

```rust
tournament["state"] = "Registration".into();
```

### CloseRegistration

**Required state**: Registration
**Required permission**: Organizer

```rust
tournament["state"] = "Waiting".into();
```

### Register

**Required state**: Registration
**Required permission**: Any authenticated user

1. Check player not already registered
2. Add player to `players` array with state `Registered`

```rust
let player = json::object! {
    user_uid: user_uid.as_str(),
    state: "Registered",
    payment_status: "Pending",
    toss: 0,
};
tournament["players"].push(player)?;
```

### AddPlayer

**Required state**: Registration or Waiting
**Required permission**: Organizer

Same as Register but organizer-initiated.

### RemovePlayer

**Required state**: Registration or Waiting
**Required permission**: Organizer

Removes player from `players` array by `user_uid`.

### CheckIn

**Required state**: Waiting
**Required permission**: Organizer

Sets player state to `Checked-in`.

```rust
players[idx]["state"] = "Checked-in".into();
```

### CheckInAll

**Required state**: Waiting
**Required permission**: Organizer

Sets all `Registered` players to `Checked-in`.

```rust
for i in 0..players.len() {
    if players[i]["state"].as_str() == Some("Registered") {
        players[i]["state"] = "Checked-in".into();
    }
}
```

### StartRound

**Required state**: Waiting
**Required permission**: Organizer

1. Check max rounds not exceeded
2. Collect checked-in player UIDs
3. Validate player count (≥4, not 6/7/11)
4. Extract previous rounds for seating optimization
5. Call seating engine: `seating::compute_next_round()`
6. Build tables JSON with empty scores
7. Set tournament state to `Playing`
8. Mark checked-in players as `Playing`

```rust
// Seating integration
let (new_round, _score) = seating::compute_next_round(
    &checked_in,
    &previous_rounds,
)?;

// Build table structure
let tables: Vec<JsonValue> = new_round
    .iter()
    .map(|table| {
        let seating: Vec<JsonValue> = table
            .iter()
            .map(|player_uid| {
                json::object! {
                    player_uid: player_uid.as_str(),
                    result: { gw: 0, vp: 0.0, tp: 0 },
                    judge_uid: "",
                }
            })
            .collect();
        json::object! {
            seating: seating,
            state: "In Progress",
            override: json::Null,
        }
    })
    .collect();
```

### FinishRound

**Required state**: Playing
**Required permission**: Organizer

1. Check all tables in current round have state `Finished`
2. Move all `Playing` players back to `Checked-in`
3. Set tournament state to `Waiting`

```rust
// Validate all tables finished
let unfinished: Vec<usize> = last_round
    .members()
    .enumerate()
    .filter(|(_, t)| t["state"].as_str() != Some("Finished"))
    .map(|(i, _)| i)
    .collect();

if !unfinished.is_empty() {
    return Err(format!("Tables {:?} not finished yet", unfinished));
}
```

### SetScore

**Required state**: Playing
**Required permission**: Organizer OR player at the table

1. Validate round and table indices
2. Check permission (organizer or seated at table)
3. Check table not locked by judge override (non-organizers blocked)
4. Validate VP values (range, 0.5 steps, impossible values)
5. Auto-compute GW and TP from VP values
6. Apply scores to matching seats
7. If organizer, set `judge_uid` on scored seats
8. Determine table state via `check_table_vps` oust-order validation

**Input**: Only `vp` per seat. GW/TP are computed, not submitted.

```json
{ "type": "SetScore", "round": 0, "table": 0,
  "scores": [{ "player_uid": "p1", "vp": 3.0 }] }
```

### Override

**Required state**: Playing
**Required permission**: Organizer only

Forces a table to "Finished" state regardless of score validity.
Requires a `comment` explaining the judge decision.

```json
{ "type": "Override", "round": 0, "table": 0, "comment": "Player left" }
```

### Unoverride

**Required state**: Playing
**Required permission**: Organizer only

Removes override, recomputes table state from scores.

```json
{ "type": "Unoverride", "round": 0, "table": 0 }
```

### FinishTournament

**Required state**: Waiting or Playing
**Required permission**: Organizer

1. Set tournament state to `Finished`
2. Mark all players as `Finished`

## Helper Types

### PlayerState

```rust
pub enum PlayerState {
    Registered, // "Registered" - signed up but not checked in
    CheckedIn,  // "Checked-in" - ready to play
    Playing,    // "Playing" - in current round
    Finished,   // "Finished" - dropped out or tournament ended
}
```

### TableState

```rust
pub enum TableState {
    InProgress, // "In Progress" - round active
    Finished,   // "Finished" - scores submitted
    Invalid,    // "Invalid" - score override applied
}
```

### SeatScore

```rust
pub struct SeatScore {
    pub player_uid: String,
    pub vp: f64,   // Victory Points (0.0-5.0), only field submitted
}
```

GW and TP are auto-computed by the engine from VP values. See Scoring section below.

## Scoring Rules (VEKN 3.7.3)

Reference implementation: `archon/src/archon/scoring.py`

### Auto-computed Fields

Only VP is submitted per seat. The engine computes:
- **GW**: 1 if VP >= 2.0 AND strictly highest at table (no tie), else 0
- **TP**: Position-based on VP rank, ties averaged:
  - 5-player: `[60, 48, 36, 24, 12]`
  - 4-player: `[60, 48, 24, 12]`
  - 3-player: `[60, 36, 12]`

### VP Validation

- Range: `[0, table_size]` in 0.5 steps
- Value `table_size - 0.5` is impossible (non-organizers rejected, organizers → Invalid)
- Total VP > table_size: non-organizers rejected, organizers → Invalid

### Table State Determination (`check_table_vps`)

Ported from archon's `scoring.check_table_vps()`. Determines table state:

1. **Override set** → Finished (judge forced)
2. **Invalid table size** (not 3-5) → Invalid
3. **Insufficient total** (`sum(ceil(vp)) < table_size`) → In Progress (incomplete)
4. **Excessive total** (`sum(ceil(vp)) > table_size`) → Invalid
5. **Oust order simulation** → validates VP distribution matches a possible game:
   - Walk the seating ring, find zero-VP seats (ousted players)
   - Transfer -1 VP to predator for each oust, remove ousted seat
   - After all ousts: remaining seats should be 0.5 (timeout/withdrawal) or one seat at 1.0
   - Detects MissingVP (fractional where full expected) and MissingHalfVP (impossible remainder)
6. **All valid** → Finished

Note: 0.5 VP can mean either a timeout survivor or a voluntary withdrawal. Both are valid.
The algorithm handles this by allowing any number of 0.5 remainders after oust processing.

### Override Mechanism

When a judge overrides a table, the table state is forced to "Finished" regardless of
score validity. This allows the tournament to proceed even with unusual situations
(player left, connection issues, etc.). The override includes a mandatory comment.

## Error Handling

All errors are returned as `Err(String)` with descriptive messages.

### Common Errors

| Error | Cause |
|-------|-------|
| `"Only organizers can perform this action"` | Non-organizer attempting privileged action |
| `"Tournament must be in X state (currently Y)"` | Wrong state for action |
| `"Already registered"` | Duplicate registration |
| `"Player not found"` | Invalid player UID |
| `"Need at least 4 checked-in players"` | Insufficient players for round |
| `"Cannot seat N players (impossible...)"` | 6, 7, or 11 players |
| `"Maximum rounds reached"` | Exceeded `max_rounds` setting |
| `"Not authorized to score this table"` | Non-seated player scoring |
| `"Table score is locked by judge"` | Player trying to modify judged table |
| `"Tables [N, M] not finished yet"` | Attempting to end round early |

## Validation Helpers

```rust
fn require_organizer(actor: &ActorContext) -> Result<(), String>;
fn require_state(current: TournamentState, expected: TournamentState) -> Result<(), String>;
fn player_exists(players: &JsonValue, user_uid: &str) -> bool;
fn find_player_index(players: &JsonValue, user_uid: &str) -> Option<usize>;
```

## Seating Integration

The engine delegates seating computation to `crate::seating::compute_next_round()`.

```rust
use crate::seating;

let (new_round, _score) = seating::compute_next_round(
    &checked_in,      // Vec<String> of player UIDs
    &previous_rounds, // Vec<Vec<Vec<String>>> history
)?;
```

See `src/seating.rs` for the simulated annealing algorithm details.

## Testing

The module includes unit tests for core functionality:

```rust
#[cfg(test)]
mod tests {
    #[test] fn test_open_registration() { ... }
    #[test] fn test_register_player() { ... }
    #[test] fn test_check_in_all() { ... }
    #[test] fn test_start_round_insufficient_players() { ... }
    #[test] fn test_non_organizer_cannot_open_registration() { ... }
}
```

Run tests:
```bash
cd engine
cargo test tournament
```

## Usage Examples

### Python (Backend)

```python
from archon_engine import PyEngine

engine = PyEngine()

# Process event
tournament_json = '{"uid": "...", "state": "Planned", ...}'
event_json = '{"type": "OpenRegistration"}'
actor_json = '{"uid": "org-1", "roles": ["Prince"], "is_organizer": true}'

try:
    updated = engine.process_tournament_event(
        tournament_json, event_json, actor_json
    )
    print(json.loads(updated)["state"])  # "Registration"
except ValueError as e:
    print(f"Error: {e}")
```

### TypeScript (Frontend)

```typescript
import { processTournamentEvent } from '$lib/engine';

const tournament = { uid: '...', state: 'Planned', ... };
const event = { type: 'OpenRegistration' };
const actor = { uid: 'org-1', roles: ['Prince'], is_organizer: true };

try {
    const updated = await processTournamentEvent(tournament, event, actor);
    console.log(updated.state);  // "Registration"
} catch (e) {
    console.error('Error:', e);
}
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     process_tournament_event                     │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. Parse JSON inputs                                            │
│     - tournament: JsonValue                                      │
│     - event: TournamentEvent                                     │
│     - actor: ActorContext                                        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Extract current state                                        │
│     TournamentState::from_str(tournament["state"])              │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Match event type and apply logic                             │
│     - Validate permissions (require_organizer)                   │
│     - Validate state (require_state)                             │
│     - Execute event-specific logic                               │
│     - Mutate tournament JsonValue                                │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. Return updated tournament as JSON string                     │
│     Ok(tournament.dump())                                        │
└─────────────────────────────────────────────────────────────────┘
```

## Design Decisions

1. **JSON-based interface**: Avoids tight coupling with specific type systems. Works equally well with Python msgspec and TypeScript.

2. **Immutable input, mutable processing**: Tournament is parsed into mutable JsonValue for in-place updates, then serialized back.

3. **Fail-fast validation**: All permission and state checks happen before any mutations.

4. **Seating delegation**: Round computation uses the battle-tested seating algorithm rather than duplicating logic.

5. **Actor context separation**: Permission data passed explicitly rather than embedded in tournament, enabling flexible authorization patterns.
