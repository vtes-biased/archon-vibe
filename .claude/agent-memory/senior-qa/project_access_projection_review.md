---
name: access-projection-review
description: How to QA a change to access_levels.py projections — where the only field-membership assertions live, and why the test suite structurally cannot catch a missing backfill.
metadata:
  type: project
---

Reviewing a widening/narrowing of a `backend/src/access_levels.py` projection:
**`backend/tests/test_access_levels.py` is the only place in the backend suite
that asserts projection field membership.** Everything else that mentions
`"public"` (`test_stream_objects.py`, `test_sse_broadcast.py`,
`test_calendar.py`) asserts row *sets*, sizes, or the calendar_token exclusion —
never which keys a projection carries.

**Why:** it makes "have I just made a field public without noticing?" a
one-file question. A green full suite is proof only because that file exists;
grepping the rest of `tests/` for `not in result` returns nothing relevant.
It's pure-unit (no DB, ~0.02s) so it always runs — a skipped-DB run does not
weaken this guarantee.

**How to apply:** read `TestTournamentPublic` / `TestLeague` etc. in that file
first; if the sensitive field for the type is already pinned there
(`checkin_code`, `organizers_uids`, `vekn_pushed_at` for tournaments), a new
"public ⊆ member" style test is redundant — say so and add nothing.

Two structural facts that change what you should look for:

- **The `av` access-version resync does NOT cover projection-code changes.**
  It forces a full resync when a *viewer's* level changes (`main.py`
  `compute_access_version` vs the client's `X-Access-Version`). When the
  *server's definition* of a level changes, no viewer transitioned and no row's
  `modified_at` moved, so clients keep the old payload forever. The fix is a
  re-save backfill that lets the `objects` BEFORE-UPDATE trigger bump
  `modified_at`. **No test can catch its absence** — verify the script exists
  and is deploy-ordered instead. Don't propose a test for this.
- Backend reads of `organizers_uids` (`db.py` personal-overlay lookup,
  `permissions.py`) all go through the `full` column/model, so narrowing a
  public projection cannot break server-side authz. The bot never syncs
  leagues; its `organizers_uids` reads are all tournament objects.

See [[project_oauth_consent_test_infra]] for the other read-surface test infra.
