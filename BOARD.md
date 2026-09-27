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

- Make the engine reject a decks-payload entry missing its public, winner or private flag instead of reading it as false, so a drifting builder fails loudly rather than republishing or leaking decks. **Done when** a missing flag errors on both the backend and frontend engine calls and the "decks payload is built twice" paragraph in `wiki/hazards.md` shrinks to one line.
- Guard the public API's two unenforced invariants: a revoked OAuth access token is refused, tested at the endpoint, and the process refuses to boot with more than one worker. **Done when** both exist, the token-revocation paragraph in `wiki/hazards.md` shrinks to the cross-file pointer, and the one-worker paragraph and `wiki/public-api.md#deployment` state it is enforced.
- Tie the signed-in user's carried-forward owner-only fields to the backend's owner-only field set, so a new owner-only field cannot be wiped on sync. **Done when** the frontend list and the backend set cannot disagree without a gate failing and the carry-forward sentence in `wiki/hazards.md` is deleted.
- Save and stamp decks through one helper so no deck frame reaches the broadcast without its organizer stamp. **Done when** every deck writer, the TWDA import included, stamps through it, the org-stamp paragraph in `wiki/hazards.md` shrinks to naming the helper and `wiki/sync.md#broadcast-and-backpressure` is updated.
- Compute the score preview and SetScore's SA/GW/TP cascade through one engine function. **Done when** both call it, the preview/SetScore equality test is deleted and the "deliberately duplicates" paragraph in `wiki/hazards.md` is deleted.
- Export the engine's rounds-played count to the frontend and have the roster and the tournament utilities call it. **Done when** both frontend twins are gone and the "round count computed in three places" paragraph in `wiki/hazards.md` is deleted.
- Remove the backend's in-function imports by resolving the import cycles they work around, keeping only listed exceptions for heavy (over 5MB), rarely-needed (under once a week) libraries such as the PDF generator. **Done when** an unlisted in-function import fails a lint gate stating the rule, the "Lazy imports hide references" paragraph in `wiki/hazards.md` is deleted and `wiki/dev.md#lint-gates` lists the gate. Context: [board/in-function-imports.md](board/in-function-imports.md).

