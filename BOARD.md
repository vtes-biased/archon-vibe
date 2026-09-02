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

Confine a disqualification to the tournament it was issued for — it never bars entry, zeroes standings or kills a rating at any other event, league sibling or not; every tournament-level sanction is bound to an event and the two VEKN-wide levels are not; and an official reading a member's profile sees which event each Warning, SA and DQ came from, as a link — **Done when** a player DQ'd at one event can register, check in and score normally at any other tournament including one in the same league, the app refuses to record a Caution, Warning, SA or DQ with no tournament and a Suspension or Probation with one on both the issue and the edit paths, the league organizer's right to lift a DQ is retired, the sanctions on a member's profile each name and link their tournament for an official, the leagues help text stops promising a league-wide block in all five catalogs, and the doc-impact listed in `board/dq-scope.md` is discharged.

Make an external registration link replace Archon's own sign-up: with a registration URL set, the engine refuses a self-service registration and the player is shown the link instead, the organizer's CSV import being how the roster fills — **Done when** such an event offers no Register button in the app and refuses the bot's `/register` from the engine with a message that names the link, an imported player still sees their own registration and can upload a decklist, the field help and wizard tip say so in all five catalogs, and the doc-impact listed in `board/external-registration.md` is discharged.
