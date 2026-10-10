# Board

A list designed to shrink. **The goal is zero.** Completion is deletion — there is
no closed state, no archive; git history is the record and `git blame` knows a
line's age.

**Order is priority.** Ranking rules, applied top to bottom when two unrelated
lines compete:

1. user-reported defects
2. correctness
3. blocking work and useful refactorings
4. polish
5. new capability

**Hard limit: 15 lines.** Adding a sixteenth forces a drop or a promotion to the
wiki. **No waiting state**: externally-gated work is deferred on the wiki page
that owns it — see [wiki/vekn-decommission.md](wiki/vekn-decommission.md) — with a
named trigger, and returns through `/intake` when the trigger fires.

**Every line must be completable** — if "done" cannot be stated, it is a subject:
promote it to a [wiki](wiki/index.md) page and delete the line. Context lives in
the wiki; asks live here. Bulky context for an in-flight line goes in
`board/<slug>.md`, deleted with the line.

Board changes ride the commit that earns them.

- Remove the winner decks duplicated by the legacy-archon merge and the TWDA attach (gh-47): where a player holds two live winner decks with identical cards for the same tournament and round, soft-delete the TWDA's uuid7 copy and keep the legacy uuid5 one a `--merge` rerun would recreate; list, without deleting, any pair whose cards differ; broadcast the deletions and recompute wins as the TWDA sync does. The legacy merge matches previous decks only by its own uid (`migrate_from_archon.py:1331`), the TWDA attach skips an existing owner (`twda_import.py:489`), and the snapshot loader stores every copy (`frontend/src/lib/db.ts:1046`). Rehearse on beta, then hand the run to the owner for production. Per-round decks of one winner (gh-47's `019f1a1a-d8e3…`) are not duplicates. **Done when** production counts no tournament where a player holds two winner decks for the same round, apart from reviewed card-differing pairs, and `wiki/hazards.md`'s TWDA paragraph says the legacy merge matches decks only by its own uid.
