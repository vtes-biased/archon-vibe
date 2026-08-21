# Post-deploy — what a production deploy unlocks

Actions that only become safe once a specific commit is live on production. The
board holds no waiting state and a subsystem page is no place for a runbook, so
they park here: one `##` section per item, **completion is deletion**, and an
empty page is the normal state.

`/post-deploy` runs them, ahead of the feedback issues it closes. Unlike the work
deferred in [vekn-decommission](vekn-decommission.md), a fired trigger here does
**not** go back through `/intake`: that trigger fires every release, and an item
reaches this page only after passing egress review, so the one decision left is
the owner's go/no-go.

**An item belongs here only if `/post-deploy` could execute it with nothing but
that go/no-go.** Work carrying judgment — reviewing a dedup's output, diffing Hall
of Fame membership either side of a backfill — stays a board line that happens to
have a production step. Without that boundary this page becomes a second board.

**Every item names the commit that gates it**, so `git tag --contains <sha>`
answers whether a given deploy has made it actionable — the same check
`/post-deploy` already runs against a feedback issue's fix. An item states what
gates it and why, what to run, what proves it worked, and what it owes afterwards:
people to tell, and the wiki text that dies with it.

## Clear the placeholder venue locations vekn.net flipped to Antarctica

**Gated on** `06681dc`. Rows the sync already flipped hold Antarctica as their own
value, and preserving them is exactly what stops them healing — but running this
before the drop is deployed is undone by the next sync within the hour.

**Run** `backend/scripts/clear_placeholder_venue_location.py --apply` on
production, from the deployed tree.

**Verify** the named rows no longer read `AQ`/UTC, and survive the next sync run.

**Then** ask the 11 organizers it names to re-enter their location — gh-9 is the
report this came from. Trim the deferral sentence in [vekn](vekn.md#tournaments) to
the fact that the sync drops venue 9999.

## Normalize the stored country values to ISO codes

**Gated on** `19cc18c`. The daily legacy merge re-saves a league or tournament on
any full-struct diff, so a row swept before that merge is deployed reads back as a
country name within a day, and the live write paths for `User.country` and
`League.country` must be normalizing too or a swept row decays one profile edit at
a time.

**Run** `backend/scripts/normalize_countries.py` from the deployed tree for the
report, review the per-type counts with the owner, then the same with `--apply`.

**Verify** a second report run comes back empty; the script is idempotent.

**Then** delete the pre-rule clause in [hazards](hazards.md) — the sentence
beginning "Rows written before that rule".

## Rebuild the stored projections widened for anonymous visitors

**Gated on** `ed50d1b`. The tournament public projection gained the event-page
fields and leagues lost `organizers_uids`, but projections are computed at write
time, so every row stored before it keeps the narrow shape: a logged-out visitor
reads "Proxies not allowed" on all 2378 events that allow them, and a short link
resolves to an event with no venue, description or deck rules. No test can catch a
missing projection backfill ([testing](testing.md)), which is why it parks here.

**Run** `backend/scripts/reproject_public.py` from the deployed tree for the count,
then the same with `--apply`. Run it **last** when the archive or event-code
backfills run in the same window: both re-save every tournament through the same
path, and only this one reaches leagues.

**Verify** every live tournament carries `proxies` at public level and no league
carries `organizers_uids`:

```sql
SELECT count(*) FILTER (WHERE type = 'tournament' AND public ? 'proxies'),
       count(*) FILTER (WHERE type = 'league' AND public ? 'organizers_uids')
FROM objects WHERE type IN ('tournament', 'league');
```

**Then** nothing to trim — [sync](sync.md#access-levels) states the re-save pattern
for every future projection change, not this run. gh-8 is the report it answers.
