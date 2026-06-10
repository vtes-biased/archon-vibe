---
name: archon-merge-cross-sync-flipflop
description: The legacy-archon daily merge and the two VEKN syncs share fields; tournament meta + officials' contact_email can flip-flop daily unless single-writer is enforced
metadata:
  type: project
---

The `--merge` mode of `backend/scripts/migrate_from_archon.py` (pst #115, runs daily during the production parallel run alongside both VEKN syncs) shares fields with `vekn_sync.py` and `vekn_tournament_sync.py`. "Single writer per field" is enforced for **members** (via `ARCHON_USER_FIELDS`) but NOT for **tournaments** — `build_tournament` writes the whole object.

Two cross-sync daily-churn (flip-flop) vectors, each silent and producing daily SSE catch-up churn:

1. **Tournament meta** (name/format/venue/country/`organizers_uids`/…). For a rich-merged event (one whose rich payload merged INTO a vekn-created copy, so `external_ids.vekn` is set), `vekn_tournament_sync.py:333-374` keeps refreshing meta on its rich-guard path (notably re-adding vekn.net organizers), while the archon merge rebuilds a fresh `Tournament` that resets those to old-archon values. They oscillate forever if the two upstreams disagree. Fix direction: in the vekn-matched merge paths, `msgspec.structs.replace(existing, rounds=..., finals=..., players=..., standings=..., winner=..., decks-side-effects)` — preserve `existing`'s identity/venue/organizers; only the own-uid/insert path should do the full build.

2. **Officials' `contact_email`**. Both the merge (`ARCHON_USER_FIELDS` includes it) and `vekn_sync.py:580-582` (`OFFICIALS_EMAILS` scraped list, officials only) write it. Diverging values flip daily for non-self-edited officials. Fix direction: merge skips `contact_email` when `vekn_id in OFFICIALS_EMAILS`.

**Why:** these are interactions a future field-set change could reintroduce; the equality-based `same_but_modified` change-detector can't catch a cross-sync oscillation (each side sees the other's write as a real change).

**How to apply:** when reviewing changes to the archon merge, the VEKN member sync, or the VEKN tournament sync, check the field-ownership matrix in `.pst/details/115-legacy-archon-sync.md` and confirm no field is written by two of the three. Pairs with [[project_dual_timestamp_sync]] (the catch-up cursor that carries this churn to clients).
