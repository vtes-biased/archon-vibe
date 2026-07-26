---
name: archon-merge-cross-sync-flipflop
description: Both known merge-vs-VEKN-sync flip-flop vectors are FIXED and guarded in code — verify the guards still stand rather than re-reporting them as live
metadata:
  type: project
---

The `--merge` mode of `backend/scripts/migrate_from_archon.py` (runs daily during the
production parallel run alongside both VEKN syncs) shares fields with `vekn_sync.py`
and `vekn_tournament_sync.py`. A field written by two of the three oscillates daily
when the upstreams disagree, bumping `modified_at` and re-delivering the row to every
client — silent, and the equality-based `same_but_modified` detector cannot catch it
(each side sees the other's write as a real change).

**Both known vectors are FIXED. Do not report them as live** — read the guard first.

1. **Tournament meta** (name/format/venue/country/`organizers_uids`/…) — guarded at
   `migrate_from_archon.py:1357-1381`. On the vekn-linked merge path it does
   `msgspec.structs.replace(existing, …)`, keeping the VEKN sync's descriptive metadata
   and writing only play data + archon-only config, with `organizers_uids` unioned
   (`dict.fromkeys(existing.organizers_uids + t.organizers_uids)`) the way the VEKN sync
   does. Only the own-uid/insert path still does a full `build_tournament`.

2. **Officials' `contact_email`** — guarded at `migrate_from_archon.py:658-662`: the
   per-field merge loop skips `contact_email` when `live.vekn_id in OFFICIALS_EMAILS`,
   since `vekn_sync.py` injects it from the scraped officials list.

**How to apply:** when reviewing changes to the archon merge, the VEKN member sync, or
the VEKN tournament sync, check the field-ownership matrix in
`.pst/details/115-legacy-archon-sync.md` and confirm no *new* field is written by two of
the three, and that the two guards above still stand. Pairs with
[[project_dual_timestamp_sync]] (the catch-up cursor that would carry such churn to
clients).

Unrelated but adjacent: the merge writes through `db.save_*`, not
`broadcast_precomputed()`, so it emits no SSE. Its changes reach clients only on their
next reconnect/catch-up — expect one large delta after a run that clears a backlog.
