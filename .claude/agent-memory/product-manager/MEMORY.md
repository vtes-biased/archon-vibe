# Product Manager Memory

## Project Overview
- Archon: offline-first PWA for VTES tournament management + VEKN membership
- Primary user: tournament organizer on mobile, under time pressure
- Product document: `PRODUCT.md` (root) — comprehensive domain + product reference

## Key Files
- `PRODUCT.md` — Product reference (domain rules, user roles, features, constraints)
- `TOURNAMENTS.md` — Tournament system implementation details (state machine, scoring, seating)
- `ARCHITECTURE.md` — Tech architecture (offline-first, Rust/WASM/PyO3, SSE sync)
- `SYNC.md` — SSE streaming, IndexedDB, data levels
- `frontend/DESIGN.md` — UI guidelines (gothic theme, dark mode, mobile-first)
- `development-plan.md` — 12-phase roadmap (root)
- `reference/` — All official VEKN documents (tournament rules, judges guides v1+v2, ethics, game terms)

## Domain Rules That Drive Features
- Seating: No repeated predator-prey (mandatory), 9 optimization priorities
- Scoring: VP -> GW (>=2 VP + strictly highest) -> TP (position-based, ties average)
- VP validation: Must match physically possible oust order around table (ring algorithm)
- 4-player tables: TP positions are 1st/2nd/4th/5th (3rd is "table bye")
- Finals: Top 5 by GW>VP>TP, toss for ties, manual seating procedure
- Impossible player counts: 6, 7, 11
- Judges Guide v2 (2026): Adds "Standings Adjustment" penalty (-1 VP), removes "Game Loss"

## Agent Conventions
- Principal engineer: guards offline-first, Rust pipeline, data sync model
- Staff frontend engineer: mobile-first UX, self-discoverability, accessibility
- Documentalist: maintains CLAUDE.md, ARCHITECTURE.md, SYNC.md; trusts code over docs
- i18n translator: 5 languages (EN/FR/ES/PT-BR/IT), official VTES terminology from game_terms.json

## Product Decisions
- No explicit save buttons (auto-save pattern)
- Sanctions: Caution/Warning/SA/DQ implemented for in-tournament; Suspension/Probation for VEKN-wide
- Game Loss penalty deliberately excluded from app (deemed impractical by VEKN)
- All business logic in shared Rust engine (not Python or TypeScript)
- Server always wins conflicts in sync

## Phase Status (as of 2026-02-17)
- Phase 1 (Decklists): COMPLETE including TWDA integration (twda.py exists with GitHub App PR creation)
- Phase 2 (Leagues): COMPLETE
- Phase 3 (Sanctions Enhancement): COMPLETE (v2 categories, SA adjustments, DQ barring, lifting)
- Phase 4 (Ratings/Hall of Fame): COMPLETE (4-cat ratings, rankings page, HoF on rankings page, RP in PlayersTab)
- Phases 5-12: NOT STARTED
- Payment tracking: IMPLEMENTED (SetPaymentStatus action)
- Organizer management: IMPLEMENTED (add/remove co-organizers)
- iCal feed: IMPLEMENTED (backend/src/routes/calendar.py — personal + public feeds)
- Tournament list rework: IMPLEMENTED (My Agenda view)
- Staggered seating: IMPLEMENTED in engine (engine/src/seating.rs — 6/7/11 player counts)
- Drag-and-drop seating alteration: IMPLEMENTED (R1 enforcement, issue indicators)
- Social export: NOT IMPLEMENTED
- Printable seating/table labels: NOT IMPLEMENTED
- Round timer: NOT IMPLEMENTED
- QR check-in: NOT IMPLEMENTED
- VEKN results reporting (push): NOT IMPLEMENTED (pull/import exists via vekn_tournament_sync.py)
- Full offline mode (ownership model): NOT IMPLEMENTED

## Recently Shipped (Jan-Feb 2026)
- Drag-and-drop seating with per-player issue indicators + R1/live score guards
- Tournament organizer console mobile-first overhaul
- Tournament list rework with My Agenda view and iCal calendar feed
- Lucide-svelte icons (offline), IC organizer access, unified profiles
- Ratings UX (4 categories, date sort, bulk load), finalist bonus fix
- Sanctions full phase (SA, DQ barring, v2 categories, escalation)
- Leagues full phase, Payment tracking, Light theme
- Diacritics-insensitive search, Organizer management
- Parent league hierarchy UI

## Phase 2: Leagues — Key Decisions
- Standings modes: RTP, Score, GP
- Standings computed at read time via Rust engine (WASM frontend / PyO3 backend)
- League SSE is config only; standings derived client-side from IndexedDB tournaments
- Meta-leagues: 2-level hierarchy max
- `allow_no_finals` is a hint, not enforcement
