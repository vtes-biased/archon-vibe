---
name: vekn-unique-index-spans-tombstones
description: the vekn_id unique index (schema.sql ~143) has NO deleted_at exclusion, so a soft-deleted user keeps its vekn_id reserved — lookups that filter deleted_at disagree with the constraint and can crash on insert
metadata:
  type: project
---

`idx_objects_user_vekn_id` (`backend/src/schema.sql` ~:143) is
`UNIQUE ... (("full"->>'vekn_id')) WHERE type='user' AND vekn_id IS NOT NULL AND
!= ''` — **no `deleted_at IS NULL`**. So a SOFT-DELETED user still reserves its
vekn_id against the constraint.

`save_object`'s upsert is `ON CONFLICT (uid)` (`db.py` ~:278) — keyed on uid, NOT
vekn_id — so a fresh INSERT carrying a vekn_id already held by a (possibly
tombstoned) different-uid row trips the unique index and raises IntegrityError
(no handler → aborts the txn).

The hazard surfaces when a lookup that DOES filter `deleted_at` (e.g. the merge's
`live_user_by_vekn_id`) returns None for a vekn_id that a tombstone still holds,
then the caller seed-inserts under a new uid → collision. `db.get_user_by_vekn_id`
does NOT filter deleted_at, so it and `live_user_by_vekn_id` disagree.

**How to apply:** when adding any vekn-id-keyed insert/lookup, make the lookup's
deleted_at filtering match the index (which spans tombstones) — or the insert can
crash on a number reserved by a soft-deleted row. The #169 archon merge cutover is
safe (its own vekn-less shells carry no vekn_id), but steady-state runtime
soft-deletes that keep vekn_id (admin user-delete) make it reachable on later
nightly merges — confirmed reachable, just not on cutover.
