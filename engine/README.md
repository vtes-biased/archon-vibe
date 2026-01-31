# Archon Engine

Lightweight Rust engine for business logic, compiled to both WebAssembly (frontend) and native Python library (backend).

## Build

### For Python (Backend)
```bash
# Install maturin
uv tool install maturin

# Build wheel
cd engine
maturin build --release

# Install in venv
uv pip install target/wheels/*.whl
```

### For WebAssembly (Frontend)
```bash
# Install wasm-pack
cargo install wasm-pack

# Build WASM module (--no-opt to avoid wasm-opt compatibility issues)
cd engine
wasm-pack build --no-opt --target web --release --features wasm

# Output will be in pkg/ directory
```

### Run Tests
```bash
cd engine
cargo test --lib
```

## Docker Integration

Both backend and frontend Dockerfiles include Rust toolchain and build the engine:

- **Backend Dockerfile**: Uses `maturin` to build Python wheel, installed via `uv pip`
- **Frontend Dockerfile.test**: Uses `wasm-pack` to build WASM, copied to `src/lib/engine/`

## Usage

### Python (Backend)
```python
from archon_engine import PyEngine

engine = PyEngine()
result = engine.process_event(event_json, objects_json)

# Tournament event processing
updated_tournament = engine.process_tournament_event(
    tournament_json,
    '{"type": "StartRound"}',
    '{"uid": "...", "roles": ["Prince"], "is_organizer": true}'
)

# Compute seating
seating = engine.compute_seating(
    '{"players": ["p1", "p2", "p3", "p4", "p5"], "rounds": 3}'
)
```

### TypeScript (Frontend)
```typescript
import init, { WasmEngine } from './lib/engine';

await init();
const engine = new WasmEngine();
const result = engine.processEvent(eventJson, objectsJson);

// Tournament event processing
const updatedTournament = engine.processTournamentEvent(
  tournamentJson,
  '{"type": "StartRound"}',
  '{"uid": "...", "roles": ["Prince"], "is_organizer": true}'
);

// Compute seating
const seating = engine.computeSeating(
  '{"players": ["p1", "p2", "p3", "p4", "p5"], "rounds": 3}'
);
```

## Modules

### Permissions (`src/permissions.rs`)

Role-based access control for VTES organization hierarchy:

- **`can_change_role(manager, target, role)`** - Check if manager can grant/revoke a role
- **`can_manage_vekn(manager, target)`** - Check if manager can manage target's VEKN ID
- **`can_edit_user(manager, target)`** - Check if manager can edit target's profile

Role hierarchy: IC > NC > Prince (country-scoped) > Judge/Judgekin

### Seating (`src/seating.rs`)

VEKN tournament seating algorithm per official rules:
- [Official seating priorities](https://groups.google.com/g/rec.games.trading-cards.jyhad/c/4YivYLDVYQc/m/CCH-ZBU5UiUJ)

Features:
- **Simulated annealing** optimization for large player counts
- **Precomputed optimal seatings** for 4-25 players (instant results)
- **Violation scoring**: same-table, position adjacency, predator-prey tracking
- **Stochastic fallback** when SA exceeds iteration limit
- **Dropout/addition** handling between rounds

Entry points:
- `compute_seating(players, rounds, history)` - Main seating computation
- `score_seating(seating, history)` - Evaluate seating quality

### Tournament (`src/tournament.rs`)

Tournament state machine and event processing for offline-first tournament management.

See [TOURNAMENT.md](TOURNAMENT.md) for business requirements.

Features:
- **State machine**: Planned → Registration → Waiting → Playing → Finished
- **Event processing**: All mutations via typed events (Register, StartRound, SetScore, etc.)
- **Permission checking**: Role-based validation for each action
- **Seating integration**: Uses seating module for round generation

Entry points:
- `process_tournament_event(tournament, event, actor)` - Main event processor

Events:
- `OpenRegistration`, `CloseRegistration`, `FinishTournament`
- `Register`, `AddPlayer`, `RemovePlayer`
- `CheckIn`, `CheckInAll`
- `StartRound`, `FinishRound`
- `SetScore`

## Design

- Minimal dependencies (json-rust, wasm-bindgen, PyO3)
- Business logic in pure Rust
- JSON-based interface for easy integration
- Size-optimized release builds
- Feature-gated bindings (`python` / `wasm`)

## Dependencies

- `json` (0.12) - Lightweight JSON library
- `rand` (0.8) - Random number generation (for seating algorithm)
- `getrandom` (0.2, with `js` feature) - Entropy source for WASM
- `wasm-bindgen` (0.2) - WASM bindings (optional, `--features wasm`)
- `pyo3` (0.27) - Python bindings (optional, `--features python`)
