# Task Tracking — pst

This repo tracks work in **pst** (`.pst/tickets`), not plan-mode plans or a `TODO.md`. The mechanics (read the board first, epic + `parent:#N` children, `wip`/`close` lifecycle, detail files, CLI-only writes) are auto-injected each session by the `.pst/mandate.md` SessionStart hook — `.pst/skill.md` has the full reference. Prefer pst over the harness Task tools.

**Committing pst changes.** Commit the board change *together with* the fix/feature it tracks (same commit closing the ticket), not as a separate `chore(pst)` commit — and stage **only the ticket lines you touched**, never the whole `.pst/tickets` file. The board is line-stable (the write rules never delete or reorder lines), so `wip`/`close` is an in-place one-line flip that forms its own isolated diff hunk. When the working tree holds other sessions' board edits, cherry-pick just your hunk: `git diff .pst/tickets`, filter to the hunk(s) mentioning your ticket, `git apply --cached`, then commit. This keeps unrelated ticket transitions out of your commit.

**Close on commit, not on deploy.** `close` a ticket in the same commit as the change that resolves it — do **not** hold it open waiting for the fix to be deployed or verified in production/beta. The board tracks what's *done in the tree*, not what's *live*. If a later deploy doesn't confirm the fix, `reopen` it. (So a deploy-bug fix lands closed even though a redeploy is still pending; the redeploy is itself tracked by the deploy/runbook ticket.)

**Committing agent memory.** Agent memory under `.claude/agent-memory/` is tracked in this repo (we commit memories, not gitignore them). When an agent writes or updates a memory file while working a task, commit those memory changes **bundled into the same commit as the work that produced them** — not a separate `chore` commit, not left dangling in the tree. Stage only the memory files your own agents touched this session (`git add .claude/agent-memory/<that-agent>/...`); leave other sessions' memory edits unstaged, same as the pst-hunk rule above. If the originating commit is already sealed (memory landed late), commit the memory on its own with a message naming the work it documents.

**Tags — priority only.** The sole tag axis is priority, one per ticket: `p1` (do it ASAP), `p2` (important), `p3` (nice-to-have, not urgent). Everything else — stack, kind, subsystem — goes in the ticket **body**, not as a tag (a label only earns a tag when you filter the board by it *and* it isn't already in the prose; only priority qualifies). There is no `deferred`/parked tag: anything on the board must be looked into, so `p3` is the floor, not a graveyard.

# Agent Workflow (PROACTIVE — do not wait for user to ask)

When implementing features or making significant changes, follow this pipeline using the Task tool:

1. **Before implementing**: Consult `product-manager` for VEKN rules, feature specs, UX requirements, or prioritization decisions. Always consult when domain context is needed.
2. **Before/during frontend work**: Consult `staff-frontend-engineer` for UX/UI review, component design, dependency evaluation, or mobile-first guidance.
3. **After significant code changes**: Launch `principal-engineer` to review architectural alignment — especially for changes touching sync, data model, Rust/WASM pipeline, or cross-module refactors.
4. **After any UI text change**: Launch `i18n-translator` to update all 5 locale files. Any new or modified user-facing string triggers this.
5. **After meaningful code changes**: Launch `documentalist` to update CLAUDE.md, ARCHITECTURE.md, SYNC.md, or other docs that are now stale.
6. **After major features or significant changes**: Launch `senior-qa` to run the test suite and assess whether new tests are warranted. Trigger for: new features touching core logic (tournament lifecycle, pairings, scoring), cross-stack changes (Rust/backend/frontend), refactors of critical paths (sync, reconciliation, access control). Skip for UI-only tweaks, copy changes, or styling.

Steps 3-6 should run in parallel when applicable. Skip agents only for trivial changes (typo fixes, single-line tweaks with no architectural or UI text impact).

# Project Guidelines

- Keep answers short and token efficient
- Prefer compact code and minimal changes
- Check assumptions in project code or web docs
- Use context7 MCP tools for external library/framework documentation (see CONTEXT7.md for library IDs)
- Challenge instructions when needed
- Follow frontend/DESIGN.md for UI styling guidelines
- **Component splitting**: When a Svelte page file exceeds ~1000 lines, extract logical sections into child components (e.g., `PlayerList.svelte`, `StandingsTable.svelte`). Pass data via props; keep state ownership in the parent. This keeps files navigable and editable by both humans and AI agents.
- **Offline-first reads**: All UI reads come from IndexedDB. The backend API is only for mutations (actions). SSE pushes data changes to IndexedDB per-user with role-appropriate data. No API GET calls for data display.
- **Packaged data files** (backend): load bundled data (JSON/SQL/xlsx under `backend/src/data/`) via `importlib.resources.files(__package__).joinpath(...).read_text()` — never `Path(__file__).parent`. `files()` resolves correctly when the backend runs as an installed wheel (CI artifact), not just from the source tree; `Path(__file__)` is the `#80`-class runtime-path bug. See `geonames.py`, `card_data.py`, `db.py` for the pattern.
- **Personal data / secrets are never committed** (the repo is public and CI publishes wheels as release assets). Don't bundle PII (e.g. scraped contact emails) into the package — it would ship inside the public wheel. Deliver it out of band: an `ansible-vault` file decrypted at deploy to a runtime path (env-pointed, e.g. `OFFICIALS_CONTACTS_FILE`), with an untracked dev copy and graceful absence. See `vekn_sync.py`'s officials-contacts loader.

## Working conventions

- **No red builds**: never report done over a failing build/test/lint — fix it or file a pst ticket. When touching build/packaging/test config, run the affected `just`/`make` targets and confirm green.
- **Minimal, meaningful tests**: default to zero new tests; add one only for a real regression with consequences — asserted at an interface, against the shipped artifact (import shared constants, never copy; no heavy mocks/seeds), one per invariant. Never encode engine-impossible states (VP sums = table size, 4–5-seat tables, stored `gw`/`tp` consistent with `compute_gw`/`compute_tp`).
- **Terse comments**: explain only the non-obvious (a why/gotcha/invariant) — never restate the code or narrate a change's history.
- **Locality over DRY**: prefer explicit, greppable local code over clever wrappers; dedup only large or fragile/hazardous duplication, not a few near-identical lines.
- **No pst numbers in commits or code**: never put `#N` / `pst #N` in commit messages or comments/docstrings (they clash with GitHub issue refs) — track linkage via the board; reference a `.pst/details/<slug>.md` path if needed.
- **Keep overview docs lean**: when an issue is fixed, remove its mention from the docs (don't annotate "Resolved") — resolution detail lives in the pst detail file.
- **Discuss before filing simplifications**: a simplify/refactor ticket is itself a decision — ground it in code and agree it *should* change before filing; cheap + isolated + useful features aren't simplification targets.
- **Context lives in-repo**: put durable project facts in the right doc (ARCHITECTURE/SYNC/PRODUCT/TOURNAMENTS, this file, agent definitions, `.pst/details/`), not in personal auto-memory. Agent memory under `.claude/agent-memory/` is the in-repo exception, for agent-specific traps.

# Architecture

Offline-first PWA. Keep deep design detail in the dedicated docs, not here:
**ARCHITECTURE.md** (full design and per-subsystem mechanics) and **SYNC.md**
(streaming, IndexedDB, access levels, and how to add an object type).

## Stack
- **Frontend**: Svelte + Vite + TypeScript, PWA (service workers), IndexedDB local storage
- **Backend**: Python FastAPI, PostgreSQL (JSONB), msgspec serialization
- **Bot**: Separate process — Discord bot (hikari + lightbulb + miru), pure OAuth client to backend, SQLite token/state storage
- **Shared**: Rust core (business logic) → WASM (frontend) + PyO3 (backend)

## Core model
- All objects extend `BaseObject` (`uid` UUID v7, `modified`, `deleted_at` soft-delete) and live in one unified `objects` table.
- Each row stores three pre-computed access projections — `public` / `member` / `full` — written at write time by `access_levels.py`. SSE reads the matching column directly; no per-viewer filtering at read time. (Levels and field visibility: SYNC.md.)
- **Synced types**: User, Sanction, Tournament, DeckObject, League (via SSE). VtesCard is static data loaded into IndexedDB.
- **Online**: action → Rust engine → PostgreSQL → CRUD event → SSE → IndexedDB → UI. **Offline**: tournament locks to one device, the WASM engine writes IndexedDB directly, and full state is pushed on go-online (server overwrites). No conflicts by construction (force-takeover / IC force-unlock are the escape hatches).
- **Mutations are optimistic**: WASM applies locally, the server request follows; on success SSE delivers authoritative state, on rejection the frontend rolls back (no API GET — reads stay offline-first).

## Key constraints
- Server always wins conflicts
- Each PWA keeps the full dataset in IndexedDB; SSE for real-time sync when online
- Rust ensures consistent business logic across the stack
