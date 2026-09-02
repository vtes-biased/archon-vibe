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

- Give every disclosure in the app one shell: `FoldableSection` is the app's single fold grammar but only two surfaces use it, while thirteen others hand-roll a chevron in two competing idioms — right/down and a rotating one. **Done when** every fold opens through `FoldableSection` or its exception is stated on the page, the second idiom is gone, a lint gate holds it the way `just dark-variant` holds the `dark:` ban with the gate recorded in `wiki/dev.md`, and `wiki/design.md` carries the corrected count in its fold grammar rule with the redesign-pass bullet that owed this cleanup deleted.
- Give the tournament list back its first screen: on a phone the filter card spends 410 of 852 pixels before the first row, and signed in the agenda toggle sits above it as well, so the live event the agenda already sorts to the top is pushed under the fold. **Done when** the selects move behind a single filter control naming how many are active, the search field and the agenda/all toggle stay in place, URL mirroring and the clear-filters empty state still hold, at 393×852 the toggle and at least two rows are visible without scrolling, and `wiki/design.md` generalizes the console's first-viewport rule to every list surface and names the public tournament masthead as owing it too.
- Tell a first-time visitor what Archon is before handing them a filter card: `/` redirects straight to the tournament list, so a player told to sign up arrives at search controls that never name the app. **Done when** a signed-out visitor to `/` gets a page naming what Archon does and the two ways in — sign up, or browse events — a signed-in one still resolves to the list as today, the surface takes the `frontend-design` skill's full process that `wiki/design.md` reserves for it, and the durable decisions fold back into `wiki/design.md` with `wiki/product.md` naming the new surface.
