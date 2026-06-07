---
name: engine-test-topology
description: How to run engine + PyO3/WASM binding tests in archon-vibe, and what each layer actually validates
metadata:
  type: project
---

Running the cross-stack engine tests in archon-vibe has non-obvious gotchas.

**Why:** The Rust core (`engine/`) compiles three ways — plain `--lib` (logic + unit tests), `--features python` (PyO3), `--features wasm` (wasm-bindgen). Bindings are thin one-line delegations; the real logic lives in feature-free functions (e.g. `tournament::compute_final_standings`, public at crate root, no feature gate).

**How to apply:**
- Engine unit tests: `cd engine && cargo test --lib`. This is the authoritative logic suite.
- PyO3 binding: validate with `cargo check --features python --lib` (type-check only). A full `cargo build`/`cargo test --features python` **fails to link** with `__Py_*` "symbol(s) not found for architecture arm64" — that is expected `extension-module` behavior (Python symbols resolve at import time, not link time), NOT a code error. Build the real wheel via maturin, not cargo, to get an importable module.
- WASM binding: `cargo check --features wasm` needs `rustup target add wasm32-unknown-unknown` locally (often missing). Frontend `npm run check` validates the TS↔WASM `.d.ts` contract instead.
- The PyO3 module is package `archon_engine` (imported in backend as `from archon_engine import PyEngine`), built into `engine/.venv/.../site-packages/archon_engine/*.so`. The repo `.venv` does NOT contain it. To run backend tests that import the engine: `PYTHONPATH=engine/.venv/lib/python3.13/site-packages ../.venv/bin/python -m pytest ...` from `backend/`. The installed .so can be stale (e.g. missing newly-added bindings) — fine for backend tests since the backend computes finalist position in Python (`ratings.py _finalist_position`), it does NOT call `compute_final_standings`/`compute_league_standings` (those are frontend/WASM-only consumers).
- To probe a feature-free engine fn ad-hoc without the link failure: drop a temp `engine/tests/_tmp_*.rs` integration test calling the public crate path (no `--features`), run, then delete it.

Backend tests touching scoring live in `backend/tests/test_ratings.py` (pure helpers, no DB). The DB-backed suites need Postgres via conftest.
