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

- Give attribution its own type, its own event and a real boundary: one typed credit — anonymous, the owner, a member by VEKN id, a named non-member, or the archive — replaces the author and attribution strings, an owner-only SetDeckAttribution event changes it in any state without touching the deck, the upload form uses the shared attribution picker, and an anonymous published deck reaches other members and the public API with no owner, the winner's deck excepted, so a profile lists to others only decks that name their owner, Finalists mode names the winner and no anonymous finalist, and the public API carries member credits only, never a free-text name. Done when an owner changes attribution during play and after finish, an anonymous published deck arrives at a non-owner member and at the public API without an owner identifier and the client keys it on the deck itself, another member's profile shows none of their anonymous decks, the TWDA credit line and every deck display resolve from the typed field, production's stored rows are migrated and its published decks re-projected, and `wiki/architecture.md`, `wiki/tournaments.md`, `wiki/vekn.md`, `wiki/public-api.md`, `wiki/sync.md`, `wiki/product.md` and `wiki/post-deploy.md` are updated. Context in `board/deck-attribution.md`.
