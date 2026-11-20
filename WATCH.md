# Watch

Work that cannot start yet: it waits on a date, recurs, or waits on something
outside our hands. The board holds no waiting state, so it waits here. The evidence
each item needs stays on the docs page that owns the subject; this file holds only
the ask, its trigger and what to do when it fires.

`/watch-check` reads it. Each item names:

- **When** — a date, a recurrence, or a condition someone could observe firing.
  Never "later".
- **Check** — how to tell whether it fired.
- **Fired** — what happens then: usually the ask goes through `/intake` as an
  ordinary board line and the item is deleted; a recurring item stays and records
  the date it was last checked.
- **Not yet** — what a check that finds nothing does, when it is more than
  "stays".

Completion is deletion, as on the board. An item that is no longer wanted is
dropped, and waiting is not exemption from that verdict. Actions a deploy unlocks
are not here: they wait on a release, not a trigger, in
[post-deploy](docs/post-deploy.md).

## VEKN stage 1 — the tournament calendar sync retires

- **When**: VEKN greenlights it and `sync_all_tournaments` stops
  ([vekn](docs/vekn.md#stage-1--the-tournament-calendar-retires-on-the-greenlight)).
  Until then the sync's full rebuild re-creates anything deleted locally and wipes
  anything corrected, which is what makes each ask unfixable today.
- **Check**: whether the stage-1 split has landed and the calendar sync no longer
  runs on production.
- **Fired**: each ask below goes through `/intake` as its own line, with its
  evidence section in [vekn-decommission](docs/vekn-decommission.md).
  - Clean up the all-live duplicate tournaments by soft-delete plus vekn-id
    transplant. Done when each group in
    [duplicate tournament cleanup](docs/vekn-decommission.md#duplicate-tournament-cleanup)
    has one live copy.
  - Give ICs a capability to delete or withdraw a tournament that still exists on
    vekn.net (gh-6). Done when an IC can remove a mistaken event, every entry in
    [events to delete](docs/vekn-decommission.md#ic-record-curation--events-to-delete)
    is gone, and the frontend no longer offers Delete on an offline-locked
    tournament, which the API refuses today.
  - Delete the `ArchivalResultsVeknLinked` guard in `engine/src/tournament/`. Done
    when an IC can correct a rounds-less row carrying `external_ids['vekn']` and the
    correction survives a full sync run.
  - Settle the winner on the rows in
    [disagree about who won](docs/vekn-decommission.md#ic-record-curation--rows-that-disagree-with-the-archive-about-who-won)
    and correct whichever side is wrong. Done when each row's `winner` matches the
    record the IC accepts.
  - Settle the eight pairs in
    [archive reconstructions](docs/vekn-decommission.md#archive-reconstructions-of-an-event-we-already-hold):
    the same event is soft-deleted and its archive key transplanted onto the
    survivor as `external_ids.twda_entry`; a distinct event stays live and is
    recorded as such. Done when no pair is ambiguous and the mixed-vekn class of
    `dedup_tournaments.py` reports only pairs it can propose.
  - Make `POST /api/tournaments` stamp its event code inline like every other
    creation path, and delete `_stamp_missing_event_codes` with its query. Done when
    a tournament created through the route carries a code in the same save, and
    [architecture](docs/architecture.md#the-short-event-code) no longer describes a
    boot sweep.
  - Delete the scheduled `run_twda_sync` and its row in
    [architecture](docs/architecture.md#scheduled-background-tasks), keeping
    `backfill_twda.py` as the manual reconciliation. Done when no scheduled job
    fetches the archive; first re-check that nothing else depends on it.

## VEKN stage 2 — the member roster sync retires

- **When**: vekn.net registration closes and `VEKNSyncService` stops
  ([vekn](docs/vekn.md#stage-2--the-member-roster-retires-when-veknnet-registration-closes)).
- **Check**: whether the roster sync still runs on production.
- **Fired**: through `/intake` — review the
  [Prince / NC divergence](docs/vekn-decommission.md#prince--nc-divergence--legacy-archon-vs-the-app):
  each divergent name gets a verdict from someone who knows the appointments, and
  the roles match it. Never a blind union, which would republish superseded
  officials' contact details and seat two coordinators in two countries.

## The VEKN admins correct the calendar entries

- **When**: the VEKN admins report the entries in
  [the results stuck on the round count](docs/vekn-decommission.md#push-the-results-stuck-on-the-calendars-round-count)
  corrected.
- **Check**: their answer, or a live read of a few listed entries through beta's
  VEKN client.
- **Fired**: through `/intake`, as a line with a production step. Per stamped event
  whose entry is fixed, read the report before writing:

  ```sh
  … /opt/archon/backend/scripts/fix_stuck_vekn_push.py --vekn <id>
  … fix_stuck_vekn_push.py --vekn <id> --apply
  ```

  Done when the first hourly batch after it pushes every finished entry listed,
  the unstamped ones on their own and the stamped ones once cleared, and none logs
  the round-count refusal again. Approval publishes, so expect them pending on
  vekn.net until an official works the queue.

## The VEKN API maintainers answer on the 15 placements

- **When**: the maintainers answer the 2026-08-24 report of
  [15 events placed in the old push order](docs/vekn.md#placements-handed-to-the-vekn-api-maintainers),
  or a re-run of `backend/scripts/audit_vekn_placement.py` shows the 15 agreeing.
- **Check**: the re-run of the audit.
- **Fired**: check the ratings a day later, since whether upstream re-derives
  points from a corrected `pos` is
  [unestablished](docs/domain/vekn.md#never-chase-veknnets-stored-rtp). If the
  ratings did not follow, the winner holds the loser's rating, and that goes
  through `/intake` as its own line.

## The Rules Director answers on no-final rating credit

- **When**: the Rules Director answers the
  [questions put in 2026-08](docs/tournaments.md#no-final-rating-credit-open-with-the-rules-director).
- **Check**: the owner's correspondence; the owner holds Rulemonger.
- **Fired**: through `/intake` — record the answers in `docs/domain/` (§3.1.6's
  reading in [tournament rules](docs/domain/tournament-rules.md), the A.2/A.2.1
  credit in [VEKN](docs/domain/vekn.md)), then change the engine or keep the
  shipped stance, citing the ruling. `FinishTournament`, `vekn_tournament_sync` and
  `archon_import.py` must end up saying the same thing. Q5, on push encoding, must
  be answered while the vekn.net API still responds.

## The two-player format becomes official

- **When**: Black Chantry or VEKN publish the
  [two-player format](docs/domain/tournament-rules.md#two-player-format-in-testing)
  as official, with rules for how an event is run (gh-83). The playtest has no
  deadline and may not pass.
- **Check**: Black Chantry's and VEKN's announcements.
- **Fired**: through `/intake` — run 1v1 events, scoped by
  [what it takes](docs/tournaments.md#the-two-player-format-not-yet-official).
  An announcement without event rules has not fired it.

## Discord bot on production, by the next production release

- **When**: before the next production release, not after: that release carries
  the organizer guide's install link, which is inert until Portal step 4 is saved.
  Written 2026-08-30; releases have shipped since, so the first check settles
  whether it was done.
- **Check**: whether Server Settings → Roles → Links → Add requirement lists
  Archon in a production guild.
- **Fired**: through `/intake` at the top — run
  [Portal setup](docs/discord.md#linked-roles) against the production application
  `1495034668469194864`, then install the bot on the production guild(s); which
  servers count as production is part of the ask. Step 1 is believed already done,
  since the journal's `pushed metadata for user` lines can only come from a working
  redirect: confirm it rather than re-adding it. Done when the Linked Roles
  requirement lists Archon with its three metadata fields, and `/setup <tournament
  url>` in a production guild creates the category with its announcement, lobby
  and judges channels.

## Public API on production

- **When**: the first `just deploy-prod` with `public_api = True`, which issues the
  `api.archon.vekn.net` certificate and starts `archon-public-api` on port 7007.
  Written 2026-09-25; releases have shipped since.
- **Check**: `curl -s https://api.archon.vekn.net/v1/` answers.
- **Fired**: through `/intake` — exercise a registered `api:read` client's daemon
  token, the throttle, and the app's rejection of that token on production.

## A member asks to keep their win out of the TWDA

- **When**: a member asks to keep their name or their winning deck out of the
  TWDA. A private deck covers every other deck; the winner's publishes regardless.
- **Check**: open `feedback` issues and the owner's mail.
- **Fired**: through `/intake` — a TWD opt-out for a winner.

## A consumer asks for league standings in the public API

- **When**: a public-API consumer asks for league standings.
- **Check**: open issues.
- **Fired**: through `/intake` — they need engine compute, or a
  promo-stock-style cross-object reprojection on tournament save.

## The owner wants a krcg entry point to the bulk export

- **When**: the owner asks for a static mirror of `/v1/export` on
  `static.krcg.org`.
- **Fired**: through `/intake`.

## SvelteKit and svelte-check ship TypeScript 7 support

- **When**: SvelteKit and svelte-check both release TS 7 support.
- **Check**: their changelogs.
- **Fired**: through `/intake` — bump TypeScript 6 → 7. Done when `npm ls` is
  clean and `svelte-check` passes on TS 7.
