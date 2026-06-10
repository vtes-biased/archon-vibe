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
    # wasm-pack shells out to whatever `cargo`/`rustc` is first on PATH. If a
    # Homebrew rust is ahead of rustup's, it has no wasm32 target and the build
    # fails — so force rustup's toolchain (which has wasm32) to the front.
    export PATH="$HOME/.cargo/bin:$PATH"
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
    PYTHONUNBUFFERED=1 \
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
    # archon_engine (our PyO3 module) isn't a tracked dep, so `uv sync` above
    # prunes it — rebuild it into the venv so the env is complete after update.
    uv run maturin develop --manifest-path engine/Cargo.toml

# Run all tests
test:
    (cd engine && cargo test)
    just lint-check
    just test-backend
    (cd frontend && npx svelte-check --threshold error)

# Run backend tests (starts DB if needed, stops it after)
test-backend *ARGS='-v':
    #!/usr/bin/env bash
    set -e
    # Build the PyO3 engine into the venv — it's our own crate, not a tracked
    # dep, so nothing else installs it for a bare test run (incremental, cached).
    uv run maturin develop --manifest-path engine/Cargo.toml
    needs_stop=false
    if ! docker compose exec -T db pg_isready -U archon > /dev/null 2>&1; then
        echo "Starting database..."
        docker compose up -d db
        for i in {1..30}; do
            docker compose exec -T db pg_isready -U archon > /dev/null 2>&1 && break
            sleep 1
        done
        needs_stop=true
    fi
    uv run python3 -m pytest backend/tests/ {{ ARGS }}; rc=$?
    if $needs_stop; then docker compose stop db > /dev/null 2>&1; fi
    exit $rc

# Build production (Docker images)
build:
    #!/usr/bin/env bash
    set -e
    # Force rustup's toolchain (has wasm32) ahead of any Homebrew rust on PATH.
    export PATH="$HOME/.cargo/bin:$PATH"
    (cd engine && wasm-pack build --target web --release -- --features wasm)
    uv run maturin develop --release --manifest-path engine/Cargo.toml
    docker compose build

# ============================================================================
# Utility
# ============================================================================

# Check linting (no changes)
lint-check:
    uv run ruff check .
    uv run ruff format --check .
    (cd engine && cargo fmt --check && cargo clippy --all-targets --all-features -- -D warnings)

# Lint and auto-fix all code
lint:
    uv run ruff check --fix . && uv run ruff format .
    (cd engine && cargo fmt && cargo clippy --all-targets --all-features -- -D warnings)

# Update VTES card data (downloads from krcg.org → engine/data/cards.json)
cards:
    uv run python scripts/update_cards.py

# Build GeoNames data (countries and cities)
build-geonames:
    uv run python backend/scripts/build_geonames.py

# Provision the officials-contacts file for dev (decrypt the committed vault copy)
officials-dev:
    #!/usr/bin/env bash
    set -euo pipefail
    # The repo only ever holds the .vault ciphertext; decrypt it into the
    # gitignored runtime path the backend reads. Needs your ansible vault password
    # (ANSIBLE_VAULT_PASSWORD_FILE in your shell, or it prompts). The VEKN sync
    # then injects these contacts on its next run. mktemp+mv so a wrong password
    # doesn't clobber an existing copy.
    src=ansible/roles/fastapi_backend/files/officials_contacts.json.vault
    out=backend/src/data/officials_contacts.json
    tmp=$(mktemp)
    ansible-vault view "$src" > "$tmp"
    mv "$tmp" "$out"
    echo "Wrote $out (gitignored, dev only)"

# Reset dev database (clears all data)
dev-reset:
    #!/usr/bin/env bash
    just dev-stop
    docker compose down -v

# Run E2E tests (Docker, isolated compose project — teardown can't touch dev DB)
test-e2e:
    #!/usr/bin/env bash
    # Own compose project so volumes are project-name-prefixed: `down -v` here
    # only removes archon-vibe-e2e_* — never archon-vibe_postgres_data (dev DB).
    cleanup() {
        docker compose -p archon-vibe-e2e --profile test down -v >/dev/null 2>&1
        echo "Test report: playwright-report/index.html"
    }
    trap cleanup EXIT
    docker compose -p archon-vibe-e2e --profile test up --build \
        --abort-on-container-exit --exit-code-from frontend-test frontend-test

# release.yml runs e2e on the pushed tag and, only if green, creates the GitHub
# Release (which then triggers the artifact build).
#
# Cut a release: push a vX.Y.Z tag (e2e-gated; see release.yml)
release tag:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{ tag }}" in v*) ;; *) echo "tag must start with 'v' (e.g. v1.2.3)"; exit 1 ;; esac
    [ -z "$(git status --porcelain)" ] || { echo "working tree not clean — commit or stash first"; exit 1; }
    git rev-parse "{{ tag }}" >/dev/null 2>&1 && { echo "tag {{ tag }} already exists"; exit 1; }
    git tag "{{ tag }}"
    git push origin "{{ tag }}"
    echo "Pushed {{ tag }}. CI: e2e → (green) create release → artifacts. Watch the Actions tab."

# Clean all build artifacts
clean:
    cd engine && cargo clean
    rm -rf frontend/dist frontend/node_modules engine/target
    find backend -type d -name __pycache__ -exec rm -rf {} +
