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
- Sign JWTs asymmetrically so the public API cannot mint them: the app signs with a private key (EdDSA), the public API and any other verifier hold only the public half, and tokens carry `aud` naming the surface they are for and `kid` so a key can be rotated without invalidating every live session. Today one shared `JWT_SECRET` under HS256 gives the internet-facing read service — which never signs anything, since `/oauth/token` proxies to the app's backend — the power to forge first-party session tokens for any user; both processes share a host today, so this is defence in depth rather than a live hole. Fold in the public API's missing default-secret boot guard, which the app has at `main.py:351` and the API's own lifespan does not, and a tighter `limit_req_zone` for `= /oauth/token`, whose Argon2 verify sits in the generic 600 r/m read zone. **Done when** the app signs with a private key, the public API verifies with the public one and refuses to boot on a default or absent key, `aud` and `kid` are issued and checked, and `wiki/access.md`'s security paragraph and the two-implementations hazard entry record the split.
- Finish the production cutover's post-flip steps: install the Discord bot on the production guild(s), set the portal redirect URIs, ToS and privacy URLs and the Linked Roles Verification URL for archon.vekn.net, then run the improved dedup on production (`--probe-vekn`, review, `--apply`) and tell the waiting organizer his event can be finished. **Done when** the bot is installed, the portal is configured, the dedup is applied and the organizer has been contacted. Context in `board/prod-migration.md`.
- Give tournament creation a wizard: start from "what kind of event is this" (real-life or online, then size, multideck, decklists, paid or free, offline, big-event options, open/self-organized rounds) and land on a prefilled configuration with inline guidance for the steps the app cannot automate — Discord bot installation, offline mode activation, QR self-check-in, rooms, the paid-registrations CSV import. **Done when** an organizer can create any of the event archetypes through the wizard without touching the raw form, the plain form stays reachable, and `wiki/product.md` and `wiki/design.md` record the flow and pattern (plus `wiki/tournaments.md` if a payment-tracking flag is introduced). Context in `board/creation-wizard.md`.
