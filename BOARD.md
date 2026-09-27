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

- Repair the stuck-VEKN-push recovery script's deck-op branch, which calls the deck processor with an argument it no longer accepts, so the runbook on the VEKN page works the day it is needed. **Done when** the script's deck path runs in dry-run against beta and the runbook in `wiki/vekn.md` is confirmed or corrected.
- Route every write of a member's roles through one helper that pushes Discord Linked Roles and resyncs on an IC/NC change — an admin merge today copies the absorbed account's roles and does neither. **Done when** merge, user edit, detach/link and the roles backfill all call it, no role write bypasses it, the "Role writes have two out-of-band consumers" paragraph in `wiki/hazards.md` is deleted and `wiki/access.md#capabilities` is updated.
- Bring the service worker back to its recorded design: precache the SPA shell so an offline reload of any route works, pass backend-served navigations (auth, OAuth, calendar feeds, the legacy display redirect) straight through, and cache no other navigation response. **Done when** an offline reload of a never-visited route serves the app, Discord login and the calendar feed work on a device the worker controls, the exclusions derive from the list nginx uses, the service-worker paragraph in `wiki/hazards.md` is rewritten to match and the Cache Storage paragraph in `wiki/sync.md` is confirmed. Context: [board/service-worker-design.md](board/service-worker-design.md).
- Enforce "a member with a VEKN id is never soft-deleted" in the one soft-delete function rather than at each caller, and drop the nightly merge's unreachable tombstone branch. **Done when** the soft-delete refuses a VEKN-bearing member, a read-only production query counting such tombstones is parked in `wiki/post-deploy.md`, and the tombstone paragraphs in `wiki/hazards.md` and `wiki/access.md` are deleted or reduced to what that query shows.
- Make the engine reject a decks-payload entry missing its public, winner or private flag instead of reading it as false, so a drifting builder fails loudly rather than republishing or leaking decks. **Done when** a missing flag errors on both the backend and frontend engine calls and the "decks payload is built twice" paragraph in `wiki/hazards.md` shrinks to one line.
- Make lowercase a database rule for email login identifiers. **Done when** a stored-value migration folds any stragglers, a constraint refuses a mixed-case email identifier, and the email paragraph in `wiki/hazards.md` and `wiki/access.md#the-email-of-record` are reduced to the contact-email half.
- Replace go-online's whole-document text replace of temporary player ids with a remap that swaps exact id values only. **Done when** the remap walks the tournament structure and the UUID-length caveat is deleted from `wiki/hazards.md`.
- Guard the public API's two unenforced invariants: a revoked OAuth access token is refused, tested at the endpoint, and the process refuses to boot with more than one worker. **Done when** both exist, the token-revocation paragraph in `wiki/hazards.md` shrinks to the cross-file pointer, and the one-worker paragraph and `wiki/public-api.md#deployment` state it is enforced.
- Tie the signed-in user's carried-forward owner-only fields to the backend's owner-only field set, so a new owner-only field cannot be wiped on sync. **Done when** the frontend list and the backend set cannot disagree without a gate failing and the carry-forward sentence in `wiki/hazards.md` is deleted.
- Save and stamp decks through one helper so no deck frame reaches the broadcast without its organizer stamp. **Done when** every deck writer, the TWDA import included, stamps through it, the org-stamp paragraph in `wiki/hazards.md` shrinks to naming the helper and `wiki/sync.md#broadcast-and-backpressure` is updated.
- Compute the score preview and SetScore's SA/GW/TP cascade through one engine function. **Done when** both call it, the preview/SetScore equality test is deleted and the "deliberately duplicates" paragraph in `wiki/hazards.md` is deleted.
- Export the engine's rounds-played count to the frontend and have the roster and the tournament utilities call it. **Done when** both frontend twins are gone and the "round count computed in three places" paragraph in `wiki/hazards.md` is deleted.
- Remove the backend's in-function imports by resolving the import cycles they work around, keeping only listed exceptions for heavy (over 5MB), rarely-needed (under once a week) libraries such as the PDF generator. **Done when** an unlisted in-function import fails a lint gate stating the rule, the "Lazy imports hide references" paragraph in `wiki/hazards.md` is deleted and `wiki/dev.md#lint-gates` lists the gate. Context: [board/in-function-imports.md](board/in-function-imports.md).
- Catch an edited index definition in CI by applying the current schema over the previous release's and comparing the indexes with a fresh database. **Done when** CI fails on an index changed without its drop and the index paragraph in `wiki/hazards.md` names the check.

