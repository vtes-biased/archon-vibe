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

> `wasm-pack` needs the **rustup** toolchain (it has the `wasm32-unknown-unknown` target); a Homebrew `cargo` lacks it. The `just dev` recipe already prepends `~/.cargo/bin`, but a standalone `wasm-pack`/`cargo` invocation needs `PATH="$HOME/.cargo/bin:$PATH"`. (The PyO3 `maturin develop` build is fine with either toolchain.)

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
    '{"uid": "...", "roles": ["Prince"], "is_organizer": true}',
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
```

## Modules

### Permissions (`src/permissions.rs`)

**Single source of truth for every authorization rule** — consumed by backend
(PyO3), frontend (WASM) and, through `/oauth/userinfo`, the Discord bot. See
`wiki/access.md` for the capability matrix and the rationale.

The rules are **data**, not functions:

- `CAPABILITIES` — one row per distinct authority: the roles that hold it
  globally, the roles that hold it over their own country, whether it is
  self-service, whether an organizer of the resource qualifies, and the
  user-facing denial. Deny by default.
- `ROLE_APPOINTMENTS` — one row per role: who may grant or revoke it.

A matrix change edits a row. The published matrix lives in wiki/access.md
(Authorization); this file describes the mechanism.

**Evaluating** — `check(capability, &Request)` is the single decision point.
`Request` carries the actor plus only what the row reads (`target_uid`,
`target_country`, `resource`); an absent field matches no grant. Both bindings
expose it as one entry point, `check_permission(capability, request_json)`.

**Resolvers** — the few rules with a precondition the table cannot express keep
a thin function over `check`: `can_change_role` (the appointment matrix plus the
target's `vekn_id`), `can_change_country` (the authority over the target's
highest official role), `can_issue_sanction` / `can_lift_sanction` /
`can_delete_sanction` (level and tournament state select the capability),
`can_link_tournament_to_league` (the `open_to_country_princes` flag), and
`is_organizer` / `can_edit_league` (named wrappers over one capability each).

**Not authority** — `is_official(actor)` answers whether someone holds the
official badge, for badges and quotas only; `unconditional_capabilities(actor)`
lists what an actor holds anywhere, for remote clients that must decide what to
offer without carrying their own copy of the matrix.

### Sanctions Reference (`src/sanctions.rs`)

Single source for the VEKN Judges-Guide v2 penalty reference: category/subcategory taxonomy, English labels, baseline penalties, escalation ladder. `sanction_reference_json()` → WASM `sanctionReference()` / PyO3 `sanction_reference()`. Consumed by `backend/src/models.py` (derives `SUBCATEGORIES_BY_CATEGORY`/`BASELINE_PENALTIES` at import), the frontend's `getSanctionReference()` (`engine.ts`), and the Discord bot via the public `GET /sanctions/reference` endpoint. Distinct from `tournament/sanctions.rs` (SA effective-round resolution — see wiki/tournaments.md).

Revision checklist — grouping/baselines/escalation propagate from here alone, but the *vocabulary and display* layers are still per-consumer: (1) the Python enums in `backend/src/models.py` (their constructors raise at backend boot on a key they don't know — loud); (2) the TS unions in `frontend/src/lib/types.ts` and the `subcategoryLabel` map in `TournamentSanctionModal.svelte` plus the 5 locale files (an unknown key renders as its raw key — quiet, so check these); (3) the bot caches the reference per process — restart it after a backend deploy that revises the tables.

### Seating (`src/seating/`)

VEKN tournament seating algorithm per official rules:
- [Official seating priorities](https://groups.google.com/g/rec.games.trading-cards.jyhad/c/4YivYLDVYQc/m/CCH-ZBU5UiUJ)

Features:
- **Simulated annealing** optimization for large player counts
- **Violation scoring**: same-table, position adjacency, predator-prey tracking
- **Stochastic fallback** when SA exceeds iteration limit
- **Dropout/addition** handling between rounds

Entry points:
- `compute_next_round(players, previous_rounds, seed)` - Seating for the next round (the StartRound path)
- `score_seating(seating, history)` - Evaluate seating quality

### Tournament (`src/tournament/`)

Tournament state machine and event processing for offline-first tournament management.

See [../wiki/tournaments.md](../wiki/tournaments.md) for the behavioral reference (state machine, full event catalog, scoring/oust-order, permissions, privacy projections). This README covers the engine's build, bindings, and entry-point signatures.

Features:
- **State machine**: Planned → Registration → Waiting → Playing → Finished
- **Event processing**: All mutations via typed events (Register, StartRound, SetScore, etc.)
- **Permission checking**: Role-based validation for each action
- **Seating integration**: Uses seating module for round generation

Entry points:
- `process_tournament_event(tournament, event, actor, sanctions, decks)` - Main event processor (returns `{tournament, deck_ops}`)
- `compute_final_standings(standings, winner)` - Reorder preliminary standings into VEKN final placement; shared by league GP/RTP scoring and the rating path. PyO3 `compute_final_standings`.
- `display_standings(tournament, sanctions)` - Rank a tournament's stored result sheet for display, final placement included. Exposed as WASM `displayStandings`; `sanctions` must be scoped to this tournament.

The event enum lives in `tournament/types.rs`; the full catalog (with required state and permissions) is documented in [../wiki/tournaments.md](../wiki/tournaments.md).

## Design

- Minimal dependencies (json-rust, wasm-bindgen, PyO3)
- Business logic in pure Rust
- JSON-based interface for easy integration
- Size-optimized release builds
- Feature-gated bindings (`python` / `wasm`)

## Dependencies

- `json` (0.12) - Lightweight JSON library
- `rand` (0.8) - Random number generation (seating shuffles, deterministic toss/raffle LCGs)
- `rand_chacha` (0.3) - Value-stable `ChaCha8Rng` for seeded, reproducible seating across WASM/PyO3
- `getrandom` (0.2, with `js` feature) - Entropy source for WASM
- `wasm-bindgen` (0.2) - WASM bindings (optional, `--features wasm`)
- `pyo3` (0.27) - Python bindings (optional, `--features python`)
