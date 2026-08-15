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

**Hard limit: 15 active lines.** Adding a sixteenth forces a drop or a promotion to
the wiki. Triggered lines below the marker are exempt from the cap.

**Every line must be completable** — if "done" cannot be stated, it is a subject:
promote it to a [wiki](wiki/index.md) page and delete the line. Context lives in
the wiki; asks live here. Bulky context for an in-flight line goes in
`board/<slug>.md`, deleted with the line.

Board changes ride the commit that earns them.

## Active

- Rebuild the Hall of Fame from a direct TWDA sync so career counts match the reference page — gh-7, a player comparing us against vekn.fr/hall_of_fame.htm; we list one of his four names at 5+ wins where the archive holds 1. Six sequenced phases, the first two read-only reconciliation that gate the rest. **Done when** the HoF is derived from TWDA-recorded wins and Watras/Izydorczyk/Pietkiewicz read 19/12/9. The plan is `board/twda-hof.md` — read that, not this line.
- Stop the tournament config auto-save chip hiding behind the mobile bottom nav — `sticky bottom-4` with no z-index parks it 16px above the *viewport* bottom, because sticky resolves against the scrollport rather than the app shell. **Done when** the chip clears the nav on a phone, deriving its offset from `--spacing-navbar` rather than a hard-coded value.
- Stop tall centred modals clipping their own header under the status bar in the installed PWA, and finish the half-done `vh` → `dvh` migration. Since `viewport-fit=cover` landed, a `max-h-[90vh]` panel centred on an 852pt iPhone leaves less clearance above it than the status bar needs. **Done when** no modal header sits under the status bar in standalone mode, and no `vh` unit remains where `dvh` is meant.
- Reconcile app tournaments against the vekn.net API record and write the diff to `board/`, **before the API is retired** — the comparison needs a reachable API and can never be reconstructed afterwards, so this runs before the cleanup it feeds. One targeted `fetch_event` per tournament carrying `external_ids['vekn']`, never the bulk sweep. **Done when** a reviewed table exists with, per row, the vekn id, the app tournament, its state/rounds/players, and a verdict of confirmed-absent / still-live / unverifiable. Read-only; deletes nothing.
- Put the drafted question set to the Rules Director on no-final tournaments and record the answer — our engine is rules-literal and awards no winner or finalist rating without a played final, while vekn.net credits a no-final top five exactly like a final. The question that matters most to us is the one the rules do not cover: whether an event that lost its final to force majeure rates at all, since we allow a no-final finish at any size. **Done when** the answers are in `wiki/domain/`, and either the engine changes or the no-final note in `wiki/tournaments.md` cites the ruling. Context in `board/no-final-rating.md`.
- Make a Standings Adjustment issuable before round 1 pairings, applying to round 1 — JG v2 §1.1.3 defines that case explicitly and the backend refuses it, requiring an existing round. **Done when** an SA issued on a tournament with no rounds lands on round 1 once it is seated, with one engine test pinning it.
- Break ties for every one of the top five finals rankings, not only the cutoff — rules §3.1 resolves remaining ties for *any* top-five ranking randomly, and qualifier rank drives the finals seating ritual (§3.1.3, lowest qualifier places first), so an unbroken tie inside the top five leaves the seating order under-determined. **Done when** `RandomToss` resolves intra-top-5 ties and the finals seed order is total.
- Issue the accompanying Warning when a Disqualification is issued — JG v2 §1.1.4: "a DQ always includes a Warning", so the player's permanent record is currently one entry short. **Done when** a DQ creates both sanctions and lifting the DQ leaves the Warning standing.
- Let an archival result carry a player count without a roster, and make an archival record correctable in-app — we cannot express "42 players, roster unknown" today, so a rounds-less import has no field size and the rating coefficient has nothing to work from. Blocks the Hall of Fame's later phases. **Done when** a rounds-less tournament can hold an attested player count, that count feeds the rating coefficient, and an official can correct an archival record without a script. Beware: `player_count` is already taken as a key by league scoring (`wiki/hazards.md`).
- Decide and write down what decommissioning the VEKN API means, and name the trigger the lines below wait on — the two live read syncs (tournament calendar, member roster) are what make several problems unfixable, since anything deleted or diverged locally is re-created on their next run. The push direction is a separate decision and must be settled explicitly rather than assumed to follow. **Done when** `wiki/vekn.md` states which syncs retire and when, and each triggered line below names that condition.
- Finish the production cutover's post-flip steps: install the Discord bot on the production guild(s), set the portal redirect URIs, ToS and privacy URLs and the Linked Roles Verification URL for archon.vekn.net, then run the improved dedup on production (`--probe-vekn`, review, `--apply`) and tell the waiting organizer his event can be finished. **Done when** the bot is installed, the portal is configured, the dedup is applied and the organizer has been contacted. Context in `board/prod-migration.md`.
- Decommission legacy archon: final `pg_dump` archive of `archondb`, remove the `archon_web` systemd unit, archive the old repository read-only, cold-store the `tournament_events` dump, and retire the `new.` hostnames — the hand-edited 302 vhost, its certbot cert and its DNS A record, on both archon.vekn.net and krcg.org. **Done when** none of those exist and the archive is stored. Context in `board/prod-migration.md`.
- Redesign the organizer console as a workbench: state owns the surface, one button budget per surface, say it once. **Done when** each of the seven reviewed screens satisfies the three rules. Context in `board/console-redesign.md`.
- Warn an organizer who sets a round time under two hours — the rules put a two-hour floor on a round (§3.1.1) and JG §5.2 unsanctions the event if a round shorter than that has any table end on time being called. A warning, not a block: the timer is optional, a short round that finishes early stays sanctioned, and the organizer may have a reason. **Done when** setting `round_time` or `finals_time` below 7200s shows the warning and saving still succeeds.
- Show a dismissible "what changed" modal on first load after an upgrade, sourced from `CHANGELOG.md` — the changelog is developer-facing and a player never sees it. Never on a first-ever visit; nothing when there are no unseen entries. Resolve first whether changelog entries are translated or stay English inside a translated shell. **Done when** a user who loaded a newer build sees only the entries they have not seen.

## Triggered

Waiting on an external green light, not on us. Exempt from the hard limit and from
eviction; re-checked at each maintenance pass for whether the trigger has fired,
and promoted into the list above when it has.

- Clean up the remaining all-live duplicate tournaments — one real event entered twice on vekn.net with both vekn ids live. Soft-delete plus vekn-id transplant is the recipe, but while the tournament sync is an upstream it re-creates whatever we delete. **Done when** each group in `board/duplicate-tournaments.md` has one live copy. `[TRIGGER: VEKN tournament sync retired]`
- Give ICs a cleanup capability that can delete or withdraw a tournament regardless of its VEKN footprint, and decide whether organizers regain any deletion right on VEKN-linked events. Origin gh-6, a Prince asking how to remove an event created by mistake. **Do not re-derive the rejected probe-at-delete approach** — it was fully built and reverted. **Done when** an IC can remove a mistaken event, every entry in `board/post-decommission-deletes.md` is gone, and the frontend no longer offers Delete on an offline-locked tournament, which the API refuses today. `[TRIGGER: VEKN tournament sync retired]`
- Review the Prince/NC divergence between legacy archon and the app and record the outcome — the census in `board/prince-nc-divergence.md` shows 27 Princes in legacy only and 34 in the app only, diverging in both directions, so only a human who knows the appointments can tell a genuine loss from someone who stepped down. A blind union would republish superseded officials' contact details publicly and seat two coordinators in two countries. **Done when** each divergent name has a verdict and the roles match it. `[TRIGGER: VEKN API decommissioned and the record settled]`
- Keep TWDA submission alive after the VEKN API decommission — the branch and file names key on the vekn event id and the submitter skips outright without one, so decommissioning silently ends archive submissions. **Done when** a finished tournament with no vekn event id still reaches the TWDA. `[TRIGGER: VEKN API decommission scope decided]`
- Bump TypeScript 6 → 7. **Done when** `npm ls` is clean and `svelte-check` passes on TS 7. `[TRIGGER: SvelteKit and svelte-check ship TS 7 support]`
- Drop the two dead IndexedDB indexes — `decks.by-user` and `users.by-country-name`, both declared with zero consumers — and update the index table in `wiki/sync.md` in the same change. Removing an index needs a `DB_VERSION` bump, which forces a full client resync, so it rides the next one rather than forcing its own. **Done when** neither index is created. `[TRIGGER: next DB_VERSION bump]`
