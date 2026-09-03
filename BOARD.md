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

- Make the bot's `/checkin` reply remind only the players whose check-in found no decklist on record, keep the neutral "don't forget" reminder on `/register` where no deck can be judged yet, reword the check-in-open channel announcement to address only those who have not uploaded, and have the engine's check-in write the missing-decklist stamp both ways so a re-check-in after an upload clears it. Done when a checked-in player with a deck on record gets no decklist text in the bot's reply, and a regression test shows a second check-in after an upload leaves the stamp false.
- Send the bot's consent link as a Discord link button instead of a raw URL, at both the setup command and the player commands. Done when both messages carry a button and the URL length stays under Discord's 512-character button limit with the state and challenge the bot generates.
- Post into each table's text chat when the round clock starts, add a 1-minute warning to the bot's 15-minute, 5-minute and time-up reminders, and announce a table's time extension in its chat when the organizer grants one, all honouring per-table extra time. Done when the start post lands in every pending table's chat on clock start but not on resume or reconnect catch-up, the regression test's threshold lists carry the 1-minute warning, and the round-timer paragraph in `wiki/discord.md` names the new set. Context in `board/timer-posts.md`.
