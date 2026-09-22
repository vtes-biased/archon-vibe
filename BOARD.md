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

- Make a backend restart serve within seconds: only a pending stored-value migration may hold the process before it serves, and its guard runs on the relaxed batch timeout so a slow cold-cache scan can no longer fail startup; event-code stamping and Discord Linked Roles registration move behind the first request like the VEKN sync already is; and the member sync's co-opted-by inference reads through the batch connection instead of timing out. Measure the cold start from process start to first answer, including the import time before startup begins. **Done when:** a cold `systemctl restart` on beta answers the API and accepts an SSE reconnection within 10 s of the process starting, with nothing but schema load ahead of serving when no migration is pending; the next prod VEKN member sync logs co-opted-by inference completing; and `wiki/architecture.md` (stored-value migrations, background jobs) and `wiki/hazards.md` (the migration paragraph) say so.
- Let an IC anonymize a member holding a VEKN id, as the counterpart of marking one deceased: it wipes name, nickname, contact, city, avatar and sign-in methods, stamps when and by whom, and locks the wiped fields against the VEKN member sync. VEKN id, country, results, ratings, wins and sanctions stay attached, and the member shows as "Anonymized member" everywhere a name appears. Irreversible; never pushed to VEKN. Past TWDA archive credits are out of scope. **Done when:** after an IC anonymizes a member, that member's profile, the members list, rankings, standings and decklists read "Anonymized member" on every device; no other member's sync carries the old name or contact; the next VEKN member sync leaves the record anonymized; the old sign-in no longer logs in; and `wiki/architecture.md` (Account surgery), `wiki/access.md`, `wiki/sync.md` (user row) and `wiki/product.md` (directory) say so.
- Show a deck's comment under its name on the deck view and make it editable in the deck editor, for the owner and for organizers under the same rules as the rest of the list. It is already filled from the deckbuilder's description on link import, kept from pasted text and written to the TWDA entry; today it is never shown and the editor can't change it. It follows the deck's own visibility. **Done when:** a deck imported from a VDB link that has a description shows that text on the deck view; the owner and an organizer can each change it and the change reaches the other's device; the finished event's TWDA entry carries the edited text; and `wiki/product.md` (Decks) names the comment.
