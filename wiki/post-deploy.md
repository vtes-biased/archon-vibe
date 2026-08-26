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

A section whose first line is **Migration** followed by a slug is the standing
proof of an entry in `backend/src/migrations.py`
([architecture](architecture.md#stored-value-migrations)). It has nothing to
run — the entry rewrote the rows before the process served — but its queries are
the only record that the rewrite reached a given database, so it is deleted only
once **every** long-lived one answers 0, and the entry it names dies in the same
commit. `just migration-pairing` fails on either half outliving the other.

**Every item names the commit that gates it**, so `git tag --contains <sha>`
answers whether a given deploy has made it actionable — the same check
`/post-deploy` already runs against a feedback issue's fix. An item states what
gates it and why, what to run, what proves it worked, and what it owes afterwards:
people to tell, and the wiki text that dies with it.

## Confirm the off-box backup retention prunes

**Gated on** the commit that groups `restic forget` by host — findable as
`git log -1 --format=%h --grep='Group restic forget by host'`. Until it is
deployed, every run re-applies the broken default grouping: each timestamp-named
dump is its own group, so nothing is ever forgotten and the snapshot count grows
by one per repository per day. Running the check earlier only observes that.

**Run**: nothing, or `systemctl start postgres-backup.service` to skip waiting
for the 03:00 timer. The first fixed run's `forget --prune` removes weeks of
accumulated snapshots per repository, so it runs noticeably longer than usual —
expected, not a failure.

**Proves it worked**: for each repository (per database, plus `globals`),
`restic snapshots` lists at most 7 daily + 4 weekly + 12 monthly snapshots —
fewer where buckets overlap — and the July snapshots are gone. The next day's
run adds none net.

**Owes afterwards**: nothing to tell anyone. Delete this section.

## Re-submit the decks the archive refused

**Gated on** the commit that makes the archive accept our pull requests —
*"Decline maintainer modification"*, findable as
`git log -1 --format=%h --grep='Decline maintainer modification'`. GitHub grants
the base maintainer edit rights on a cross-repository branch by default, and the
archive's installation — pull requests and nothing else — cannot grant that on a
fork it cannot see, so every creation was refused with a 422: the stuck events
have their deck committed on the fork's branch with no pull request behind it.
Running earlier just re-records the refusal.

The query catches two shapes: `failed`, the refused creations, and
`skipped / not_configured`, events that finished before the fork installation and
its vault entries existed — nothing refires either, because their results are
already pushed and the batch retry never looks at them again.

**Run**: list the events, then for each one `POST /api/tournaments/{uid}/push-vekn`
as an admin. With the results already pushed that path skips vekn.net entirely and
re-runs only the submission.

```sql
SELECT "full"->>'uid', "full"->>'name', "full"->'twda_status'->>'outcome'
FROM objects WHERE type='tournament' AND deleted_at IS NULL
  AND ("full"->'twda_status'->>'outcome' = 'failed'
    OR ("full"->'twda_status'->>'outcome' = 'skipped'
        AND "full"->'twda_status'->>'reason' = 'not_configured'));
```

**Proves it worked**: the query returns no rows, and each event's `twda_status`
reads `submitted` with a PR URL on `GiottoVerducci/TWD`.

**Owes afterwards**: nothing to tell anyone — the organizers never saw the failure.
Delete this section.
