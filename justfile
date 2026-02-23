# Archon - just command runner

default:
    @just --list

# ============================================================================
# Core Commands
# ============================================================================

# Start full dev environment (db + backend + frontend), rebuilding engine first
dev:
    #!/usr/bin/env bash
    set -e
    just dev-stop
    echo "Building engine..."
    (cd engine && wasm-pack build --target web --release -- --features wasm)
    uv run maturin develop --release --manifest-path engine/Cargo.toml
    echo "Starting PostgreSQL database in Docker..."
    docker compose up -d db
    echo "Waiting for database to be ready..."
    for i in {1..30}; do
        docker compose exec -T db pg_isready -U archon > /dev/null 2>&1 && break
        sleep 1
    done
    echo "Database ready!"
    ENGINE_PKG=$(uv run python3 -c "import pathlib, archon_engine; print(pathlib.Path(archon_engine.__file__).parent)")
    DATABASE_URL=postgresql://archon:archon_dev_password@localhost:5433/archon \
    nohup uv run uvicorn backend.src.main:app --reload --reload-dir backend --reload-dir "$ENGINE_PKG" --reload-delay 2 --host :: --port 8000 --timeout-graceful-shutdown 1 > backend.log 2>&1 &
    echo "Backend started (PID: $!). Logs: backend.log"
    (cd frontend && nohup npm run dev > ../frontend.log 2>&1 &)
    echo "Frontend started. Logs: frontend.log"
    echo ""
    echo "  Database:  Docker on port 5433"
    echo "  Backend:   http://localhost:8000 (logs: backend.log)"
    echo "  Frontend:  http://localhost:5173 (logs: frontend.log)"
    echo "  Stop:      just dev-stop"

# Stop all local dev services
dev-stop:
    #!/usr/bin/env bash
    for port in 8000 5173; do
        pid=$(lsof -ti :$port 2>/dev/null) && kill -9 $pid 2>/dev/null && echo "Killed process on port $port" || true
    done
    docker compose stop db 2>/dev/null || true
    rm -f backend.log frontend.log

# Update all dependencies to latest versions
update:
    cargo install wasm-pack
    uv lock --upgrade && uv sync
    (cd frontend && npm update)
    (cd engine && cargo update)

# Run all tests
test:
    (cd engine && cargo test)
    uv run ruff check backend/
    uv run python3 -m pytest backend/tests/ -v
    (cd frontend && npx svelte-check --threshold error)

# Build production (Docker images)
build:
    #!/usr/bin/env bash
    set -e
    (cd engine && wasm-pack build --target web --release -- --features wasm)
    uv run maturin develop --release --manifest-path engine/Cargo.toml
    docker compose build

# ============================================================================
# Utility
# ============================================================================

# Lint and auto-fix all code
lint:
    uv run ruff check --fix backend/ && uv run ruff format backend/
    (cd engine && cargo fmt && cargo clippy --all-targets --all-features)

# Update VTES card data (downloads from krcg.org → engine/data/cards.json)
cards:
    uv run python scripts/update_cards.py

# Build GeoNames data (countries and cities)
build-geonames:
    uv run python backend/scripts/build_geonames.py

# Reset dev database (clears all data)
dev-reset:
    #!/usr/bin/env bash
    just dev-stop
    docker compose down -v

# Run E2E tests (Docker)
test-e2e:
    #!/usr/bin/env bash
    cleanup() {
        docker compose --profile test down
        echo "Test report: playwright-report/index.html"
    }
    trap cleanup EXIT
    docker compose --profile test up --build --abort-on-container-exit frontend-test

# Clean all build artifacts
clean:
    cd engine && cargo clean
    rm -rf frontend/dist frontend/node_modules engine/target
    find backend -type d -name __pycache__ -exec rm -rf {} +
