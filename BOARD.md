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

- Let an organizer delete the mistaken event that vekn.net no longer has: an event deleted upstream stays linked here forever, undeletable, and re-pushed by the hourly batch into a 404 loop nobody reads — the unanswered half of the deletion block a Prince asked about. **Done when** the calendar sync records on the tournament itself that its vekn id was positively confirmed gone, taken from the scan's confirmed-no-event answer and never from absence in the scan's yield, which drops every past event with no players and so drops exactly this population; the record clears itself as soon as the event answers again; no client can write it; the finished-tournament header tells the organizer the upstream record is gone; deletion is permitted on that state alone with the IC cleanup capability left deferred; and `wiki/vekn.md` documents the flag while `wiki/vekn-decommission.md` retires the reconciliation ask this supersedes and narrows the IC ask to the rest.
- Give a league page its standings without a scroll: `product.md` calls auto-updating standings the league's headline feature, but they sit below an unbounded event list and a card spending 210px on one date range, so on a phone three events push the Standings heading under the fold and four put it 82px under — and the league that prompted this plans four. **Done when** `/leagues/[uid]` carries the app's tab strip over Events and Standings with the child-leagues block joining it on a meta-league, the league's identity — name, kind, badges and date range — stays above the strip and the Dates card is gone, the strip never opens on the empty standings a league with no play yet renders, and `wiki/design.md` adds the league page to the surfaces its tab-strip rule names and records the tab set the way the member profile's is recorded.
