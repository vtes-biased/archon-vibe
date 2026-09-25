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

- Let the tournament list filter by a date window and by several countries at once — a Prince (gh-41) wants to see every event in a given month, across more than one country; the list has no date filter and a single-country one, and the calendar feed takes one country. The first-viewport rule in `wiki/design.md` keeps both inside the folded filter panel: one row of two native date inputs, and the country select becoming a multi-select, nothing added in the open. **Done when** an optional from and to date (either alone works) keep only events whose start falls inside the window, in both the agenda and the all views; the all view's country filter holds several countries and shows events in any of them; each counts in the fold's active-filter number and Clear filters empties it; all ride the URL and the remembered view like the other filters; the feed's `country` parameter takes a comma-separated list, so every existing single-country subscription URL keeps working, and the feed link built from the list carries the chosen countries and no dates; the list still reaches its first rows without scrolling on a 393×852 phone; and `wiki/product.md`'s list filters name the date window and multi-country.
