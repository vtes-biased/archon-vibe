---
name: archon-merge
description: legacy-archon daily-merge (migrate_from_archon.py --merge) test infra + the "no sync writes roles" invariant and its coverage
metadata:
  type: project
---

The legacy-archon → new-stack **daily merge** (`backend/scripts/migrate_from_archon.py`
`--merge` mode) runs during the production parallel run (pst #115; real
acceptance is a prod-dump rehearsal, pst #91 — unit tests are only high-confidence
regression guards). Coverage: `backend/tests/test_archon_merge.py`.

**Shipped functions the tests exercise directly** (importable, no mocks):
`process_tournament_row`, `merge_member`, `build_user`, `deck_uid`, plus
`VEKNSyncService._map_vekn_to_user`. Tests run against the real DB.

**Merge invariants pinned (one test each):** rich-merge-into-vekn-copy +
second-run idempotence; archon-first interleave dedup (round-less copy
tombstoned, `tournaments.roundless_copy_tombstoned`); echo guard
(`tournaments.echo_skipped`); both-rich skip (`tournaments.both_rich_conflict`);
member field-ownership respecting `local_modifications`; member vekn-id dedup
(`members.vekn_copy_tombstoned`).

**The "no sync ever writes roles" invariant (security-relevant, was UNCOVERED
before #115).** Roles are seeded once from old archon (`build_user`) and
app-managed thereafter. Two sides now enforce it, guarded by one test each:
- `_map_vekn_to_user` omits the `roles` key entirely (was: princeid→PRINCE,
  coordinatorid→NC, static ADMINS/JUDGES lists; `vekn_roster.py` deleted).
  Test: `test_member_sync_never_maps_roles` in test_archon_merge.py. A
  regression here flip-flops IC/NC/PRINCE access control daily.
- `merge_member` never merges roles (`ARCHON_USER_FIELDS` excludes them).
  Test: `test_member_merge_respects_field_ownership`.
No pre-#115 test imported `VEKNSyncService`/`_map_vekn_to_user` — `mock_vekn_data.py`
sets `Role.*` directly on User objects, it does NOT exercise the derivation.

**Self-edit survives sync invariant (write side).** `profile.py` now records
`nickname`/`contact_email`/`contact_phone`/`phone_is_whatsapp` into
`local_modifications` on a PATCH /auth/me, so the daily merge + officials' email
injection skip them. Test: `test_self_edited_contact_fields_flagged_local` in
test_profile_update.py. The merge *read* side (respecting the flag) is covered by
the merge test; this guards the *recording* half.

**Test-writing facts (not obvious):**
- `test_db` fixture only wipes `type='user'`. The merge tests use a
  `_cleanup()` asynccontextmanager that DELETEs `type IN ('tournament','deck')`.
  Same pattern as [[account-surgery]].
- `_map_vekn_to_user` is callable with no DB/network: `VEKNSyncService()` only
  builds a `VEKNAPIClient`. Pass a player dict with no `city` to skip the
  geonames `match_city` lookup.
- `local_modifications` survives the "full" projection (the merge reads it back
  via `get_user_by_uid`), so it IS assertable after a route PATCH.
- Engine-possible seats: `_seats()` builds a legal 5-seat finished table
  (VP 2(GW)/1/1/0.5/0.5 = 5.0, one GW). Respects the no-impossible-states rule.
- Both `external_id` lookups gained `deleted_at IS NULL` (db.py
  `get_tournament_by_external_id`, vekn_sync `_get_user_by_vekn_id`) so the VEKN
  syncs don't refresh a merge-tombstoned duplicate. Covered transitively by the
  dedup tests' tombstone assertions.
