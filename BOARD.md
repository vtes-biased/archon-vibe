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
- Let the seating editor decide who is in the round — an organizer who seats round 1 and then finds absent players at the tables cannot fix it without leaving "Alter seating", because the event behind it only ever rearranges a fixed player set. Make the submitted seating authoritative: the engine diffs it against the round and does the seating and unseating itself, refusing only the structurally impossible — an unknown player, a duplicate, an illegal table size — and never a player state, since every state it might bar is reachable by another route anyway. Player states move on one promotion and one demotion rule, and `UnseatPlayer` adopts the same demotion, which today reinstates a player who dropped out and strands one still playing a parallel round. Reported by a player who had used Check All In. **Done when** alter seating can add and remove players and save in one action, the demotion rule's three cases are covered at the engine interface, and the events table in `wiki/tournaments.md` describes the new contract. Context in `board/alter-seating-player-set.md`.
- Put the drafted question set to the Rules Director on no-final tournaments and record the answer — our engine is rules-literal and awards no winner or finalist rating without a played final, while vekn.net credits a no-final top five exactly like a final. The question that matters most to us is the one the rules do not cover: whether an event that lost its final to force majeure rates at all, since we allow a no-final finish at any size. **Done when** the answers are in `wiki/domain/`, and either the engine changes or the no-final note in `wiki/tournaments.md` cites the ruling. Context in `board/no-final-rating.md`.
- Finish the production cutover's post-flip steps: install the Discord bot on the production guild(s), set the portal redirect URIs, ToS and privacy URLs and the Linked Roles Verification URL for archon.vekn.net, then run the improved dedup on production (`--probe-vekn`, review, `--apply`) and tell the waiting organizer his event can be finished. **Done when** the bot is installed, the portal is configured, the dedup is applied and the organizer has been contacted. Context in `board/prod-migration.md`.
- Decommission legacy archon: final `pg_dump` archive of `archondb`, remove the `archon_web` systemd unit, archive the old repository read-only, cold-store the `tournament_events` dump, and retire the `new.` hostnames — the hand-edited 302 vhost, its certbot cert and its DNS A record, on both archon.vekn.net and krcg.org. **Done when** none of those exist and the archive is stored. Context in `board/prod-migration.md`.
- Stamp the short event code across the production corpus — every tournament minted from now on gets one, and a short URL, the TWDA submission and every shared link already key on it, but the 8475 rows that predate the change carry none and fall back to the 36-character uuid. It must run **after** the archive backfill above: a reconstruction takes the archive's own key as its code, a code is never rewritten, and one stamped early keeps a minted code instead of the one the TWDA publishes for it. **Done when** `backfill_event_codes.py` has been reviewed and applied on production and every live tournament carries a code. Context in `board/short-event-id.md`.
- Make an in-app notification readable on a phone — an announcement arriving mid-event paints the muted surface over the app's own muted surface, so it lands grey on grey, and the toast strip is inset from the right edge only, leaving the card flush against the left of the screen. The palette already rules that info is azure and that status colour travels through a `toast-*` class; this one reaches past both. **Done when** an announcement toast reads at the palette's azure on a 360-pixel viewport with equal insets on both edges, and every toast type resolves through a `toast-*` class.
