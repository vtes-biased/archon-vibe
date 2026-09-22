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

- Let an organizer find a player on demand. Players tab: the add-player field's "already registered" match becomes a way to jump to that player, not a greyed-out row: tapping it scrolls to their roster row and highlights it, clearing any filter hiding it, and registered matches rank first. Rounds tab: a search icon opens a field over the event's own players, each result showing its table and seat in the latest round they sit in; tapping one opens that round and highlights the seat, hiding nothing. **Done when:** typing "jose" in the add-player field of a 40-player event with a common-name member base lists the registered José first, and tapping him scrolls to his highlighted row; on the Rounds tab the same search reads "Table 4, seat 2" and tapping it opens his round on the highlighted seat; and `wiki/design.md` ("Unactionable match" reworded from addable to actionable; the workbench noting the Rounds search icon) says so.
- Let an IC anonymize a member holding a VEKN id, as the counterpart of marking one deceased: it wipes name, nickname, contact, city, avatar and sign-in methods, stamps when and by whom, and locks the wiped fields against the VEKN member sync. VEKN id, country, results, ratings, wins and sanctions stay attached, and the member shows as "Anonymized member" everywhere a name appears. Irreversible; never pushed to VEKN. Past TWDA archive credits are out of scope. **Done when:** after an IC anonymizes a member, that member's profile, the members list, rankings, standings and decklists read "Anonymized member" on every device; no other member's sync carries the old name or contact; the next VEKN member sync leaves the record anonymized; the old sign-in no longer logs in; and `wiki/architecture.md` (Account surgery), `wiki/access.md`, `wiki/sync.md` (user row) and `wiki/product.md` (directory) say so.
- Show a deck's comment under its name on the deck view and make it editable in the deck editor, for the owner and for organizers under the same rules as the rest of the list. It is already filled from the deckbuilder's description on link import, kept from pasted text and written to the TWDA entry; today it is never shown and the editor can't change it. It follows the deck's own visibility. **Done when:** a deck imported from a VDB link that has a description shows that text on the deck view; the owner and an organizer can each change it and the change reaches the other's device; the finished event's TWDA entry carries the edited text; and `wiki/product.md` (Decks) names the comment.
