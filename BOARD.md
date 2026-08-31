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

- Give tournament creation a wizard: start from "what kind of event is this" (real-life or online, then size, multideck, decklists, paid or free, offline, big-event options, open/self-organized rounds) and land on a prefilled configuration with inline guidance for the steps the app cannot automate — Discord bot installation, offline mode activation, QR self-check-in, rooms, the paid-registrations CSV import. **Done when** an organizer can create any of the event archetypes through the wizard without touching the raw form, the plain form stays reachable, and `wiki/product.md` and `wiki/design.md` record the flow and pattern (plus `wiki/tournaments.md` if a payment-tracking flag is introduced). Context in `board/creation-wizard.md`.
