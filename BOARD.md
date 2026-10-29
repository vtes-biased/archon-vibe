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

- Let a league play its own final and crown its winner Champion instead of the standings leader ([context](board/league-final.md)) — **Done when** a league organiser can seat a final from the league's top five and enter its result on the league page, scored like a tournament final with seeds from league rank, a finished league crowns that final's winner (the standings leader when no final was played), and the Leagues paragraph in `wiki/product.md`, a "league final" row in `wiki/glossary.md` and the finals scoring section of `wiki/tournaments.md` state it.
- Give tied members the same rank on the rankings page, Hall of Fame and rating tabs alike (1, 2, 2, 4, tied rows ordered by name) — gh-68: rows are numbered by position (`frontend/src/routes/rankings/+page.svelte:233`) after a sort on the score alone — **Done when** two members with equal wins or equal rating points show the same rank and the next member's rank skips past them, and the Ratings and Hall of Fame paragraph in `wiki/product.md` says ties share a rank.
