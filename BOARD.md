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

- Link player names in a tournament's standings and its winner line to the member's public profile, as organizer names already are (`PlayerView.svelte:664,:776,:812`, `FinishedResults.svelte:78`, pattern at `+page.svelte:929`); the organizer roster and seating rows keep their controls and stay unlinked. And let player-facing names wrap instead of truncating on the player's own table and finals table and in the decklist rows (`PlayerView.svelte:506,:590`, `PlayerDecksSection.svelte:363,:367`) — on a phone there is no hover to recover a cut name. gh-20, from a Prince comparing against vekn.net event results; gh-21, a player on Android. **Done when:** clicking a name in any standings table or on the winner line of a tournament page opens that member's profile, signed in or not, and no player-facing seat or decklist row ellipsizes a name at 360px width. Doc-impact: none — a link on an existing surface, no recorded decision changes.
- Give the member profile's Record tab a full "Events played" list — every finished tournament the member played, newest first, with date, country and final place, whatever its age and whether or not it counted for rating — built from the tournaments members already sync, since today the rating table is the only history and it stops at 18 months and skips unranked events. **Done when:** a member profile, viewed while signed in, lists a tournament the member played more than 18 months ago and an unranked one they played, each linking to its tournament page. Doc-impact: `wiki/product.md` — the Ratings and Hall of Fame paragraph's sentence on what a member profile carries.
