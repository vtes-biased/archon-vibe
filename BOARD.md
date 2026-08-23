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

- Take the disqualification the archive already told us about: a results import reads only a player's position, so vekn.net's own disqualification and withdrawal flags are dropped and that player lands as an ordinary last-placed competitor, keeping the participation rating points a disqualification forfeits and counting as placed in league scoring and on the standings screen. The two import paths also each sort the sheet by a key of their own, neither the engine's, so excluded rows are not parked last and tied rows come out in an order the engine would never produce. **Done when** an imported disqualification or withdrawal carries its flag onto the standings sheet, both imports sort by the engine's rule, and the inbound section of `wiki/vekn.md` and the imported-sheet rules in `wiki/tournaments.md` say so. Context in `board/import-sheet-fidelity.md`.
- Let one place decide whether a player was a finalist: the rating bonus reads it three ways — the backend off the finals table with the roster flag as the round-less fallback, which is the rule the wiki states; the standings screen off the finals table alone; league scoring off the flag alone. Each shortcut is wrong on the shape the other handles, so an event imported as a summary shows its runners-up a rating missing the finalist bonus their own rating page gives them, and a league whose winner carries no finalist flag scores that winner as an also-ran. **Done when** the engine decides it once and all three read that, and the finalist-sourcing rule in `wiki/tournaments.md` and the twins paragraph in `wiki/hazards.md` name one source instead of three. Context in `board/finalist-position-twins.md`.
- Put the drafted question set to the Rules Director on no-final tournaments and record the answer — our engine is rules-literal and awards no winner or finalist rating without a played final, while vekn.net credits a no-final top five exactly like a final. The question that matters most to us is the one the rules do not cover: whether an event that lost its final to force majeure rates at all, since we allow a no-final finish at any size. **Done when** the answers are in `wiki/domain/`, either the engine changes or the no-final note in `wiki/tournaments.md` cites the ruling, and the archon-file importer — which today crowns the top preliminary seat where the engine crowns nobody — is reconciled with it. Context in `board/no-final-rating.md`.
- Finish the production cutover's post-flip steps: install the Discord bot on the production guild(s), set the portal redirect URIs, ToS and privacy URLs and the Linked Roles Verification URL for archon.vekn.net, then run the improved dedup on production (`--probe-vekn`, review, `--apply`) and tell the waiting organizer his event can be finished. **Done when** the bot is installed, the portal is configured, the dedup is applied and the organizer has been contacted. Context in `board/prod-migration.md`.
- Decommission legacy archon: final `pg_dump` archive of `archondb`, remove the `archon_web` systemd unit, archive the old repository read-only, cold-store the `tournament_events` dump, and retire the `new.` hostnames — the hand-edited 302 vhost, its certbot cert and its DNS A record, on both archon.vekn.net and krcg.org. **Done when** none of those exist and the archive is stored. Context in `board/prod-migration.md`.
- Put the public API online on beta: the daemon grant, the `public_api` ansible role, its cert and its throttled vhost are written and unrun, so what is left is the `api.archon.krcg.org` A record, a full (not quick-lane) beta deploy, and the verification — register an `api:read` client, mint a daemon token with it, read one full refresh unthrottled, see a tight loop of them refused with 429, and see the same token rejected by the app. **Done when** the beta API answers a daemon token and the throttle has been observed. Context in `board/public-api.md`.
