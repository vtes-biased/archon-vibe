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

- Show a deck's comment under its name on the deck view and make it editable in the deck editor, for the owner and for organizers under the same rules as the rest of the list. It is already filled from the deckbuilder's description on link import, kept from pasted text and written to the TWDA entry; today it is never shown and the editor can't change it. It follows the deck's own visibility. **Done when:** a deck imported from a VDB link that has a description shows that text on the deck view; the owner and an organizer can each change it and the change reaches the other's device; the finished event's TWDA entry carries the edited text; and `wiki/product.md` (Decks) names the comment.
