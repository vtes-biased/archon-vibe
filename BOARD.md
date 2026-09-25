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

- Fold the player-facing tournament page's details into one panel under a short action row, drop them from the organizer console, and make Setup a permanent console tab — agenda (icon + "Agenda"), share, the view toggle and the organizer's Go Offline and Tools make the row; in the player view every badge, the vekn.net and league links, venue, dates, organizers, event code and the description move inside the panel; the console shows no details, Setup standing last among its tabs in every state (default only while Planned) with the details and organizers panels leaving Tools, and the view toggle serving as the preview; the VEKN sync warnings move to the action bar; the Register button is one primary button whether the sign-up is in-app or on an external page, the external one only adding an outbound icon; Setup's standalone table-rooms section goes, the venue one stays. **Done when** the folded panel shows country (or Online), the state unless Finished, and the start date and time; it starts open only while the event is Planned or in Registration with no round or final ever played, including after registration reopens between rounds; four console tabs fit at 360px in every locale; nothing but the action row stands between the title and the panel, or, in the console, the action bar; and the workbench, fold-grammar, tab-strip and Buttons sections of `wiki/design.md` and the `registration_url` row of `wiki/tournaments.md` record the new masthead.
