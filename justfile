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
    for port in 8000 8001 5173; do
        pid=$(lsof -ti :$port 2>/dev/null) && kill -9 $pid 2>/dev/null && echo "Killed process on port $port" || true
    done
    docker compose stop db 2>/dev/null || true
    rm -f backend.log frontend.log public-api.log

# Start the public read-only API against the dev database (wiki/public-api.md).
# Its own process by design — `just dev` does not start it.
dev-api:
    #!/usr/bin/env bash
    set -e
    DATABASE_URL=postgresql://archon:archon_dev_password@localhost:5433/archon \
    PYTHONUNBUFFERED=1 \
    nohup uv run uvicorn backend.src.public_api.main:app --reload --reload-dir backend/src/public_api --host :: --port 8001 > public-api.log 2>&1 &
    echo "Public API started (PID: $!) on http://localhost:8001/docs. Logs: public-api.log"

# Update the toolchains AND all dependencies to latest versions. Semver-major
# dependency bumps stay manual by design (an unreviewed major can break the
# build) — the closing deps-check report lists what remains.
update:
    #!/usr/bin/env bash
    set -euo pipefail
    # Toolchains first: deps can only be as fresh as the tools resolving them.
    rustup update
    # uv: brew-managed here (`uv self update` refuses on brew installs); try
    # brew first, fall back to the standalone self-updater.
    brew upgrade uv 2>/dev/null || uv self update 2>/dev/null || true
    npm install -g npm >/dev/null 2>&1 || echo "npm self-update failed (non-fatal)"
    cargo install wasm-pack
    uv lock --upgrade && uv sync
    (cd frontend && npm update)
    (cd engine && cargo update)
    # archon_engine (our PyO3 module) isn't a tracked dep, so `uv sync` above
    # prunes it — rebuild it into the venv so the env is complete after update.
    uv run maturin develop --manifest-path engine/Cargo.toml
    just hooks   # ensure the pre-commit hook is installed (idempotent symlink refresh)
    just -q deps-check || true   # report what stayed manual (semver-major bumps)

# Exits non-zero if any ecosystem has updates available — used to gate `just release`.
# Report whether `just update` would pull newer deps (read-only; no lockfile writes).
deps-check:
    #!/usr/bin/env bash
    set -uo pipefail   # not -e: run all three probes, then aggregate
    stale=0
    echo "Dependency freshness (read-only; per-ecosystem deps, not the tools themselves):"
    # Python/uv: `uv lock --upgrade --dry-run` reports what `just update` WOULD change
    # (within constraints) — unlike `uv tree --outdated`, which flags transitive deps
    # that are pinned by their parents and thus unreachable. Prints "No lockfile
    # changes detected" when nothing would move.
    if out=$(uv lock --upgrade --dry-run 2>&1); then
        if printf '%s\n' "$out" | grep -q 'No lockfile changes detected'; then
            echo "  python deps (uv)     current"
        else
            stale=1; echo "  python deps (uv)     updates available:"
            printf '%s\n' "$out" | grep -vE '^[[:space:]]*$|Resolved ' | sed 's/^/      /'
        fi
    else echo "  python deps (uv)     (could not check)"; fi
    # Frontend/npm: `npm outdated` exits non-zero when a package is upgradable.
    # Frontend/npm: stale only when `npm update` would move something (current
    # != wanted) — this gate's stated intent. Beyond-Wanted semver-majors are
    # manual-or-blocked-upstream (e.g. typescript 7 vs the SvelteKit peer cap):
    # reported informationally, never gating.
    npmrep=$(cd frontend && npm outdated --json 2>/dev/null | node -e '
        let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{
          const o=s.trim()?JSON.parse(s):{};
          for(const [k,v] of Object.entries(o)){
            if(v.current!==v.wanted)console.log(`TAKE ${k} ${v.current} -> ${v.wanted}`);
            else if(v.wanted!==v.latest)console.log(`INFO ${k} ${v.current} (latest ${v.latest}: semver-major, manual bump)`);
          }});') || true
    if printf '%s\n' "$npmrep" | grep -q '^TAKE '; then
        stale=1; echo "  frontend deps (npm)  updates available:"
        printf '%s\n' "$npmrep" | grep '^TAKE ' | sed 's/^TAKE /      /'
    else
        echo "  frontend deps (npm)  current (within ranges)"
    fi
    printf '%s\n' "$npmrep" | grep '^INFO ' | sed 's/^INFO /      /' || true
    # Engine/cargo: `cargo update --dry-run` prints "name vX -> vY" without writing.
    if out=$(cd engine && cargo update --dry-run 2>&1); then
        if printf '%s\n' "$out" | grep -q ' -> '; then
            stale=1; echo "  engine deps (cargo)  updates available:"
            printf '%s\n' "$out" | grep ' -> ' | sed 's/^/      /'
        else echo "  engine deps (cargo)  current"; fi
    else echo "  engine deps (cargo)  (could not check)"; fi
    exit "$stale"

# Run all tests
test:
    (cd engine && cargo test)
    just lint-check
    just test-backend
    (cd frontend && npm run check -- --threshold error)

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

# ============================================================================
# Utility
# ============================================================================

# Check linting (no changes)
lint-check:
    uv run ruff check .
    uv run ruff format --check .
    (cd engine && cargo fmt --check && cargo clippy --all-targets --all-features -- -D warnings)
    just permission-drift
    just comment-blocks
    just dark-variant
    just fold-grammar
    just locale-parity
    just public-api-isolation
    just event-run-coverage
    just model-drift
    just migration-pairing
    just help-mockups

# Fail when a role literal is used for gating outside the engine's capability
# table — the drift this repo's permission model keeps re-growing without it.
permission-drift:
    uv run python3 scripts/check_permission_drift.py

# Fail on a contiguous inline comment block over three lines — the bloat a
# review pass keeps having to delete by hand.
comment-blocks:
    uv run python3 scripts/check_comment_blocks.py

# Fail on Tailwind's `dark:` variant, which follows the OS preference rather than
# the theme the user picked and so inverts the wrong way for anyone whose two
# disagree.
dark-variant:
    uv run python3 scripts/check_dark_variant.py

# Fail when a disclosure is drawn outside `FoldableSection` — the app's one fold
# grammar, whose exceptions are listed in the script and in wiki/design.md.
fold-grammar:
    uv run python3 scripts/check_fold_grammar.py

# Fail when a locale's message catalog disagrees with the base one — Paraglide
# falls back silently, so a forgotten translation ships as English with no error.
locale-parity:
    uv run python3 scripts/check_locale_parity.py

# Fail when the app names the public API, or the public API imports the app's
# engine, scheduler, SSE or connection pool — the separation is the whole design.
public-api-isolation:
    uv run python3 scripts/check_public_api_isolation.py

# Fail when the public API's Member API section and the app's
# `event:run` allowlist disagree — the listing is the published boundary.
event-run-coverage:
    uv run python3 scripts/check_event_run_coverage.py

# Fail when models.py and types.ts disagree on a field name or an enum value —
# nothing generates one from the other, so a one-sided change ships silently.
model-drift:
    uv run python3 scripts/check_model_drift.py

# Fail when a stored-value migration has no proof section in wiki/post-deploy.md,
# or a section proves an entry that no longer exists — the pairing is what makes
# an entry die in the commit that retires its proof.
migration-pairing:
    uv run python3 scripts/check_migration_pairing.py

# Fail when a help-guide mockup hand-rolls a Button/Badge or hard-codes a live UI
# label — the drawings of the console rot silently as the real screens move.
help-mockups:
    uv run python3 scripts/check_help_mockups.py

# Lint and auto-fix all code
lint:
    uv run ruff check --fix . && uv run ruff format .
    (cd engine && cargo fmt && cargo clippy --all-targets --all-features -- -D warnings)
    @just _backup-drift
    just permission-drift
    just comment-blocks
    just dark-variant
    just fold-grammar
    just locale-parity
    just public-api-isolation
    just event-run-coverage
    just model-drift
    just migration-pairing
    just help-mockups

# Warn (never fail) when the hand-synced backup scripts drift from server-setup's
# copies (script headers document the contract). Comment wording and the
# documented createdb encoding divergence are sanctioned; anything else warns.
# The upstream checkout lands via the ansible justfile's `galaxy` recipe.
_backup-drift:
    #!/usr/bin/env bash
    up=ansible/galaxy_collections/server-setup/files
    ours=ansible/roles/db_backup/files
    [ -d "$up" ] || { echo "backup-drift: no server-setup checkout (cd ansible && just galaxy) — check skipped"; exit 0; }
    for s in pg-backup.sh pg-backup-check.sh; do
        if diff <(grep -vE '^[[:space:]]*(#|$)' "$up/$s") <(grep -vE '^[[:space:]]*(#|$)' "$ours/$s") | grep '^[<>]' | grep -vq createdb; then
            echo "⚠️  WARNING: $s drifted from server-setup files/$s — resync or document the divergence in its header"
        fi
    done

# Install git hooks (pre-commit: ruff auto-format of staged Python)
hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    src="$(git rev-parse --show-toplevel)/.githooks/pre-commit"
    dst="$(git rev-parse --git-path hooks)/pre-commit"   # worktree-safe, not hard-coded .git/hooks
    ln -sf "$src" "$dst"
    echo "Installed $dst -> $src"

# Update VTES card data (downloads from krcg.org → engine/data/cards.json)
cards:
    uv run python scripts/update_cards.py

# Build GeoNames data (countries and cities)
build-geonames:
    uv run python backend/scripts/build_geonames.py

# Generate a VAPID keypair for Web Push (#314). One per env; store the private key in
# ansible-vault, never commit it. Rotating invalidates all existing subscriptions.
vapid-keys:
    uv run python backend/scripts/gen_vapid_keys.py

# Generate the Ed25519 JWT signing keypair. One per env; the private key is the app's
# alone (ansible-vault), the public key goes to every verifier.
jwt-keys:
    uv run python backend/scripts/gen_jwt_keys.py

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

# Smoke-test the PRODUCTION frontend build — catches prod-build-only breakage the
# dev-server e2e misses (asset paths, SPA fallback, WASM, API base). No backend
# needed; mirrors CI's frontend-build job.
test-smoke:
    #!/usr/bin/env bash
    set -e
    (cd engine && wasm-pack build --target web --release -- --features wasm)
    cd frontend
    VITE_API_URL="" npm run build
    npm run test:smoke

# release.yml runs e2e on the pushed tag and, only if green, creates the GitHub
# Release, then builds + attaches the artifacts in the same run. Examples:
#   just release patch   # v0.1.10 -> v0.1.11
#   just release minor   # v0.1.10 -> v0.2.0
#   just release major   # v0.1.10 -> v1.0.0
#   just release v1.2.3  # or an explicit tag
# The tag is the single source of truth for the backend/bot/frontend versions:
# hatch-vcs stamps the wheels from it; CI passes it to the frontend build. The
# Rust engine is the exception — its version is bumped by hand in engine/Cargo.toml
# + engine/pyproject.toml when the engine changes, independent of the release tag.
# Cut a release: bump type (patch/minor/major) or explicit vX.Y.Z (e2e-gated)
release bump:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -z "$(git status --porcelain)" ] || { echo "working tree not clean — commit or stash first"; exit 1; }
    latest=$(git tag --list 'v*' --sort=-v:refname | head -n1)
    case "{{ bump }}" in
        patch|minor|major)
            IFS=. read -r ma mi pa <<<"${latest:-v0.0.0}"; ma=${ma#v}
            case "{{ bump }}" in
                patch) pa=$((pa + 1)) ;;
                minor) mi=$((mi + 1)); pa=0 ;;
                major) ma=$((ma + 1)); mi=0; pa=0 ;;
            esac
            tag="v${ma}.${mi}.${pa}"
            ;;
        v*.*.*) tag="{{ bump }}" ;;
        *) echo "usage: just release <patch|minor|major|vX.Y.Z>"; exit 1 ;;
    esac
    git rev-parse "$tag" >/dev/null 2>&1 && { echo "tag $tag already exists"; exit 1; }
    # Nudges: discourage (but don't block) releasing on stale deps or with no notes
    # written. `if` keeps set -e from aborting.
    anyway=""
    if ! just deps-check 2>/dev/null; then   # 2>/dev/null: drop just's "recipe failed" wrapper line
        echo "⚠ Dependencies are out of date — prefer 'just update' before cutting a release."
        anyway=" anyway"
    fi
    if ! grep -q '^## Unreleased$' CHANGELOG.md; then
        echo "⚠ No '## Unreleased' section in CHANGELOG.md — run /changeset first, or this release ships unannounced."
        anyway=" anyway"
    fi
    read -r -p "Release $tag${anyway} (latest is ${latest:-none})? [y/N] " ans
    [ "$ans" = y ] || [ "$ans" = Y ] || { echo "aborted"; exit 1; }
    if grep -q '^## Unreleased$' CHANGELOG.md; then
        stamp="## $tag — $(date +%F)"
        # Must match ENTRY_HEADING in frontend/src/lib/changelog.ts, or the app skips the
        # entry and shows nothing, silently — reachable via a pre-release tag like v1.2.3-rc1.
        printf '%s' "$stamp" | grep -qE '^## v[0-9]+\.[0-9]+\.[0-9]+ — [0-9]{4}-[0-9]{2}-[0-9]{2}$' \
            || { echo "$tag would stamp a heading the app cannot parse"; exit 1; }
        uv run python3 -c "import pathlib, re, sys; p = pathlib.Path('CHANGELOG.md'); p.write_text(re.sub(r'(?m)^## Unreleased$', lambda m: sys.argv[1], p.read_text(), count=1))" "$stamp"
        git add CHANGELOG.md
        git commit -m "Stamp $tag in the changelog"
        git push origin HEAD
    fi
    git tag "$tag"
    git push origin "$tag"
    echo "Pushed $tag. CI: e2e → (green) create release → artifacts. Watch the Actions tab."

# Clean all build artifacts
clean:
    cd engine && cargo clean
    rm -rf frontend/dist frontend/node_modules engine/target
    find backend -type d -name __pycache__ -exec rm -rf {} +
