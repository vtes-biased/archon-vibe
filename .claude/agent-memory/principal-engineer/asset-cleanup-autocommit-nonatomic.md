---
name: asset-cleanup-autocommit-nonatomic
description: db.py connection pool is autocommit=True, so multi-statement writes that must be consistent need an explicit conn.transaction() — else a crash mid-sequence leaves a partial, sometimes unrecoverable, state
metadata:
  type: project
---

`db.py` inits the pool with `autocommit=True`, so a sequence of `conn.execute(...)` calls with **no** explicit transaction commits each statement separately. Any multi-statement write that must stay consistent has to open `async with conn.transaction():` (which nests as a savepoint if `conn` is already inside a caller transaction like `tournament_transaction`).

**Why it bites:** the hard-delete paths delete the `objects` row AND its keyed side-table asset (`avatars.user_uid`, `banners.tournament_uid` — no FK cascade in schema.sql, so cleanup is manual). Under autocommit a crash between the `objects` delete and the asset delete orphans the image bytes PERMANENTLY — the next `purge_deleted_objects` keys off `deleted_at` on a row that no longer exists and can never re-collect them. Leaked bytes only (never a sync/correctness bug), but it defeats the exact orphan the cleanup exists to prevent.

**How to apply:** `delete_object` and `purge_deleted_objects` are the correct exemplar — both now wrap their object+asset deletes in `async with conn.transaction():` (do NOT "re-fix" them; they're already atomic). When you ADD or review another multi-statement delete/update that must be consistent, check whether it runs under autocommit (no real transaction open) and wrap it the same way. `conn.transaction()` is safe whether the conn is bare-autocommit (opens a tx) or mid-transaction (opens a savepoint).
