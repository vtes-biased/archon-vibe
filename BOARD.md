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
- Give a tournament's player list a CSV export carrying country and region — an organizer tracking a big event has no way to see where registrations are coming from without opening each profile one at a time, and the roster table (`frontend/src/routes/tournaments/[uid]/PlayersTab.svelte:872-897`) is already ten columns at 360px, so the answer is a file rather than more columns. The data is local already: `_USER_MEMBER_FIELDS` gives every VEKN member `country`, `city` and `state` (`backend/src/access_levels.py:50-53`) and only `PlayerInfoMap` discards them (`frontend/src/lib/tournament-utils.ts:30-33`, built at `frontend/src/routes/tournaments/[uid]/+page.svelte:257-264`); reuse `buildCsv`/`downloadCsv` (`frontend/src/lib/promo-csv.ts:2`, `:7`) the way the promo ledger does. **Done when** an organizer can download the roster with each player's name, VEKN id, country and region from Registration onward — not only once standings exist, which is what gates the existing results rows at `ToolsSheet.svelte:233-235` — players with no account degrade to blank cells, and the Tournaments bullet in `wiki/product.md` names the export. gh-13.
- Give the tournament list a championship-rank filter — an organizer hunting National and Continental events has none and browses by hand, though `rank` is already in the client list projection (`frontend/src/lib/db.ts:705`, populated `:723`) and in `_TOURNAMENT_PUBLIC_FIELDS` (`backend/src/access_levels.py:135`), so this is one predicate in `getFilteredTournaments` (`frontend/src/lib/db.ts:849-874`), one select beside the existing format and country ones (`frontend/src/routes/tournaments/+page.svelte:377-401`), and one more key in the URL sync at `:245-250`. Grand Prix is not a value here and must not become one — `wiki/tournaments.md:81-86` puts a GP on the league surface deliberately. **Done when** the list filters to National or Continental championships, the choice survives Back and a shared link like the filters beside it, and the Tournaments bullet in `wiki/product.md` names the filter. gh-17.
- Give tournament creation a wizard: start from "what kind of event is this" (real-life or online, then size, multideck, decklists, paid or free, offline, big-event options, open/self-organized rounds) and land on a prefilled configuration with inline guidance for the steps the app cannot automate — Discord bot installation, offline mode activation, QR self-check-in, rooms, the paid-registrations CSV import. **Done when** an organizer can create any of the event archetypes through the wizard without touching the raw form, the plain form stays reachable, and `wiki/product.md` and `wiki/design.md` record the flow and pattern (plus `wiki/tournaments.md` if a payment-tracking flag is introduced). Context in `board/creation-wizard.md`.
