---
name: tournament-transaction-nested-pool
description: go_online holds a tournament_transaction row lock + pooled conn while _resolve_or_create_offline_player grabs a SECOND pooled conn and pg_advisory_xact_lock(1) — nested-lock / pool-starvation hazard
metadata:
  type: project
---

`go_online` in `backend/src/routes/tournaments.py` runs the whole offline
reconciliation inside `tournament_transaction(uid)` (db.py:343 — `SELECT "full"
FROM objects WHERE uid=%s FOR UPDATE`). Inside that lock it calls
`_resolve_or_create_offline_player`, which calls `allocate_next_vekn_id`
(db.py:787). That function acquires a **second** pooled connection via
`_pool.getconn()` and takes `pg_advisory_xact_lock(1)`.

So a single go_online request holds: pooled conn A (tx + tournament row lock,
held for the whole reconciliation) + pooled conn B (advisory lock 1, short).

**Why:** Lock ordering is consistent (the FOR UPDATE row lock is per-tournament;
the advisory lock is a single global id taken/released quickly), so no classic
deadlock between two go_online calls. But it is a NESTED pool acquisition: every
concurrent go_online with N offline players holds 2 pool slots and serializes on
advisory_xact_lock(1). Pool is `max_size=20` (db.py:58). N concurrent go_online
each needing 2 slots starves at ~10 concurrent, not 20.

**How to apply:** This is acceptable for current scale (tournament go_online is
rare, low concurrency). The proper fix is pst #12 (prefetch read-only data —
user lookups, vekn allocation — BEFORE opening tournament_transaction, so the row
lock is held only across the final save_object). Flag if anyone moves MORE
multi-connection work inside tournament_transaction, or if go_online concurrency
rises. Do NOT take the advisory lock on conn A while inside the tx — it would
create a real lock-ordering hazard. Related: [[tournament-get-route-prefix]].
