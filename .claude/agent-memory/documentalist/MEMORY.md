# Documentalist Agent Memory

## Documentation Map
- `CLAUDE.md` — top-level project guidelines (lean; deep design lives in the docs below)
- `ARCHITECTURE.md` — full design + per-subsystem mechanics (data model, Rust integration, calendar, leagues, community links, Discord bot + linked roles, TWDA in/out)
- `SYNC.md` — SSE streaming, IndexedDB, access levels, "adding a new object type"
- `TOURNAMENTS.md` — tournament state machine, scoring, seating
- `engine/TOURNAMENT.md` — engine-side tournament reference (**known stale, pst #16** — don't trust without checking code)
- `engine/README.md` — engine module + permissions reference
- `PRODUCT.md` — domain rules, roles, features, constraints
- `frontend/DESIGN.md` — UI styling guidelines
- `CONTEXT7.md` — library IDs for context7 MCP
- `TESTING.md` — E2E infra (global setup/teardown, auth + sync helpers, lifecycle test)
- `VEKN_SYNC.md` — VEKN external sync

## Working Principle
- **Trust code over docs.** Verify every claim against current source before writing it; many docs drift.
- Per project convention, several docs carry inline `pst #N` pointers next to known-issue scopes — when code in that scope changes, update the referenced ticket (and add a pointer when recording a new scoped issue).
- On fixing a tracked issue, **remove** its mention from ARCHITECTURE.md (don't annotate "Resolved"); resolution detail belongs in the pst detail file.

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
