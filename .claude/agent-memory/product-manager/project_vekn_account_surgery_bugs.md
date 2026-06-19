---
name: vekn-account-surgery-bugs
description: Regression watch-list for VEKN account-surgery (merge/detach) — the defect classes the merge/detach rework fixed and must not return
metadata:
  type: project
---

# Account-surgery regression watch-list (merge/detach, backend/src/db.py)

The merge/detach rework (one change collapsed strip+split into `detach_user_from_vekn`;
a later pair fixed merge) closed a set of subtle defects. They're easy to
reintroduce, so when touching `merge_users` / `detach_user_from_vekn` /
`reassign_*`, confirm none of these returns. Policy: [[vekn-id-detach-policy]].

1. **Field-by-field reconstruction drops new fields.** merge_users once hand-built
   `User(...)` (~28 fields) and silently reset `resync_after` every merge. Use
   `msgspec.structs.replace`, never hand-list fields.
2. **Decks not reassigned.** A non-VEKN user with decks who claims a VEKN ID must
   have decks repointed (`DeckObject.user_uid: old → keep`), or they're lost when
   the old uid is soft-deleted.
3. **PII leak on the orphan.** A detached/orphan VEKN record must NOT keep the
   departed person's `discord_id` / contact fields — those are in the `full`
   projection and get re-broadcast (and rebuilt by vekn_sync). Detach nulls them.
4. **Missing `modified=now` on the orphan** → stripped data doesn't re-broadcast,
   stale data lingers in clients' IndexedDB.
5. **Sanctions/coopted ownership.** Per policy: sanctions ALWAYS stay with the
   VEKN record (keyed on the stable uid); coopted_by/at + vekn_prefix always stay
   with the record. Don't reassign these to the departing person.

Known unfixed edge (acceptable): merge does not reassign tournament *results* keyed
to the dying uid (only matters if the claimant already had results under a separate
non-VEKN account). See test infra in senior-qa's account-surgery memory.
