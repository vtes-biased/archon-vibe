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

- Make console deck upload accept a VDB deck-in-URL link (the `/decks/deck?name=…#id=count;…` shape), which today fails as "VDB did not answer" because krcg reads the path word `deck` as a deck id, and stop reporting a bad or dead deck id as a provider outage. Done when krcg's VDB fetcher takes the fragment branch for that URL with a round-trip regression test of its own serializer, krcg is released and Archon's pin bumped past 5.11, a 4xx answer from any provider maps to the bad-link code while 5xx and transport failures keep the unavailable code, and the linked URL imports through the console.
- Post into each table's text chat when the round clock starts, add a 1-minute warning to the bot's 15-minute, 5-minute and time-up reminders, and announce a table's time extension in its chat when the organizer grants one, all honouring per-table extra time. Done when the start post lands in every pending table's chat on clock start but not on resume or reconnect catch-up, the regression test's threshold lists carry the 1-minute warning, and the round-timer paragraph in `wiki/discord.md` names the new set. Context in `board/timer-posts.md`.
- Make the bot's `/checkin` reply remind only the players whose check-in found no decklist on record, keep the neutral "don't forget" reminder on `/register` where no deck can be judged yet, reword the check-in-open channel announcement to address only those who have not uploaded, and have the engine's check-in write the missing-decklist stamp both ways so a re-check-in after an upload clears it. Done when a checked-in player with a deck on record gets no decklist text in the bot's reply, and a regression test shows a second check-in after an upload leaves the stamp false.
- Echo each table's seating into that table's own voice text chat when a round or the finals start, and into only the tables whose seating changed on a mid-round update, alongside the #announcement post, with no replay on reconnect. Done when a pure diff function like the result-announcement one has one regression test showing it emits nothing on a score report or check-in and skips the zero sentinel of a failed channel create, and the announcements paragraph in `wiki/discord.md` says seating is also echoed per table.
- Review the whole tournament bot package cold, after the bot lines above it have landed, for organization, efficiency, lingering traps and defects, and land what it finds as one change. Done when every finding is fixed in the change, refused with its reason in the commit message, or sent through ingress as separable work, the comment pass has run over every bot module, `just lint` and the bot's pytest are green, and the "Rounds and the bot" section of `wiki/hazards.md` plus the tournament bot and SSE listener sections of `wiki/discord.md` describe the code as it stands.
