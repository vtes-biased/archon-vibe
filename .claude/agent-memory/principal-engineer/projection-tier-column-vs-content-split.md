---
name: projection-tier-column-vs-content-split
description: When tiering SSE access, a NEW precomputed column is only justified when the projection CONTENT must vary by viewer tier; otherwise collapse to an existing level + shrink the lower one.
metadata:
  type: project
---

Adding an access tier (e.g. #307 anonymous vs account vs VEKN-member) does NOT
automatically mean a new precomputed column. The decision hinges on one question:

**Does the projection content for a given object need to differ between two viewers at the SAME nominal level?**
- **No** → collapse the new tier onto an existing column (`base_data_level` one-liner + `entitled_level` widen) and shrink the lower projection. No migration, no NULL-column cliff, no per-type `compute_*` functions. Strongly preferred.
- **Yes** (e.g. "non-VEKN account sees officials but NOT the plain members list" → two different `member`-ish User projections) → a precomputed shared column physically cannot hold two contents, so a new level/column IS justified — but only `User` differs; scope the other types' new-level functions to trivial passthroughs (`_identity` / copy of `public`).

**Why:** A 4th global column taxes EVERY object type (5 new `compute_*` funcs, +1 JSONB col on every row, +1 snapshot file/15min) to express what was usually a ONE-TYPE (`User`) policy. 4 of 5 funcs end up byte-identical copies. The migration-day failure mode is the killer: existing rows have the new column NULL, so the snapshot/SSE read (`SELECT {level}::text`) returns nothing for that tier until a full corpus re-`save_object` backfills it.

**How to apply:** Before recommending a new projection column, grep which types actually differ at the new tier. If only `User`, push back on a corpus-wide column. Note that the `av` fingerprint (`compute_access_version`, db.py) already folds `base_level`, so ANY tier mechanism that moves `base_data_level` gets resync-on-tier-change for free — don't re-implement it.

Related: the `_obfuscate`/`deobfuscateContact` base64 on `compute_user_public` contacts is a HARVESTER speed-bump, NOT access control — the recipient's IDB decodes it. Shrinking a `public` projection to fix a data-on-the-wire leak is mandatory and independent of any tier-shape choice; a frontend gate never fixes it. See [[error-codes-contract]] for the single-source-of-truth discipline this mirrors.
