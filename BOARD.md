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

- Run the Hall of Fame rebuild against production — the archive sync, the reconstruction of the 1130 unlinked events and the new win rule are built and green, but the reference counts stay wrong until the archive actually reaches the corpus: regenerate the decisions file against prod, apply the backfill, and diff Hall of Fame membership either side of it, since 47 members sit at exactly five wins and a silent eviction is a support ticket with a name on it. gh-7, a player comparing us against vekn.fr/hall_of_fame.htm. **Done when** the backfill is applied and Watras/Izydorczyk/Pietkiewicz read 19/12/9 on the live site. The runbook is `board/twda-hof.md` — read that, not this line.
- Stop a detached account from walking away with promo stock it does not hold — splitting an account leaves the VEKN record holding its uid and with it every ledger entry that earns the stock, but the fresh personal record inherits a copy of the stock dictionary, so two accounts show the same inventory until a nightly recompute clears the one that owns none. Community links and promo stock both stay with the VEKN record. **Done when** a detached personal account holds no promo stock, `wiki/architecture.md` states that links and stock both stay with the VEKN record, and `wiki/hazards.md` carries the personal-side clear-list as the inverse of the null-list it already names.
- Fix the organizer's event-copy download by producing it where the data already lives — the button navigates to a backend endpoint that authenticates on a bearer header an anchor navigation never sends, so it answers 401 to every organizer who clicks it, and no test covers it; its text format has no caller at all; and both formats render from a tournament, its users and its winner's deck, every one of which the organizer's device already holds offline. The engine's canonical TWDA library ordering has to reach the frontend for the deck half, which also retires the two copies of it living there. **Done when** the event copy is generated client-side from local data, the engine owns the deck ordering and every copy outside it is gone, the endpoint and the five hand-mirrored formatting helpers only it used are deleted while the TWDA renderer the submitter shares stays, and `wiki/architecture.md` and `wiki/design.md` record that the export is client-side.
- Put the drafted question set to the Rules Director on no-final tournaments and record the answer — our engine is rules-literal and awards no winner or finalist rating without a played final, while vekn.net credits a no-final top five exactly like a final. The question that matters most to us is the one the rules do not cover: whether an event that lost its final to force majeure rates at all, since we allow a no-final finish at any size. **Done when** the answers are in `wiki/domain/`, and either the engine changes or the no-final note in `wiki/tournaments.md` cites the ruling. Context in `board/no-final-rating.md`.
- Finish the production cutover's post-flip steps: install the Discord bot on the production guild(s), set the portal redirect URIs, ToS and privacy URLs and the Linked Roles Verification URL for archon.vekn.net, then run the improved dedup on production (`--probe-vekn`, review, `--apply`) and tell the waiting organizer his event can be finished. **Done when** the bot is installed, the portal is configured, the dedup is applied and the organizer has been contacted. Context in `board/prod-migration.md`.
- Decommission legacy archon: final `pg_dump` archive of `archondb`, remove the `archon_web` systemd unit, archive the old repository read-only, cold-store the `tournament_events` dump, and retire the `new.` hostnames — the hand-edited 302 vhost, its certbot cert and its DNS A record, on both archon.vekn.net and krcg.org. **Done when** none of those exist and the archive is stored. Context in `board/prod-migration.md`.
- Stamp the short event code across the production corpus — every tournament minted from now on gets one, and a short URL, the TWDA submission and every shared link already key on it, but the 8475 rows that predate the change carry none and fall back to the 36-character uuid. It must run **after** the archive backfill above: a reconstruction takes the archive's own key as its code, a code is never rewritten, and one stamped early keeps a minted code instead of the one the TWDA publishes for it. **Done when** `backfill_event_codes.py` has been reviewed and applied on production and every live tournament carries a code. Context in `board/short-event-id.md`.
- Let the engine decide the standings the app displays — the preliminary sort cascade, the disqualification zeroing and the combined disqualified-or-proxy signal are written twice, once in the engine and again in the frontend, and for a round-less VEKN import the frontend's copy is the only one that runs, so the whole historic corpus is ranked by a rule the engine does not own. The export has to rank a result sheet it is handed rather than recompute one from rounds, or it breaks the guard that protects imported history. **Done when** the engine exports the standings the display path needs, the frontend marshals instead of computing, no copy of the cascade or the zeroing survives outside the engine, and `wiki/tournaments.md` and `wiki/architecture.md` say where the display path computes.
