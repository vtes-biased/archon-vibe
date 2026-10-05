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

## Confirm a deploy no longer surges promo images

Gated by `43cfddab`, which moved promo and card images into a cache that
outlives service-worker versions ([sync](sync.md#frontend-storage)). Before it,
every version change wiped them. Measuring before the commit is live proves
nothing.

Run against production Loki (`grafanacloud-logs` on vtesbiased), over the six
hours after the deploy that first carries the commit:

```logql
sum(count_over_time({tag="nginx"} |~ "GET /api/promos/[^ ]+/image" [1h]))
```

It worked when no hour in that window exceeds the highest hourly count of the
seven days before the deploy. Before this commit that ceiling was about 4,000
(16 full catalog prefetches of 253 images), all of it from fresh installs. If an
hour does exceed it, the surge is the finding: bring it to the owner.

Nothing else is owed.
