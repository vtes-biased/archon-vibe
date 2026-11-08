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
docs. **No waiting state**: externally-gated work is deferred on the docs page
that owns it — see [docs/vekn-decommission.md](docs/vekn-decommission.md) — with a
named trigger, and returns through `/intake` when the trigger fires.

**Every line must be completable** — if "done" cannot be stated, it is a subject:
promote it to a [docs](docs/index.md) page and delete the line. Context lives in
the docs; asks live here. Bulky context for an in-flight line goes in
`board/<slug>.md`, deleted with the line.

Board changes ride the commit that earns them.

- Adopt a `WATCH.md` beside the board for dated checks, recurring checks and externally-gated work: move the deferred asks out of `vekn-decommission.md` (its evidence stays as docs) and the Rules Director trigger off `tournaments.md`, leave the post-release journal where it is since it waits on a release rather than a date, add a watch-check skill that reads the file and sends fired items through intake, and stop upkeep watching triggers. Done when no docs page carries a triggered ask except the post-release journal, `WATCH.md` holds the moved items with when, what to check and what each outcome does, the intake and upkeep skills name the file, and `index.md` and `dev.md` describe it.
- Run the retrospective as published: ship writes a friction trailer on each commit (owner corrections, review rounds, surprises, failing checks); upkeep reads the trailers and recent session transcripts through a cheap-model subagent, proposes a rule at two occurrences with its evidence and a one-line reason, and removes rules whose reason has lapsed. Done when the ship skill names the trailer format, the upkeep skill names the mining step and the removal verdict, `principles.md` carries the trailer in its Git section, and one upkeep pass has run it.
