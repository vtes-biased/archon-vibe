---
name: tournament-transaction-nested-pool
description: tournament_transaction pooled-conn nesting — pst #12 reuse fix, pst #44 ambient ContextVar, and the load-bearing reason writes pool independently (go_online VEKN-id collision)
metadata:
  type: project
---

**pst #45 (2026-06) RESTRUCTURED go_online — the per-player nested-pool concern
below is now RESOLVED.** `go_online` in `backend/src/routes/tournaments.py`
(lines ~1598-1731) now resolves/creates offline players (the
`_resolve_or_create_offline_player` loop → `allocate_next_vekn_id` +
`insert_user` + invite emails) OUTSIDE `tournament_transaction`. Order: (1) cheap
UID-match validation; (2) pre-lock gate — unlocked `get_tournament_by_uid`, then
`_is_organizer` (403) + device-lock (409) checks that gate side effects; (3)
resolve loop builds `uid_map` on independent pooled conns (lock not yet held, so
`_tx_conn` unset); (4) `tournament_transaction` holds ONLY tx_conn — re-checks
org+device authoritatively, merges organizers, remaps uids (CPU), single
`save_object(conn=tx_conn)`; (5) post-lock sanctions/decks/broadcasts. So the
lock no longer acquires any pooled conn per player — pool-starvation concern gone.

**TOCTOU preserved, but new orphaned-user window (acceptable):** Two devices can
still both pass the unlocked pre-check and both create users; only one holds the
FOR UPDATE row lock at a time. First reconcile clears offline_mode; the second's
locked re-check sees offline_mode=False so its device check is bypassed and it
saves too (last-writer-wins upsert) — identical to pre-#45 behavior, fine under
"server always wins / force-takeover escape hatch". NEW leak: if the requester is
removed from organizers_uids by a concurrent reconcile between the pre-check and
the lock, the locked re-check (line ~1652) 403s AFTER users were already created
→ orphaned coopted User rows (+ possible sent invite emails), tournament not
saved by this request. Old code created users inside the lock after the checks,
so never had this window. Verdict: low-harm (orphans are valid VEKN-allocated
User records, dedup by vekn/email on retry), rare race — acceptable trade-off for
removing in-lock pool pressure. Document as known limitation; don't block.

**How to apply:** Flag if anyone moves MULTI-CONNECTION write work back inside
tournament_transaction, or adds a pre-lock side effect that's expensive to orphan.
Do NOT take the advisory lock on tx_conn while inside the tx — real lock-ordering
hazard. Related: [[tournament-get-route-prefix]], [[sync-cursor-timestamp-trap]].

--- HISTORICAL (pre-#45 state, kept for the load-bearing rationale below) ---

Before #45, `go_online` ran the whole offline reconciliation inside
`tournament_transaction(uid)` (`SELECT "full" FROM objects WHERE uid=%s FOR
UPDATE`). Inside that lock it called `_resolve_or_create_offline_player`, which
calls `allocate_next_vekn_id`. That function acquires a **second** pooled
connection and takes `pg_advisory_xact_lock(1)`. So a single go_online request
held: pooled conn A (tx + tournament row lock, whole reconciliation) + pooled
conn B (advisory lock 1, short). Every concurrent go_online with N offline
players held 2 pool slots and serialized on advisory_xact_lock(1); pool
`max_size=20`, so it starved at ~10 concurrent. #45 removed this by moving the
resolve loop out of the lock (see above).

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
scope was a DIFFERENT path, NOT addressed by the #12 fix —
`tournament_action` doesn't allocate vekn ids. That nested-pool concern was
RESOLVED separately by **pst #45** (resolve loop moved out of the lock — see top
of this file).

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
