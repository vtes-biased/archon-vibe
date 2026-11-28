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
