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

- **Verify the Discord tournament section on a server that hides channels by default.** On a test server whose `@everyone` lacks View Channels and whose onboarding is on, with the bot re-authorised for Manage Server (install integer `8861518896`, `wiki/discord.md`), run `/setup`, start a round, then `/teardown`. **Done when** a member who opted into nothing sees #announcement, #lobby and their table channel, cannot post in #announcement, cannot see #judges, the server's onboarding prompts are unchanged and its default channels are back as they were after `/teardown` (the test server needs at least one prompt), and `wiki/discord.md` (Onboarding) states whether default channels reach existing members and whether a table channel needs onboarding to show.
