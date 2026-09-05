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

A decklist the event unpublishes stays visible to a member — the broadcast sends no frame when a row's member projection drops to null, so a `decklists_mode` narrowed on a still-Finished event leaves a stale `public: true` in every connected member's IndexedDB and the profile deck list shows a decklist that is no longer public. Done when narrowing `decklists_mode` on a Finished event removes the now-private decks from a connected member's IndexedDB, a member reconnecting after the narrowing has them removed by catch-up, and `wiki/sync.md` records that a member projection dropping to null retracts the row.
