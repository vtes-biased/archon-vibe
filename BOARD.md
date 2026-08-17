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

- Rebuild the Hall of Fame from a direct TWDA sync so career counts match the reference page — gh-7, a player comparing us against vekn.fr/hall_of_fame.htm; we list one of his four names at 5+ wins where the archive holds 1. Six sequenced phases, the first two read-only reconciliation that gate the rest. **Done when** the HoF is derived from TWDA-recorded wins and Watras/Izydorczyk/Pietkiewicz read 19/12/9. The plan is `board/twda-hof.md` — read that, not this line.
- Make the review gate bite: every finding the reviewer returns gets addressed, and comment bloat becomes one of them — advisory findings are currently reported and dropped, so the reviewer's standing power to delete narration comments has never once fired, and a recent change added 58 comment lines against 304 of code with the rationale duplicated into the wiki page it updated in the same commit. Report-everything must not become find-something: "looks good" stays a common verdict. **Done when** the reviewer runs a named comment pass that demands deletion of any comment the wiki or another comment already states, `just lint` fails on a contiguous inline comment block over three lines in the three source trees, the ship loop no longer permits dropping a finding, and `wiki/dogmas.md` and `wiki/dev.md` say so.
- Put the drafted question set to the Rules Director on no-final tournaments and record the answer — our engine is rules-literal and awards no winner or finalist rating without a played final, while vekn.net credits a no-final top five exactly like a final. The question that matters most to us is the one the rules do not cover: whether an event that lost its final to force majeure rates at all, since we allow a no-final finish at any size. **Done when** the answers are in `wiki/domain/`, and either the engine changes or the no-final note in `wiki/tournaments.md` cites the ruling. Context in `board/no-final-rating.md`.
- Break ties for every one of the top five finals rankings, not only the cutoff — rules §3.1 resolves remaining ties for *any* top-five ranking randomly, and qualifier rank drives the finals seating ritual (§3.1.3, lowest qualifier places first), so an unbroken tie inside the top five leaves the seating order under-determined. **Done when** `RandomToss` resolves intra-top-5 ties and the finals seed order is total.
- Fold accented letters to ASCII in the frontend's search normaliser — `normalizeSearch` strips combining marks only, so the eleven letters that do not decompose (ł, ø, æ, ß …) survive and a query for `Pawel` finds no `Paweł` across member, card and city search. The backend and the engine both hold the correct map; the engine's is private and not WASM-exported, which is why a third implementation drifted. **Done when** the ASCII spelling resolves the accented record in all four search surfaces, and the standing-defect note in `wiki/hazards.md` is gone.
- Finish the production cutover's post-flip steps: install the Discord bot on the production guild(s), set the portal redirect URIs, ToS and privacy URLs and the Linked Roles Verification URL for archon.vekn.net, then run the improved dedup on production (`--probe-vekn`, review, `--apply`) and tell the waiting organizer his event can be finished. **Done when** the bot is installed, the portal is configured, the dedup is applied and the organizer has been contacted. Context in `board/prod-migration.md`.
- Decommission legacy archon: final `pg_dump` archive of `archondb`, remove the `archon_web` systemd unit, archive the old repository read-only, cold-store the `tournament_events` dump, and retire the `new.` hostnames — the hand-edited 302 vhost, its certbot cert and its DNS A record, on both archon.vekn.net and krcg.org. **Done when** none of those exist and the archive is stored. Context in `board/prod-migration.md`.
- Warn an organizer who sets a round time under two hours — the rules put a two-hour floor on a round (§3.1.1) and JG §5.2 unsanctions the event if a round shorter than that has any table end on time being called. A warning, not a block: the timer is optional, a short round that finishes early stays sanctioned, and the organizer may have a reason. **Done when** setting `round_time` or `finals_time` below 7200s shows the warning, saving still succeeds, and the two-hour-floor note in `wiki/architecture.md` reflects the warning.
- Give every tournament a short human-readable code a player can read out and an external record can cite — the VEKN event id is that identifier today (`12794` names the TWDA file, the forum post and the vekn.net URL) and the decommission retires it, leaving a 36-character uuid as the only handle. A uuid prefix cannot stand in: uuid7 is time-ordered, so our 8475 tournaments yield only 336 distinct 8-character prefixes. This line also carries TWDA submission continuity, which has no other home: the branch and file names key on the vekn event id and the submitter skips outright without one, so the decommission would silently end archive submissions. **Done when** every tournament carries a unique short code, a short URL resolves to it, a finished tournament with no vekn event id still reaches the TWDA citing that code instead of the uuid, and `wiki/architecture.md`, `wiki/sync.md` and `wiki/vekn.md` reflect it. Context in `board/short-event-id.md`.
- Show a dismissible "what changed" modal on first load after an upgrade, sourced from `CHANGELOG.md` — the changelog is developer-facing and a player never sees it. Never on a first-ever visit; nothing when there are no unseen entries. Resolve first whether changelog entries are translated or stay English inside a translated shell. **Done when** a user who loaded a newer build sees only the entries they have not seen.
