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

- Put the drafted question set to the Rules Director on no-final tournaments and record the answer — our engine is rules-literal and awards no winner or finalist rating without a played final, while vekn.net credits a no-final top five exactly like a final. The question that matters most to us is the one the rules do not cover: whether an event that lost its final to force majeure rates at all, since we allow a no-final finish at any size. **Done when** the answers are in `wiki/domain/`, either the engine changes or the no-final note in `wiki/tournaments.md` cites the ruling, and the archon-file importer — which today crowns the top preliminary seat where the engine crowns nobody — is reconciled with it. Context in `board/no-final-rating.md`.
- Finish the production cutover's post-flip steps: install the Discord bot on the production guild(s), set the portal redirect URIs, ToS and privacy URLs and the Linked Roles Verification URL for archon.vekn.net, then run the improved dedup on production (`--probe-vekn`, review, `--apply`) and tell the waiting organizer his event can be finished. **Done when** the bot is installed, the portal is configured, the dedup is applied and the organizer has been contacted. Context in `board/prod-migration.md`.
- Document "Login with Archon" for third-party apps in the public API reference, which today explains only the daemon grant: the authorization-code + PKCE walk-through from client registration in the profile's Developer section through `/consent`, `/oauth/token`, `/oauth/userinfo`, refresh rotation and `/oauth/revoke`, with the consent weight of `profile:read` versus `user:impersonate` stated plainly, plus a recipe section naming what `/v1` already serves a deck-archive or statistics app (`/v1/decks`, `/v1/export`) and its publication contract — decks appear only once an event finishes, per its `decklists_mode`, and a reopen withdraws them. **Done when** the `/docs` description carries the flow end to end with a runnable example per step, the recipe names the deck endpoints and the finished-only contract, and `wiki/public-api.md`'s docs section reflects the added coverage.
- Give tournament creation a wizard: start from "what kind of event is this" (real-life or online, then size, multideck, decklists, paid or free, offline, big-event options, open/self-organized rounds) and land on a prefilled configuration with inline guidance for the steps the app cannot automate — Discord bot installation, offline mode activation, QR self-check-in, rooms, the paid-registrations CSV import. **Done when** an organizer can create any of the event archetypes through the wizard without touching the raw form, the plain form stays reachable, and `wiki/product.md` and `wiki/design.md` record the flow and pattern (plus `wiki/tournaments.md` if a payment-tracking flag is introduced). Context in `board/creation-wizard.md`.
- Bind the player guide's mockups to the app the way the organizer guide's now are: every control the real `Button`/`Badge`/`InlineNotice`, every label the same `m.*()` key the live screen renders, so a reworded label or a restyled primitive moves the drawing with it. Its ~100 hand-built controls and labels are why `scripts/check_help_mockups.py` still exempts the file. **Done when** `PlayerGuide.svelte` is out of that script's `EXEMPT_FILES` and `just help-mockups` passes with the exemption gone.
