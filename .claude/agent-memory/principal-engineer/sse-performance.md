# SSE Sync Performance (2026-02)

## Original Problem
Initial SSE sync took 8-16s on localhost for ~500 users and ~10k tournaments.

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

## Remaining Issues

### Frontend buffers until sync_complete
All data buffered in JS arrays until `sync_complete` event, then flushed to IndexedDB in one batch. No progressive rendering during sync.
