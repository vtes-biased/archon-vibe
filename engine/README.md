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

**Single source of truth for all authorization predicates** — consumed by backend (PyO3) and frontend (WASM). See `.pst/details/72-authz-rust-single-source.md` for the design rationale.

Role hierarchy: IC > NC > Prince (country-scoped) > Judge/Judgekin (displayed as Sheriff)

**User predicates** (take `UserContext {roles, country, vekn_id}`):
- `can_change_role(actor, target, role)` — can actor grant/revoke a role
- `can_manage_vekn(actor, target)` — can actor manage target's VEKN ID
- `can_edit_user(actor, target)` — can actor edit target's profile
- `is_official(actor)` — IC, NC, or Prince
- `can_manage_country(actor, target_country)` — IC (any), or NC/Prince of that country
- `can_manage_tournaments(actor)` — can create/manage tournaments (= `is_official`)
- `can_manage_leagues(actor)` — IC or NC

**Resource predicates** (take `OwnedResource {country, organizers_uids}`; league adds `open_to_country_princes`):
- `is_organizer(actor, actor_uid, tournament)` — in organizers list, IC, or same-country NC
- `can_edit_league(actor, actor_uid, league)` — IC, same-country NC, or a league organizer
- `can_link_tournament_to_league(actor, actor_uid, league)` — `can_edit_league`, or a same-country Prince when the league's `open_to_country_princes` flag is set (attach-only — no other league rights)

**Sanction predicates**:
- `can_issue_sanction(actor, actor_uid, level, tournament)` — IC/Ethics, or a tournament organizer (caution/warning/SA/DQ); IC/Ethics only for suspension/probation
- `can_lift_sanction(actor, actor_uid, ctx)` — takes a `SanctionContext` (level + tournament/league fields)

All exposed via both PyO3 and WASM bindings in `lib.rs`.

### Sanctions Reference (`src/sanctions.rs`)

Single source for the VEKN Judges-Guide v2 penalty reference: category/subcategory taxonomy, English labels, baseline penalties, escalation ladder. `sanction_reference_json()` → WASM `sanctionReference()` / PyO3 `sanction_reference()`. Consumed by `backend/src/models.py` (derives `SUBCATEGORIES_BY_CATEGORY`/`BASELINE_PENALTIES` at import), the frontend's `getSanctionReference()` (`engine.ts`), and the Discord bot via the public `GET /sanctions/reference` endpoint. Distinct from `tournament/sanctions.rs` (SA effective-round resolution — see TOURNAMENTS.md).

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

See [../TOURNAMENTS.md](../TOURNAMENTS.md) for the behavioral reference (state machine, full event catalog, scoring/oust-order, permissions, privacy projections). This README covers the engine's build, bindings, and entry-point signatures.

Features:
- **State machine**: Planned → Registration → Waiting → Playing → Finished
- **Event processing**: All mutations via typed events (Register, StartRound, SetScore, etc.)
- **Permission checking**: Role-based validation for each action
- **Seating integration**: Uses seating module for round generation

Entry points:
- `process_tournament_event(tournament, event, actor, sanctions, decks)` - Main event processor (returns `{tournament, deck_ops}`)
- `compute_final_standings(standings, winner)` - Reorder preliminary standings into VEKN final placement; shared by league GP/RTP scoring and the post-finals display. Exposed as WASM `computeFinalStandings` and PyO3 `compute_final_standings`.

The event enum lives in `tournament/types.rs`; the full catalog (with required state and permissions) is documented in [../TOURNAMENTS.md](../TOURNAMENTS.md).

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
