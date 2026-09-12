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

- An organizer's edit to a tournament filed on vekn.net is reverted by the inbound sync within six hours — the app must own its name, finish and timezone, while vekn.net keeps the fields a mismatch would break. Done when an organizer's edit to those three survives a sync cycle unchanged, and `wiki/vekn.md` states which tournament fields the app owns, which vekn.net owns, and the rule that decides — context in [board/vekn-app-owned-fields.md](board/vekn-app-owned-fields.md).
- Finish Tournament stands in the action bar's More menu, not only in Tools › Wrap Up, once a Waiting tournament has two played rounds — the moment finals become one exit among two rather than the only one. Done when that menu item opens the same confirmation the Tools entry does, the Tools entry stays as the any-state path, and `wiki/design.md` records the placement as a standing decision alongside the promo-CTA and CSV-import precedents it follows.
