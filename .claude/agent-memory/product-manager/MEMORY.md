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
- Sanctions: Caution/Warning/DQ in current system; Standings Adjustment planned for v2
- Game Loss penalty deliberately excluded from app (deemed impractical by VEKN)
- All business logic in shared Rust engine (not Python or TypeScript)
- Server always wins conflicts in sync

## Phase Status (as of 2026-02-15)
- Phase 1 (Decklists): COMPLETE except TWDA integration (1.6)
- Phase 2 (Leagues): COMPLETE — model, API, SSE, frontend, Rust standings engine
- Phase 3 (Sanctions Enhancement): NOT STARTED
- Phase 4 (Ratings/Hall of Fame): NOT STARTED (ratings engine works, visibility missing)
- Phases 5-12: NOT STARTED
- HIGH-priority standalone items (from PRODUCT.md 5.2): payment tracking, iCal feed, social export

## Phase 2: Leagues — Key Decisions
- See `leagues-design.md` for full design notes
- Standings modes: RTP, Score, GP
- Standings computed at read time via Rust engine (WASM frontend / PyO3 backend)
- League SSE is config only; standings derived client-side from IndexedDB tournaments
- Meta-leagues: 2-level hierarchy max
- `allow_no_finals` is a hint, not enforcement

Notes:
- Legacy archon league code at `/Users/lionelpanhaleux/dev/perso/archon/src/archon/db.py` lines 1403-1509
- Legacy models at `/Users/lionelpanhaleux/dev/perso/archon/src/archon/models.py` lines 75-84, 228-232, 301-420
