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

- Keep immutable images across deploys: first confirm in Loki whether promo-image bursts follow deploys or new clients, then promo and card images live in a service-worker cache that a new version does not wipe, pruned to the images still in use, and nginx caches versioned promo-image responses so a client's first full prefetch does not mean 253 database reads. **Done when** Loki shows no promo-image surge after a deploy, and `wiki/sync.md`'s Cache Storage paragraph and `wiki/architecture.md`'s promo-image paragraphs describe the new caches.
