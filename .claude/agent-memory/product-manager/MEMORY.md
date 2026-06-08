# Product Manager Memory

## Project Overview
- Archon: offline-first PWA for VTES tournament management + VEKN membership
- Primary user: tournament organizer on mobile, under time pressure
- `PRODUCT.md` (root) is the comprehensive domain + product reference; `development-plan.md` is the 12-phase roadmap.

## Key Reference Docs
- `PRODUCT.md` — domain rules, user roles, features, constraints
- `TOURNAMENTS.md` — tournament state machine, scoring, seating
- `ARCHITECTURE.md` / `SYNC.md` — tech architecture, offline-first, sync
- `frontend/DESIGN.md` — UI guidelines (gothic theme, dark-first, mobile-first)
- `reference/` — official VEKN documents (tournament rules, judges guides v1+v2, ethics, game terms)

## Domain Rules That Drive Features
- Seating: no repeated predator-prey (mandatory); 9 optimization priorities.
- Scoring: VP → GW (≥2 VP AND strictly highest) → TP (position-based, ties average).
- VP validation: must match a physically possible oust order around the table (ring algorithm).
- 4-player tables: TP positions are 1st/2nd/4th/5th (3rd is a "table bye").
- Finals: top 5 by GW>VP>TP, random toss only for the cutoff tie, manual seating procedure.
- Impossible player counts: 6, 7, 11 (engine uses staggered seating for these).
- Judges Guide v2 (2026): adds "Standings Adjustment" penalty (−1 VP), removes "Game Loss".

## Product Decisions (durable)
- No explicit save buttons — auto-save pattern throughout.
- Sanctions: Caution/Warning/SA/DQ for in-tournament; Suspension/Probation for VEKN-wide.
- Game Loss penalty deliberately excluded (deemed impractical by VEKN).
- All business logic in the shared Rust engine (not Python or TypeScript).
- Server always wins sync conflicts.

## Leagues — Key Decisions
- Standings modes: RTP, Score, GP (GP is an app house rule, not VEKN — see [GP league points](project_vekn_gp_league_points.md)).
- Standings computed at read time via the Rust engine (WASM frontend / PyO3 backend); league SSE payload is **config only**, standings derived client-side from IndexedDB tournaments.
- Meta-leagues: 2-level hierarchy max. `allow_no_finals` is a hint, not enforcement.

## Roadmap Status (as of 2026-06)
Most of phases 1–11 have shipped (decklists+TWDA, leagues, sanctions v2, ratings/HoF, QR check-in, online features, offline mode, help/docs, ratings push to VEKN). Treat `development-plan.md` + `PRODUCT.md` as the source of truth; don't re-track shipped features here. **Still outstanding / forward-looking:**
- Phase 12 Discord tournament bot — partially built (slash commands + SSE listener exist), not a finished phase.
- Table labels (phase 7 remainder), Pretix integration (phase 9 remainder), VEKN venue import (phase 10 remainder).

## Agent Conventions
- Principal engineer: guards offline-first, Rust pipeline, data sync model.
- Staff frontend engineer: mobile-first UX, self-discoverability, accessibility.
- Documentalist: maintains CLAUDE.md/ARCHITECTURE.md/SYNC.md; trusts code over docs.
- i18n translator: 5 languages (EN/FR/ES/PT-BR/IT), official VTES terminology from game_terms.json.

## Memory Files
- [VEKN standings & toss scope](project_vekn_standings_toss_scope.md) — published rank = gw,vp,tp with skips; toss is cutoff-only, never a general tiebreak.
- [VEKN GP league points](project_vekn_gp_league_points.md) — GP house rule; ties use best-position+skip; GP position must be FINAL placement, not prelim order.
- [VEKN ID detach policy](project_vekn_id_detach_policy.md) — what stays with the VEKN ID vs follows the human on abandon/displace/merge; self-abandon blocked while suspended.
- [Account-surgery regression watch-list](project_vekn_account_surgery_bugs.md) — the merge/detach defect classes #59/#65/#78 fixed; check none return when touching that code.
- [TWDA designer credit](project_twda_designer_credit.md) — `Created by:` label, anonymity = omit the line (no "Anonymous" string), names only no VEKN ids, winner always in header.
