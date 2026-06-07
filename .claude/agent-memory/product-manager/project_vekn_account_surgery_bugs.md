---
name: vekn-account-surgery-bugs
description: Confirmed defects in merge_users/strip/split account-surgery functions (ticket #59) and the must-fixes
metadata:
  type: project
---

# Account-surgery defects (ticket #59, backend/src/db.py)

Confirmed by reading code 2026-06-07. These motivate collapsing strip+split into
`detach_user_from_vekn` and fixing merge_users. See policy: [[vekn-id-detach-policy]].

1. **merge_users hand-builds `User(...)` (~28 fields)** instead of `msgspec.structs.replace`
   → omits `resync_after` (silently reset every merge); any future User field meets the
   same fate. Latent data-drift bug. Fix: use structs.replace.
2. **merge_users never reassigns decks** → a non-VEKN user with decks who /claims a VEKN
   ID has decks left on their soon-soft-deleted uid = deck loss. Need reassign_decks
   (DeckObject.user_uid: delete_uid -> keep_uid). No reassign_decks helper exists today.
3. **split leaks discord_id** → orphan VEKN record keeps the departed person's discord_id,
   which is in access_levels._USER_CONTACT_FIELDS (full projection) and gets re-broadcast,
   plus kept alive via vekn_sync _infer_coopted_by rebuild. Real PII leak. strip nulls it.
4. **split omits `modified=now` on orphan** → stripped personal data doesn't re-broadcast
   over SSE; stale data lingers in clients' IndexedDB. strip sets it.
5. **strip vs split inverted sanction/coopted handling**: split reassigns ALL sanctions to
   the person + nulls coopted_by/at/vekn_prefix on orphan; strip keeps sanctions on record +
   keeps coopted/prefix. Correct answer (per policy): sanctions split by LEVEL, coopted/prefix
   always stay with record.

**How to apply:** ticket #59 should (a) collapse strip+split -> detach_user_from_vekn,
(b) fix merge_users (structs.replace + reassign_decks), (c) make sanction reassignment
level-aware. Items 1-2 are merge-side and beyond #59's literal scope but should ride along.
Known limitation NOT fixed by #59: merge also doesn't reassign tournament results keyed to
delete_uid (edge: claimant already had results under a non-VEKN account).
