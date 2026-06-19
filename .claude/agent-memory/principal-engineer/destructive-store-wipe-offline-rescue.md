---
name: destructive-store-wipe-offline-rescue
description: TWO call sites destructively wipe IDB stores and must rescue in-flight offline-tournament rows (tournament+sanctions+decks+player-stubs), not just the tournament row
metadata:
  type: project
---

Destructive IndexedDB store-wipes must rescue the FULL in-flight offline set, not just the tournament row. There are TWO triggers of the same data-loss class:

1. `frontend/src/lib/db.ts` `getDB()` upgrade handler — destructive drop/recreate on any DB_VERSION bump (forces full SSE resync). Fixed via `rescueOfflineData()`/`restoreOfflineData()` inside the versionchange tx.
2. `frontend/src/lib/sync.ts` `clearAllStores()` — server-driven resync (stale cursor / role change) + refresh + logout reset. More frequent trigger. Historically rescued ONLY the tournament row, dropping offline sanction/deck rows and player user-stubs.

The complete rescue set (defined by what `frontend/src/lib/stores/offline.svelte.ts` `goOnline()` consumes on reconciliation):
- tournament row (key: `offline_tournament:<uid>`)
- offline sanction rows (uids in `offline_sanctions:<uid>` JSON array → `getSanction`)
- offline deck rows (uids in `offline_decks:<uid>` JSON array → `getDeck`)
- player user-stubs (temp_uid in `offline_players:<uid>` JSON → temp User rows; needed for display AND reconciliation)
- `offline_*` metadata keys themselves (the manifest); `offline_last_sync:` is harmless to keep

**Why:** offline tournaments are device-locked and hold unsynced work; dropping their rows is a silent, catastrophic sync bug. Metadata pointers surviving without the referenced rows → `getSanction`/`getDeck`/`getUser` return undefined → silently dropped from `goOnline()` reconciliation.

**How to apply:** any time code clears these object stores wholesale, verify it rescues all four row types above for every uid in `getOfflineTournamentUids()`. idb versionchange-tx liveness rule: issue all row reads in one synchronous burst then a single `Promise.all`; never sequential await-per-row (auto-commit hazard in WebKit/Firefox). Owner prefers locality over DRY, so two explicit rescue call sites is acceptable over a shared helper.
