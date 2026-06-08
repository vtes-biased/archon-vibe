---
name: merge-reassign-no-broadcast
description: merge_users reassigns sanctions/decks/coopted_by but those object changes are not broadcast — they stay stale on other clients until snapshot
metadata:
  type: project
---

`db.py:merge_users` calls `reassign_sanctions` / `reassign_decks` / `reassign_coopted_by_references`, which repoint `user_uid` on those objects (and other users' `coopted_by`). As of the pst #66 fix, these reassigns do NOT return BroadcastData and are NOT broadcast.

**Why:** pst #66 was deliberately scoped to the surviving/dying USER records only. The reassign helpers were left out as an explicit deferral.

**Consequence:** Other connected clients (same-country NC/Prince, IC) keep sanctions/decks cached under the OLD `delete_uid` and other users' stale `coopted_by` until their next snapshot resync — the exact "stale cached records" symptom #66 is named for, just for non-user object types. Sanctions staleness is correctness-visible.

**How to apply:** If asked to "complete" #66 or review merge/account-surgery sync, this is the remaining gap. Fix is the same pattern #66 applied: make the reassign helpers return BDs, broadcast_precomputed them in the route. Should be its own ticket. Relates to [[user-delete-sse-noop]].
