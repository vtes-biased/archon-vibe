# Watch

Work that cannot start yet: it waits on a date, recurs, or waits on something
outside our hands. The board holds no waiting state, so it waits here. The evidence
each item needs stays on the docs page that owns the subject; this file holds only
the ask, its trigger and what to do when it fires.

`/watch-check` reads it, as the first step of `/upkeep` and after every production
deploy in `/post-deploy`. Each item names:

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

## VEKN stage 1 — post-deploy curation and TWDA retirement

- **When**: Stage 1 (tournament calendar sync retirement) is deployed on
  production ([vekn](docs/vekn.md#decommission)). Until then the live production
  sync can still re-create deleted rows or overwrite archival corrections.
- **Check**: whether the Stage 1 commit is deployed on production.
- **Fired**: each ask below goes through `/intake` as its own line, with its
  evidence section in [vekn-decommission](docs/vekn-decommission.md).
  - Clean up the all-live duplicate tournaments by soft-delete plus vekn-id
    transplant. Done when each group in
    [duplicate tournament cleanup](docs/vekn-decommission.md#duplicate-tournament-cleanup)
    has one live copy.
  - Delete the mistaken historical rows in
    [events to delete](docs/vekn-decommission.md#ic-record-curation--events-to-delete)
    now that ICs can delete any event. Done when every listed entry is gone.
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
  - Delete the scheduled `run_twda_sync` and its row in
    [architecture](docs/architecture.md#scheduled-background-tasks), keeping
    `backfill_twda.py` as the manual reconciliation. Done when no scheduled job
    fetches the archive; first re-check that nothing else depends on it.

## VEKN stage 2 — Prince / NC divergence review

- **When**: Stage 2 (member roster sync retirement) is deployed on production
  ([vekn](docs/vekn.md#decommission)).
- **Check**: whether the Stage 2 commit is deployed on production.
- **Fired**: through `/intake` — review the
  [Prince / NC divergence](docs/vekn-decommission.md#prince--nc-divergence--legacy-archon-vs-the-app):
  each divergent name gets a verdict from someone who knows the appointments, and
  the roles match it. Never a blind union, which would republish superseded
  officials' contact details and seat two coordinators in two countries.

## The Rules Director answers on no-final rating credit

- **When**: the Rules Director answers the
  [questions put in 2026-08](docs/tournaments.md#no-final-rating-credit-open-with-the-rules-director).
- **Check**: the owner's correspondence; the owner holds Rulemonger.
- **Fired**: through `/intake` — record the answers in `docs/domain/` (§3.1.6's
  reading in [tournament rules](docs/domain/tournament-rules.md), the A.2/A.2.1
  credit in [VEKN](docs/domain/vekn.md)), then change the engine or keep the
  shipped stance, citing the ruling. `FinishTournament` and `archon_import.py`
  must end up saying the same thing.

## The two-player format becomes official

- **When**: Black Chantry or VEKN publish the
  [two-player format](docs/domain/tournament-rules.md#two-player-format-in-testing)
  as official, with rules for how an event is run (gh-83). The playtest has no
  deadline and may not pass.
- **Check**: Black Chantry's and VEKN's announcements.
- **Fired**: through `/intake` — run 1v1 events, scoped by
  [what it takes](docs/tournaments.md#the-two-player-format-not-yet-official).
  An announcement without event rules has not fired it.

## SvelteKit and svelte-check ship TypeScript 7 support

- **When**: SvelteKit and svelte-check both release TS 7 support.
- **Check**: their changelogs.
- **Fired**: through `/intake` — bump TypeScript 6 → 7. Done when `npm ls` is
  clean and `svelte-check` passes on TS 7.
