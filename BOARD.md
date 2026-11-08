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

- Show a member's worldwide rank next to each rating total on their profile and public member page, through one ranking function the rankings page also uses — its sort, tie and threshold logic (`rankings/+page.svelte:73-90`) moves to `tournament-utils.ts` rather than being copied into `PlayerRatings.svelte`; players currently scroll the rankings to find themselves (gh-87) — **Done when** a rated member's profile shows the same rank as their row on the rankings page with no country filter, ties included, the rankings page ranks through the same function, and the profile description in `wiki/product.md` mentions the rank.
