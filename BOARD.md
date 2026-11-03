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


- Let an official switch the promo inventory between grouping by promo and grouping by holder, so an NC can read each Prince's stock at a glance. **Done when** a segmented pill toggle above the holdings offers "By promo" / "By holder", mirrored in the URL; by holder lists each holder alphabetically with their promos, showing remaining and received counts and the retired badge; both views work offline from the synced holdings; the labels exist in every locale; and doc-impact is none, since it reuses the segmented-toggle idiom and records no new decision. From an NC.
