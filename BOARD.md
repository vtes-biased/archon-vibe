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

- Give a league page its standings without a scroll: `product.md` calls auto-updating standings the league's headline feature, but they sit below an unbounded event list and a card spending 210px on one date range, so on a phone three events push the Standings heading under the fold and four put it 82px under — and the league that prompted this plans four. **Done when** `/leagues/[uid]` carries the app's tab strip over Events and Standings with the child-leagues block joining it on a meta-league, the league's identity — name, kind, badges and date range — stays above the strip and the Dates card is gone, the strip never opens on the empty standings a league with no play yet renders, and `wiki/design.md` adds the league page to the surfaces its tab-strip rule names and records the tab set the way the member profile's is recorded.
