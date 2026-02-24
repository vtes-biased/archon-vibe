# SSE Sync Performance (2026-02)

## Original Problem
Initial SSE sync took 8-16s on localhost for ~20k users and ~10k tournaments.
(Non-authenticated users only see ~500 users: NC/Prince officials.)

## What Was Fixed

### 1. Double serialization (was ~50% of time) — FIXED
Old: `PG JSONB -> dict -> JSON -> msgspec Struct -> to_builtins -> dict -> JSON`
New: `stream_objects_new()` uses `SELECT col::text` to get raw JSON strings, passes them through to SSE directly. No parse/reserialize cycle.

### 2. Tournament filter Struct creation (was ~15%) — FIXED
`_filter_tournament()` no longer exists. Access-level filtering is now done at write time via pre-computed JSONB columns (public/member/full).

### 3. Pool size — FIXED
`max_size=20` (was 10).

### 4. SSE connection duplication — FIXED
`+layout.svelte` owns connect/disconnect/reconnect. Components only listen for events via addEventListener.

## Resolved (no remaining issues)
- Frontend buffering concern is moot: snapshot loads directly into IDB, SSE catch-up is small
- Batch saves use simple single-transaction writes (data already in memory from snapshot/buffer, chunking adds overhead for no benefit)
