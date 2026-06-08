# Documentalist Agent Memory

## Documentation Map
- `CLAUDE.md` — top-level project guidelines (lean; deep design lives in the docs below)
- `ARCHITECTURE.md` — full design + per-subsystem mechanics (data model, Rust integration, calendar, leagues, community links, Discord bot + linked roles, TWDA in/out)
- `SYNC.md` — SSE streaming, IndexedDB, access levels, "adding a new object type"
- `TOURNAMENTS.md` — single behavioral reference for the tournament domain: state machine, full event catalog (required state + permissions), scoring/oust-order, data model, permissions, SSE privacy. (Former `engine/TOURNAMENT.md` was deleted under pst #16 — it duplicated this doc and went stale; do not recreate an engine-side tournament behavior doc.)
- `engine/README.md` — engine build, bindings, module map + entry-point signatures (the engine *integration* reference, not behavior)
- `PRODUCT.md` — domain rules, roles, features, constraints
- `frontend/DESIGN.md` — UI styling guidelines
- `CONTEXT7.md` — library IDs for context7 MCP
- `TESTING.md` — E2E infra (global setup/teardown, auth + sync helpers, lifecycle test)
- `VEKN_SYNC.md` — VEKN external sync

## Working Principle
- **Trust code over docs.** Verify every claim against current source before writing it; many docs drift.
- **Keep ticket numbers out of the prose docs.** Don't add `pst #N` pointers to ARCHITECTURE.md/SYNC.md/TOURNAMENTS.md/etc. — tracking lives in pst, and stale numbers clash with GitHub issue refs. On fixing a tracked issue, **remove** any mention from ARCHITECTURE.md (don't annotate "Resolved"); resolution detail belongs in the pst detail file.

## Terminology (use consistently)
- Abbreviations: SSE, CRUD, PWA, WASM, PyO3, IC (Inner Circle), NC (National Coordinator), VEKN, VTES.
- Data model: `BaseObject` (uid/modified/deleted_at), always say **UUID v7** (not generic UUID), `deleted_at` = soft-delete timestamp, access **levels** = public/member/full.
- Synced object types: User, Sanction, Tournament, DeckObject, League (via SSE). VtesCard is static data. DeckObject is standalone (not embedded in Tournament).

## Which Docs Update Together
- New object type → ARCHITECTURE.md (data model) + SYNC.md ("adding a new object type") + maybe CLAUDE.md summary.
- Sync pattern change → SYNC.md (primary), ARCHITECTURE.md (only if fundamental).
- Rust engine capability change → ARCHITECTURE.md (Rust Integration) + TOURNAMENTS.md (if tournament-related) + engine/README.md.
- Architecture fact that affects mutations/reads → confirm CLAUDE.md's terse summary still matches (it intentionally stays high-level).

## Documented Invariants (verify before re-stating)
- Mutation pipeline: business event → Rust engine → CRUD → SSE → IndexedDB; ALL business events via `POST /{uid}/action` (no per-event REST routes). Optimistic: WASM first, server confirms via SSE.
- StartRound forwards WASM-computed seating into the server POST: WASM and PyO3 use separate RNGs, so the frontend injects its seating to keep optimistic + authoritative identical.
- Access filtering is write-time (precomputed public/member/full columns), not read-time per-viewer.
