---
name: tournament-transaction-nested-pool
description: Inside tournament_transaction, reads join the txn (ambient _tx_conn) but writes acquire the pool independently — the asymmetry is load-bearing (go_online VEKN-id allocation), not stylistic
metadata:
  type: project
---

`tournament_transaction(uid)` holds `SELECT "full" FROM objects WHERE uid=%s FOR UPDATE`. Connection handling inside it has one non-obvious, **load-bearing** rule:

**Reads join the txn; writes acquire the pool independently.**
- `_acquire(conn=None)` resolves: explicit `conn=` → ambient `_tx_conn` ContextVar (same task only) → pool. So any READ helper called inside the txn reuses `tx_conn` automatically (one in-flight action = one pooled conn). A cross-task child (`create_task`/`gather` that inherited the copied context) raises via the `current_task() is not active.task` guard.
- WRITES (`get_connection()`: `save_object`, `insert_user`) are deliberately NOT ambient. **Why:** go_online's `_resolve_or_create_offline_player` loop runs `allocate_next_vekn_id` (own pooled conn + `pg_advisory_xact_lock(1)` + COMMIT) → `insert_user` → next-iteration `allocate_next_vekn_id` that MUST see the committed user. If `insert_user` joined the outer (uncommitted) txn, the next advisory-locked allocation would reissue the same VEKN id → **duplicate IDs**. A write joins the txn ONLY via explicit `conn=tx_conn`.

**go_online (tournaments.py ~1598-1731) keeps the per-player resolve loop OUTSIDE the lock** (pst #45). Order: (1) cheap UID-match validation; (2) pre-lock gate — unlocked `get_tournament_by_uid` + `_is_organizer` (403) + device-lock (409); (3) resolve loop builds `uid_map` on independent pooled conns (lock not held); (4) `tournament_transaction` holds only tx_conn — re-checks org+device, merges organizers, remaps uids (CPU), single `save_object(conn=tx_conn)`; (5) post-lock sanctions/decks/broadcasts. So the lock never acquires a pooled conn per player — no pool starvation.

**Known accepted limitation:** if a concurrent reconcile removes the requester from `organizers_uids` between the pre-check and the locked re-check (~1652), users were already created → orphaned coopted User rows (+ maybe sent invite emails). Low-harm (orphans are valid VEKN-allocated records, dedup by vekn/email on retry), rare race. Document, don't block.

**How to apply:** Flag if anyone (a) makes writes ambient-aware, (b) moves multi-connection write work back inside the lock, or (c) takes the advisory lock on `tx_conn` while inside the txn (real lock-ordering hazard). Related: [[tournament-get-route-prefix]], [[finals-seed-order-uid-field]].
