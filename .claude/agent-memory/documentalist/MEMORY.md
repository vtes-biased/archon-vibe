# Documentalist Agent Memory

## Documentation File Locations

- `/Users/lionelpanhaleux/dev/perso/archon-cursor/CLAUDE.md` — Top-level project guidelines
- `/Users/lionelpanhaleux/dev/perso/archon-cursor/ARCHITECTURE.md` — Detailed architecture
- `/Users/lionelpanhaleux/dev/perso/archon-cursor/SYNC.md` — SSE sync patterns
- `/Users/lionelpanhaleux/dev/perso/archon-cursor/CONTEXT7.md` — Library IDs for context7 MCP
- `/Users/lionelpanhaleux/dev/perso/archon-cursor/frontend/DESIGN.md` — UI styling guidelines
- `/Users/lionelpanhaleux/dev/perso/archon-cursor/TOURNAMENTS.md` — Tournament system details
- `/Users/lionelpanhaleux/dev/perso/archon-cursor/VEKN_SYNC.md` — VEKN external sync
- `/Users/lionelpanhaleux/dev/perso/archon-cursor/TESTING.md` — Testing guidelines

## Documentation Cross-References

**CLAUDE.md** references:
- ARCHITECTURE.md for architecture details
- SYNC.md for sync implementation
- CONTEXT7.md for library IDs
- frontend/DESIGN.md for UI guidelines

**ARCHITECTURE.md** references:
- TOURNAMENTS.md for tournament event processing examples

**SYNC.md** provides:
- Implementation details for patterns described in ARCHITECTURE.md
- Adding new object types (referenced from CLAUDE.md)

## Key Terminology Conventions

**Abbreviations used consistently:**
- SSE — Server-Sent Events
- CRUD — Create/Read/Update/Delete
- PWA — Progressive Web App
- WASM — WebAssembly
- PyO3 — Rust-Python bindings
- IC — Inner Circle (VEKN role)
- NC — National Coordinator (VEKN role)
- VEKN — Vampire: Elder Kindred Network
- VTES — Vampire: The Eternal Struggle

**Data model terms:**
- `BaseObject` — Base class with uid/modified/deleted_at
- UUID v7 — Time-ordered UUID (always specify v7, not generic UUID)
- `deleted_at` — Soft-delete timestamp (nullable)
- Data levels — public/member/full (access control tiers)

## Architecture Patterns Documented

**Mutation Pipeline:**
- Business events → Rust engine → CRUD events → SSE → IndexedDB
- ALL business events go through `POST /{uid}/action`
- NO separate REST endpoints per event type
- Optimistic updates: WASM processes first → server confirms via SSE

**Sync Patterns:**
- Generic `stream_objects()` using keyset pagination (not server-side cursors)
- Spec-based buffers in frontend (SPECS array in sync.ts)
- Per-type filter functions (`_filter_user`, `_filter_tournament`, `_filter_league`, etc.)

**Object Types:**
- User, Sanction, Tournament, Rating, League (synced via SSE)
- VtesCard (static data, loaded into IndexedDB)
- Deck (embedded in Tournament, not standalone)

## Files That Update Together

When adding a new object type:
1. ARCHITECTURE.md — Data model section
2. SYNC.md — "Adding a New Object Type" section
3. CLAUDE.md — May need architecture summary update

When sync patterns change:
1. SYNC.md — Primary update
2. ARCHITECTURE.md — If fundamental pattern changes

When Rust engine capabilities change:
1. ARCHITECTURE.md — Rust Integration section
2. TOURNAMENTS.md — If tournament-related

## Recent Changes

**Session 2026-02-16: Calendar System, Tournament List Rework**
- ARCHITECTURE.md: added Calendar System section documenting iCal feed endpoint, calendar token, agenda matching, frontend integration
- SYNC.md: documented `calendar_token` stripped from `_filter_user()` in Per-Type Filtering section
- New backend endpoint: `GET /api/calendar/tournaments.ics` with personal/country/global feed types
- `calendar_token` field on User model (nullable, generated on demand via `POST /auth/me/calendar-token`)
- Frontend: `getAgendaTournaments()` and simplified `getFilteredTournaments()` in db.ts
- Tournament list: removed sort/state dropdowns, added "My Agenda" toggle for members, "Include online" toggle
- Continent helpers: `getContinent()` / `getCountriesOnContinent()` in frontend/backend geonames

**Session 2026-02-15: League system, keyset pagination, i18n**
- Added League object type (full SSE sync support)
- ARCHITECTURE.md: added League System section
- SYNC.md: updated all stream_specs, SPECS arrays, IndexedDB table to include leagues
- ARCHITECTURE.md: added i18n section documenting Paraglide JS (5 locales: en/fr/es/pt/it)
- SYNC.md: documented keyset pagination replacing server-side cursors
- CLAUDE.md: added Object Types list to data model section

**Session 2026-02-13: Cards/Deck Support**
- CLAUDE.md updated: added card/deck mention to data model section
- ARCHITECTURE.md updated: added Card/Deck System section, documented cards store in IndexedDB
- Verified implementation: cards.rs in engine, VtesCard in types.ts, cards store in db.ts

**BaseObject Pattern:**
- Confirmed `deleted_at` is part of BaseObject (was already documented correctly)
- Updated ARCHITECTURE.md to explicitly list deleted_at in Object Structure section

**Session 2026-02-16: Icon library migration (@iconify/svelte → lucide-svelte)**
- Replaced @iconify/svelte (runtime icon fetching from api.iconify.design) with lucide-svelte (tree-shaken, build-time bundled)
- Updated staff-frontend-engineer MEMORY.md stack dependencies (line 9)
- Reason: offline-first PWA requirement — runtime icon fetching breaks offline mode
- lucide-svelte provides ~2000+ SVG icons, auto tree-shakes unused icons during build
- New DiscordIcon.svelte component created for Discord logo (not available in lucide)
- No updates needed to CLAUDE.md, ARCHITECTURE.md, CONTEXT7.md, or frontend/DESIGN.md (icons not a documented architecture concern)
