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

- Restore the member list the way the viewer left it — `/users` never mirrors its tab to the URL (`frontend/src/routes/users/+page.svelte:23-29`; the tab buttons at `:52`/`:59`/`:66` write nothing back), so browser Back from a member profile lands a filtered viewer on the Community tab, and the two sanction toggles are held in component state alone (`frontend/src/lib/components/UserList.svelte:61-62`) under a comment calling them officials-only (`:49-50`) when their controls render at `:433-452`, outside the `{#if isOfficial}` guard at `:455`, for every signed-in viewer. Mirror the tab the way `/rankings` already does (`frontend/src/routes/rankings/+page.svelte:107-113`) and carry the sanction toggles with it; sponsor and no-VEKN are genuinely officials-only and stay out of the query string. **Done when** a Prince who filters the member list to sanctioned players, opens a profile and hits Back returns to the Members tab with every filter still applied, a shared `/users` URL carries no sponsor or no-VEKN filter, and the list-view-state section of `wiki/design.md` records which filters are excluded and why. gh-11.
- Let a member see and re-download their own playtest NDA after the flow is over — today the record vanishes from their view the moment they leave the page, while every PTC keeps seeing it. The Account tab of their profile lists their NDA records, signed or paper-uploaded, with the signature date and a download of the sealed file, and the signing page shows that same signed state instead of dead-ending on "no pending request". **Done when** a member who has completed the flow can retrieve their copy at any time from their own profile, and the Account-tab bullet in `wiki/design.md`, the NDA-records section of `wiki/architecture.md` and the Members bullet in `wiki/product.md` name the self-facing view.
- Put the drafted question set to the Rules Director on no-final tournaments and record the answer — our engine is rules-literal and awards no winner or finalist rating without a played final, while vekn.net credits a no-final top five exactly like a final. The question that matters most to us is the one the rules do not cover: whether an event that lost its final to force majeure rates at all, since we allow a no-final finish at any size. **Done when** the answers are in `wiki/domain/`, either the engine changes or the no-final note in `wiki/tournaments.md` cites the ruling, and the archon-file importer — which today crowns the top preliminary seat where the engine crowns nobody — is reconciled with it. Context in `board/no-final-rating.md`.
- Give tournament creation a wizard: start from "what kind of event is this" (real-life or online, then size, multideck, decklists, paid or free, offline, big-event options, open/self-organized rounds) and land on a prefilled configuration with inline guidance for the steps the app cannot automate — Discord bot installation, offline mode activation, QR self-check-in, rooms, the paid-registrations CSV import. **Done when** an organizer can create any of the event archetypes through the wizard without touching the raw form, the plain form stays reachable, and `wiki/product.md` and `wiki/design.md` record the flow and pattern (plus `wiki/tournaments.md` if a payment-tracking flag is introduced). Context in `board/creation-wizard.md`.
