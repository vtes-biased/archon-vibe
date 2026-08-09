---
name: vekn-member-sync
description: VEKN member-sync role-seeding test infra (test_vekn_member_sync.py) + the non-obvious update-path enforcement surface.
metadata:
  type: project
---

`backend/tests/test_vekn_member_sync.py` covers the role-seed contract for
`vekn_sync.sync_player`: (a) CREATE seeds derived roles (Prince/NC from
princeid/coordinatorid, IC from the static `data/vekn_roster.py`; judge ranks are
NOT seeded — app-managed); (b) UPDATE
never writes roles (app-granted roles survive a re-sync that would derive a
different set). Both run end-to-end against the real `test_db` DB, no mocks; import
roster ids from `vekn_roster.py` rather than hand-copying.

**Why:** roles are seeded on first import and app-managed thereafter (commit
364a7ec + `.pst/details/115-legacy-archon-sync.md`). A sync re-deriving roles on
update would flip-flop access control daily — this path already swung once.

**How to apply:**
- The UPDATE-preserves invariant is enforced by `_update_user`'s explicit field
  *enumeration* (it only assigns name/country/city/state/vekn_prefix/contact_email),
  NOT by `roles` being absent from `vekn_data`. So a faithful regression mutation
  must patch BOTH: seed on the update branch in `sync_player` AND add a `roles`
  assignment in `_update_user`. Patching only one passes (the seed is inert without
  the enumeration). Mutation-test accordingly before trusting a future variant.
- `_update_user` never receives the raw `vekn_player` (only mapped `vekn_data`,
  which strips princeid/coordinatorid), so it structurally cannot derive roles on
  its own — derivation lives only in `sync_player`'s create branch.
- This replaced a relic (`test_member_sync_never_maps_roles` in test_archon_merge.py)
  whose docstring asserted the opposite of current behavior. See [[archon-merge]].
