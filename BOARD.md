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

Coming back from a member's profile returns to the members tab it was opened from, not the community tab — **Done when** an official who opens a member from the members list and navigates back lands on that list with its tab and filters intact, in the browser and in the installed app, and `wiki/design.md` states the mechanism that makes it true.

Give the dev database a fixed, known-credentials IC-role account so members management can be exercised signed in — **Done when** a standalone script creates it with constant credentials, re-running it changes nothing, it deletes and modifies no existing row, it refuses any database but the local dev one, its VEKN id sits outside the e2e seed cleanup's range, no frontend affordance or backend endpoint is added, and `wiki/dev.md` carries the credentials and records that a dev login is never an app feature.
