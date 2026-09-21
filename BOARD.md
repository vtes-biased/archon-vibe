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

- Link player names in a tournament's standings and its winner line to the member's public profile, as organizer names already are (`PlayerView.svelte:664,:776,:812`, `FinishedResults.svelte:78`, pattern at `+page.svelte:929`); the organizer roster and seating rows keep their controls and stay unlinked. gh-20, from a Prince comparing against vekn.net event results. **Done when:** clicking a name in any standings table or on the winner line of a tournament page opens that member's profile, signed in or not. Doc-impact: none — a link on an existing surface, no recorded decision changes.
