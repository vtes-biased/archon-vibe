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
- Stop rebuilding the access-level snapshots when nothing has changed: the pass runs every fifteen minutes whatever the corpus did, ninety-six times a day, each one reading every object and writing thirty-five megabytes of gzip — on a quiet day three and a half gigabytes of writes and a page cache repeatedly emptied of the database's working set, to reproduce four files identical to the ones already there. **Done when** a regeneration is skipped when neither the object count nor the newest modification has moved since the last one, a purge that shrinks the corpus without moving the newest modification still triggers one, and the fifteen-minute claim in `wiki/sync.md` describes what now actually happens.
- Stop paying for the snapshot download twice: in production the app answers `/snapshot` with auth, level and the access-version header only and hands the body to nginx to serve from disk, so a room-sized cold connect no longer runs every byte through Python twice and a proxy hop once — ~1.3GB of transient memory at 200 clients, against production's ~300MB spare — while the app's own streaming path stays for dev, for the fallback and for the zip export, and declares its length up front from the fd it serves so a mid-stream regeneration cannot truncate it. **Done when** a 200-client cold burst on beta shows the body served by nginx with the backend's memory flat, the same client still receives `X-Access-Version` and completes snapshot → stream → sync_complete, and the serving description in `wiki/sync.md` plus the two hazards entries it obsoletes (the unbuffered-snapshot trap and the room-sized-cold-connect limit) are rewritten with re-measured numbers. Context in `board/snapshot-accel.md`.
- Give the member profile a tab strip so a top player's page stops running three screens: identity stays above the strip, and Profile · Play record · Account swap below it, using the tournament console's tab anatomy — icon always, the label spelled out on the active tab only below `sm`, the full label as the accessible name — so three labels survive five locales on a phone. The public member page carries the same strip without the Account tab, and the undocumented-decklist nudge lives on the Play record tab beside the wins it names. **Done when** both profile surfaces carry the strip, the row does not overflow at 360px in en, fr, es, pt and it, and `wiki/design.md` carries three things it does not today: the profile's tab structure, the tab-label rule lifted out of the console redesign section to govern every tab row, and one app-wide fold grammar naming the four competing chevron patterns it replaces. Context in `board/profile-tabs.md`.
