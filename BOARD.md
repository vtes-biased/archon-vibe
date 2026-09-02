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

Make an external registration link replace Archon's own sign-up: with a registration URL set, the engine refuses a self-service registration and the player is shown the link instead, the organizer's CSV import being how the roster fills — **Done when** such an event offers no Register button in the app and refuses the bot's `/register` from the engine with a message that names the link, an imported player still sees their own registration and can upload a decklist, the field help and wizard tip say so in all five catalogs, and the doc-impact listed in `board/external-registration.md` is discharged.
