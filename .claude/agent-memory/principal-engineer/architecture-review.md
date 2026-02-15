# Architecture Review Notes (2026-02-14)

## Critical Issues
1. **Buffer drop on disconnect** (`sync.ts:213`): `flushAllBuffers()` is async, called without await in sync `disconnect()`. Data loss during SSE reconnection.
2. **In-memory auth stores** (`auth.py:66`): WebAuthn challenges, magic links, Discord states in Python dicts. Multi-worker and restart unsafe.
3. **JWT_SECRET default** (`auth.py:54`, `middleware/auth.py`): Falls back to known string. Must fail on startup in production.

## Important Issues
1. **Offline-first violations** (`api.ts:82-88, 330-333, 376-378`): `fetchUser`, `fetchTournament`, `getUserSanctionsApi` make API GET calls instead of reading IndexedDB.
2. **Deck logic in Python** (`tournaments.py:921-1102`): Upload/update/delete bypass Rust engine. Cannot work offline. Should be tournament events.
3. **Tournament hard-delete** vs soft-delete pattern. Special `tournament_delete` event in sync adds complexity.
4. **TournamentEventType incomplete** (`engine.ts:80-100`): Missing ~10 event types vs Rust enum. Optimistic updates silently fall back to server-only.
5. **Sanction.vp_adjustment missing** from TypeScript types.
6. **WASM/PyO3 duplication** (`lib.rs`): ~300 lines duplicated between wasm/python modules.
7. **Minimal test coverage**: 4 backend tests, 5 Rust tests. No SSE filtering tests (data leak risk).

## Suggestions
- CORS wildcard (dev-only concern)
- Broadcast injection pattern (works but implicit)
- No IndexedDB index on vekn_id (getUserByVeknId does full scan)
- Tournament page at 904 lines (approaching 1000-line split guideline)
- No service worker yet (needed for true offline)
- SQL table name in f-string in db.py stream_objects (safe today, fragile)
