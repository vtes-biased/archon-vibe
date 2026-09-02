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

- Hold a Limited deck to the checks that apply in every format, not to Standard construction: under Limited the engine reports only unknown and banned cards, never the 60–90 library, the 12-card crypt or the consecutive-groups rule. **Done when** a 40-card three-group deck validates clean on a Limited event and errors on a Standard one, an engine test pins that beside the V5 one, the format row in `wiki/tournaments.md` says what Limited validation does, and the deck-validation paragraph in `wiki/architecture.md` no longer says the sizes apply whatever the format.
