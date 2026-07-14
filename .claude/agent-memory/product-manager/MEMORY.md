# Product Manager Memory

## Project Overview
- Archon: offline-first PWA for VTES tournament management + VEKN membership
- Primary user: tournament organizer on mobile, under time pressure
- `PRODUCT.md` (root) is the comprehensive domain + product reference; planned/outstanding work is tracked in pst tickets.

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
- Standings modes: RTP, Score, GP (GP is an app house rule, not VEKN — see PRODUCT.md Leagues).
- Standings computed at read time via the Rust engine (WASM frontend / PyO3 backend); league SSE payload is **config only**, standings derived client-side from IndexedDB tournaments.
- Meta-leagues: 2-level hierarchy max. (`allow_no_finals` was a dead never-wired field — removed 2026-07.)

## Roadmap Status (as of 2026-06)
Core features have shipped; `PRODUCT.md` + pst tickets are the source of truth — don't re-track shipped features here. Still outstanding / forward-looking:
- Discord tournament bot — partially built (slash commands + SSE listener exist), not finished.
- VEKN venue import. (Table labels shipped as table rooms; Pretix rejected 2026-07 — payments stay deliberately status-only, see PRODUCT.md §5 Payments.)

## Agent Conventions
- Principal engineer: guards offline-first, Rust pipeline, data sync model.
- Staff frontend engineer: mobile-first UX, self-discoverability, accessibility.
- Documentalist: maintains CLAUDE.md/ARCHITECTURE.md/SYNC.md; trusts code over docs.
- i18n translator: 5 languages (EN/FR/ES/PT-BR/IT), official VTES terminology from game_terms.json.

## Memory Files
- Published standings = GW/VP/TP competition-ranking w/ skips; toss is top-5-cutoff-only — see PRODUCT.md (§3.5).
- GP league points (established convention, NOT to be framed as "house rule" — the app is VEKN-official; merely not a hard VEKN tournament rule; ties best-position+skip; position=final placement) — see PRODUCT.md (Leagues).
- [VEKN ID detach policy](project_vekn_id_detach_policy.md) — what stays with the VEKN ID vs follows the human on abandon/displace/merge; self-abandon blocked while suspended.
- [Account-surgery regression watch-list](project_vekn_account_surgery_bugs.md) — the merge/detach defect classes (fixed); check none return when touching that code.
- TWDA designer-credit convention (Created by:, anonymity=omit, names-only) — see ARCHITECTURE.md (TWDA Outbound).
- [Sponsor (coopted_by) visibility](project_vekn_sponsor_visibility.md) — full-projection-only, but the SSE personal overlay already delivers it to IC/NC/Prince/self, so surfacing is frontend-only (presence = permission); detail-view + own-profile, never a list column; p3.
- [Seating alteration validation](project_seating_alteration_validation.md) — hard-block <4/>5/empty tables on save, warn-only on pred-prey repeats, add-table belongs in the edit-seating draft.
- [max_rounds vs VEKN push](project_max_rounds_vekn_push.md) — max_rounds = one per-player-cap concept, IS pushed to VEKN (VEKN build requires it); only self_organized_rounds is never-pushed; disabled toggle = frozen-after-start/push, not mutual exclusion.
