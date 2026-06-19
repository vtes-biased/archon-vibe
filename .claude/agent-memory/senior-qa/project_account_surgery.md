---
name: account-surgery
description: VEKN account-surgery (merge/detach) test infra + key test-writing facts for those db functions
metadata:
  type: project
---

VEKN account-surgery primitives live in `backend/src/db.py`: `merge_users`,
`detach_user_from_vekn` (replaced strip_vekn_from_user + split_user_from_vekn),
`user_has_active_suspension`, and the reassign_* helpers. Regression coverage is
`backend/tests/test_account_surgery.py` (10 tests, db-layer + 2 route-guard).
Design rule: `.pst/details/59-vekn-detach.md` — a uid carrying a vekn_id is
immovable; only the non-vekn person moves to a fresh uid.

**Why:** these were untested before the merge/detach rework; the invariant is subtle and easy to
re-break (the merge bug silently reset `resync_after` by rebuilding User from
scratch; a later fix addressed orphaned decks).

**How to apply:** when any of those db functions change, run this file. Key
test-writing facts learned here (not obvious from the code):
- `get_user_by_uid` returns the "full" projection which STRIPS `calendar_token`
  (always None). To assert token state, use `get_calendar_token(uid)` /
  `get_user_by_calendar_token(token)`, never the returned model's field.
- The `test_db` fixture only deletes `type='user'`. Sanctions, decks, and
  auth_methods must be torn down explicitly (use an asynccontextmanager that
  DELETEs `type IN ('sanction','deck')` and `FROM auth_methods`). See
  test_action_conn_reuse.py for the same pattern.
- No `get_decks_for_user` helper exists — query objects directly (mirror
  reassign_decks' own SQL).
- The vekn router mounts at `/vekn` (NO `/api` prefix); users mounts at
  `/api/users`. Prefix is per-router, there is no global root_path. So the guard
  endpoint is POST `/vekn/abandon`.
- `CurrentUser` (src/middleware/auth.py) resolves the real user from the DB via
  the JWT, so `make_auth_header(uid)` works without inserting auth_methods.
- Route side-effects (broadcast_resync, asyncio.create_task discord sync) are
  safe in tests: no SSE connections → no-op; discord sync is detached.

**calendar_token (was a gap, now FIXED):** `detach_user_from_vekn` now
carries the feed token to the personal account — it reads `get_calendar_token(old)`
explicitly (the model field is always None, stripped from "full"), clears it on the
orphan first, then sets it on the new uid. Matches `merge_users`. Covered by
`test_detach_moves_calendar_token_to_personal` (asserts token off the orphan AND
re-homed on personal so `get_user_by_calendar_token` still resolves).
