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

- Review the whole tournament bot package cold, after the bot lines above it have landed, for organization, efficiency, lingering traps and defects, and land what it finds as one change. Done when every finding is fixed in the change, refused with its reason in the commit message, or sent through ingress as separable work, the comment pass has run over every bot module, `just lint` and the bot's pytest are green, and the "Rounds and the bot" section of `wiki/hazards.md` plus the tournament bot and SSE listener sections of `wiki/discord.md` describe the code as it stands.
