---
name: tournament-transaction-nested-pool
description: tournament_transaction pooled-conn nesting — pst #12 reuse fix, pst #44 ambient ContextVar, and the load-bearing reason writes pool independently (go_online VEKN-id collision)
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
rare, low concurrency). Flag if anyone moves MORE multi-connection work inside
tournament_transaction, or if go_online concurrency rises. Do NOT take the
advisory lock on conn A while inside the tx — it would create a real
lock-ordering hazard. Related: [[tournament-get-route-prefix]].

**pst #12 resolution pattern (2026-06):** The `tournament_action` path (the
common one — every CRUD action) was fixed NOT by prefetch but by
connection-REUSE. `db._acquire(conn=None)` asynccontextmanager yields a
passed-in conn or else pool-acquires; read helpers (`get_object_full`,
`get_user_by_uid`, `get_tournament_by_uid`, `get_decks_for_tournament`,
`get_sanctions_for_tournament/_for_user`, `get_all_leagues`, plus new batched
`get_sanctions_for_users`) take optional `conn`. Inside the lock,
`tournament_action` passes `conn=tx_conn` to every read, so one in-flight action
= one pooled conn. Reuse was chosen over the ticket's literal "prefetch" because
the per-player sanction set depends on the locked tournament's player list —
prefetch would reintroduce a TOCTOU window. Reuse is safe here: plain awaited
SELECTs on the autocommit conn inside its `conn.transaction()`, no nested
transaction/pipeline (same idiom save_object(conn=) already used).

The `go_online` / `allocate_next_vekn_id` second-pooled-conn-for-advisory-lock
scope described above is a DIFFERENT path and is NOT addressed by that fix —
`tournament_action` doesn't allocate vekn ids. That nested-pool concern remains
open for go_online.

**pst #44 (2026-06): ambient ContextVar + the load-bearing read/write split.**
#44 makes reuse automatic via a `ContextVar` `_tx_conn` holding
`_ActiveTx(conn, owner_task)`. `tournament_transaction` set()s it (token reset in
`finally`, inside the `_pool.connection()` block so reset precedes pool return);
`_acquire(conn=None)` resolves explicit conn → ambient (same task) → pool. So any
READ helper called inside a transaction reuses tx_conn even without `conn=`
threaded. A cross-task use (a `create_task`/`gather` child that inherited the
copied context) raises via `asyncio.current_task() is not active.task`.

CRITICAL non-obvious rationale — WHY writes must NOT be ambient-aware:
`get_connection()` (all writes: save_object, insert_user) is deliberately NOT
ambient. Reason discovered: go_online's `_resolve_or_create_offline_player` loop
runs `allocate_next_vekn_id` (own pooled conn + advisory lock + COMMIT) →
`insert_user` → next-iteration `allocate_next_vekn_id` that MUST see the
committed user. If insert_user joined the outer (uncommitted) txn, the next
allocation (separate advisory-locked txn) would reissue the same VEKN id →
duplicate IDs. So the read-ambient / write-independent asymmetry is load-bearing,
not stylistic. A write joins the txn ONLY via explicit `conn=tx_conn`.

Recommendation given (#5 of review): KEEP the explicit `conn=tx_conn` threading
in tournament_action even though ambient now makes it redundant — it's the safer
mechanism (task-independent, call-site-visible txn boundary) and survives the one
failure mode the cross-task guard exists to catch. Verdict on #44: LGTM, no
blocking issues. go_online in-lock writes are pool-pressure not deadlock (diff
rows, short-lived conns) — defer.
