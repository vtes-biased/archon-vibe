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
- Make the off-box backup retention actually apply: every dump is uploaded under a filename carrying its own timestamp, so the pruner sorts each snapshot into a group of one and keeps it forever — 48 snapshots per repository where the policy asks for at most 23, one more every day, with four July dumps still present in late August, each one counted as the newest daily, weekly and monthly of a group containing only itself. **Done when** a backup run prunes the series to the configured policy, the snapshot count stops growing, and `wiki/dev.md` documents the backup regime it currently says nothing about: the daily cluster dump, the weekly restore-verify, the off-box push and the retention each applies.
- Stop rebuilding the access-level snapshots when nothing has changed: the pass runs every fifteen minutes whatever the corpus did, ninety-six times a day, each one reading every object and writing thirty-five megabytes of gzip — on a quiet day three and a half gigabytes of writes and a page cache repeatedly emptied of the database's working set, to reproduce four files identical to the ones already there. **Done when** a regeneration is skipped when neither the object count nor the newest modification has moved since the last one, a purge that shrinks the corpus without moving the newest modification still triggers one, and the fifteen-minute claim in `wiki/sync.md` describes what now actually happens.
- Give the member profile a tab strip so a top player's page stops running three screens: identity stays above the strip, and Profile · Play record · Account swap below it, using the tournament console's tab anatomy — icon always, the label spelled out on the active tab only below `sm`, the full label as the accessible name — so three labels survive five locales on a phone. The public member page carries the same strip without the Account tab, and the undocumented-decklist nudge lives on the Play record tab beside the wins it names. **Done when** both profile surfaces carry the strip, the row does not overflow at 360px in en, fr, es, pt and it, and `wiki/design.md` carries three things it does not today: the profile's tab structure, the tab-label rule lifted out of the console redesign section to govern every tab row, and one app-wide fold grammar naming the four competing chevron patterns it replaces. Context in `board/profile-tabs.md`.
- Take off the production box what it does not use: a package cache and a build cache no deploy ever cleans, a system log written twice because a second daemon duplicates what the journal already keeps, a journal with no size limit on a twenty-four gigabyte disk, database connection slots for sixty clients when the pool asks for eight, and daemons a single-disk virtual machine has no use for — multipath, firmware update, modem management, disk management, and the guest tools of a hypervisor this box does not run on. Roughly a gigabyte of disk and thirty megabytes of memory, on a box with three hundred spare. **Done when** the provisioning role installs none of it and cleans what is already there, a fresh run leaves the caches empty and the journal capped, and `wiki/dev.md` records the box's real size and the baseline the role guarantees.
- Put the public API online on beta: the daemon grant, the `public_api` ansible role, its cert and its throttled vhost are written and unrun, so what is left is the `api.archon.krcg.org` A record, a full (not quick-lane) beta deploy, and the verification — register an `api:read` client, mint a daemon token with it, read one full refresh unthrottled, see a tight loop of them refused with 429, and see the same token rejected by the app. **Done when** the beta API answers a daemon token and the throttle has been observed. Context in `board/public-api.md`.
- Replace the paper NDA loop with in-app click-to-sign so a Playtest Coordinator can enroll a playtester end to end: the PTC requests a signature, the member reads the BCP NDA prefilled with their name and the current date and signs by typing their name, the server seals a PDF carrying the document version, hash, signer and timestamp on an audit page and emails the signer a copy, PTC and IC view and download it from the member record, the PTC can instead upload a paper-signed scan as fallback, and granting PT is engine-refused without an NDA on record — existing PT holders keep the role and surface as missing-NDA for backfill. **Done when** the full path — request, sign, sealed PDF, refused grant, granted after signing — demos on beta and the wiki pages named in `board/playtester-nda.md` are updated. Context there.
