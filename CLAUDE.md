# Task Tracking — pst

This repo tracks work in **pst** (`.pst/tickets`), not plan-mode plans or a `TODO.md`. The mechanics (read the board first, epic + `parent:#N` children, `wip`/`close` lifecycle, detail files, CLI-only writes) are auto-injected each session by the `.pst/mandate.md` SessionStart hook — `.pst/skill.md` has the full reference. Prefer pst over the harness Task tools.

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
