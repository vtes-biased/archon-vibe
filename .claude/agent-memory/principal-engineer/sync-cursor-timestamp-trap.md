---
name: sync-cursor-timestamp-trap
description: The objects table has TWO distinct timestamps (column modified_at vs JSONB modified) that diverge in value AND string format — mixing them in the SSE since-cursor silently skips events
metadata:
  type: project
---

The `objects` table carries two different "modified" timestamps that are easy to conflate and dangerous to mix in the SSE `since` cursor logic.

- **`objects.modified_at`** — the DB **column**, set by trigger `objects_modified_trigger` (`backend/src/db.py:283-298`) to `CURRENT_TIMESTAMP` on every write. Emitted via psycopg `.isoformat()` → **naive**, no suffix (e.g. `2026-06-03T12:30:45.123456`). This is the authoritative cursor for: the `since` filter (`db.py:541` `WHERE modified_at > %s`), the `sync_complete` timestamp (`db.py:556` `rows[-1][1].isoformat()`), and snapshot meta (`backend/src/snapshots.py:82-90`).
- **`modified`** — a field **inside** the model / JSONB `full` payload, set in app code via `datetime.now(UTC)` (e.g. `db.py:1180`). msgspec serializes it as RFC3339 UTC with a `Z`/`+00:00` suffix (e.g. `2026-06-03T12:30:45.123456Z`). This is what the frontend sees as `item.modified` on a live SSE single-event.

Two divergences, both silent-and-catastrophic per the sync pillar:
1. **Value**: trigger-clock vs app-clock are written at different instants; not equal. Using one as a `since` cursor against the other can skip events (`modified > modified_at` for the same row → next reconnect's `modified_at > cursor` filter excludes it).
2. **Format**: lexically `"...Z" > "...+00:00" > "...<naive>"` are all true for the same instant. A `>` string-comparison monotonic guard seeded from a naive value and advanced with a `Z` value will mis-order, wedge, or jump.

**Why:** discovered reviewing pst #6 (frontend sync high-water-mark cursor), which advanced the persisted `since` cursor from `item.modified` (JSONB) while every server consumer filters on `modified_at` (column). See [[p1-sync-fixes-review-2026-06]].

**How to apply:** Any cursor/`since`/high-water-mark logic must use ONE timestamp source in ONE format. The live SSE event payload only exposes JSONB `modified`, not the column `modified_at` — so either add `modified_at` to the broadcast envelope, or normalize both fields to the same value+format at write time. Never compare a JSONB `modified` against a column `modified_at`. When reviewing any new `setLastSyncTimestamp`/`since` code, check which timestamp it reads.
