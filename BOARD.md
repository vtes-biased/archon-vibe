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


- Add a copy-as-text button to every read-only decklist, reusing `formatDeckText` (`social-text.ts:15`) so the clipboard gets the TWDA-style text deckbuilders import — done when `DeckDisplay` offers the copy on published finals decks, a member's record and a player's own deck, pasting into VDB's text import reproduces the deck, and it works offline. Reported in gh-46 (a judge on Android could only copy the rendered list, which VDB rejects; "Copy results" carries the winner's deck alone).
