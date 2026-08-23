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

- Report the actual tournament winner to vekn.net: the results push sends preliminary standings order as the archon file's placement field, so vekn.net crowns the top seed whenever the final was won from a lower seat — and its rating batch then hands that player the winner's rating points. Event 13385 carries the wrong name today. Take the placement from the engine's final-standings rule, which already knows winner-first, and give disqualified and withdrawn players the archive's own DQ/WD flags instead of a number. **Done when** a finals win from a lower seat pushes that player at position 1, the format section of `wiki/vekn.md` says the field is the final placement, and `wiki/hazards.md` lists the push among the consumers of a placement. Context in `board/vekn-winner-position.md`.
- Put the drafted question set to the Rules Director on no-final tournaments and record the answer — our engine is rules-literal and awards no winner or finalist rating without a played final, while vekn.net credits a no-final top five exactly like a final. The question that matters most to us is the one the rules do not cover: whether an event that lost its final to force majeure rates at all, since we allow a no-final finish at any size. **Done when** the answers are in `wiki/domain/`, and either the engine changes or the no-final note in `wiki/tournaments.md` cites the ruling. Context in `board/no-final-rating.md`.
- Finish the production cutover's post-flip steps: install the Discord bot on the production guild(s), set the portal redirect URIs, ToS and privacy URLs and the Linked Roles Verification URL for archon.vekn.net, then run the improved dedup on production (`--probe-vekn`, review, `--apply`) and tell the waiting organizer his event can be finished. **Done when** the bot is installed, the portal is configured, the dedup is applied and the organizer has been contacted. Context in `board/prod-migration.md`.
- Decommission legacy archon: final `pg_dump` archive of `archondb`, remove the `archon_web` systemd unit, archive the old repository read-only, cold-store the `tournament_events` dump, and retire the `new.` hostnames — the hand-edited 302 vhost, its certbot cert and its DNS A record, on both archon.vekn.net and krcg.org. **Done when** none of those exist and the archive is stored. Context in `board/prod-migration.md`.
- Say once what a member's email address actually is: `contact_email` is the account's email of record — the key that door-dedup, the account merge, the reset for someone who never had a password, and the VEKN registry push all read — and not an address the member chose to publish, which is how its name reads and how it is treated once its holder becomes NC or Prince. Fix the one place that disagrees: resolving an offline player matches the email auth method case-sensitively against identifiers that are stored lowercased, so a hand-typed mixed-case address at the venue misses a member who holds a login but no contact address. **Done when** the offline resolution normalizes the address once instead of at each of its call sites, `wiki/access.md` states what the field is, who ever sees it, and why we deliberately do not canonicalize `+tag` subaddresses, and the offline-player-resolution note in `wiki/sync.md` names both lookups it now makes.
- Put the public API online on beta: the daemon grant, the `public_api` ansible role, its cert and its throttled vhost are written and unrun, so what is left is the `api.archon.krcg.org` A record, a full (not quick-lane) beta deploy, and the verification — register an `api:read` client, mint a daemon token with it, read one full refresh unthrottled, see a tight loop of them refused with 429, and see the same token rejected by the app. **Done when** the beta API answers a daemon token and the throttle has been observed. Context in `board/public-api.md`.
