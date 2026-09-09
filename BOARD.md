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

- Let a player hold a decklist back entirely: a private flag on the deck, set by its owner or an organizer on a deck already submitted and never offered on the upload form, keeps the deck out of publication whatever the decklists mode, so it reaches its organizers and no one else — not other members under All, not the public API or the export once the event is finished — with the winner's deck published regardless so the archive keeps its win registry, and privacy composing with credit rather than replacing it, an anonymous deck still reaching the archive with no owner. Done when a player marks a submitted deck private and a non-owner member and `/v1/decks` see nothing of it on a Finished All-mode event, the organizer still holds it at full, marking an already-published deck private retracts it from the members who held it, a private winner's deck publishes and reaches the TWDA anyway, and `wiki/tournaments.md`, `wiki/product.md`, `wiki/public-api.md` — including the TWD opt-out deferred item narrowed to the winner's deck and name — `wiki/vekn.md` and `wiki/architecture.md` are updated. Context in `board/private-decks.md`.
