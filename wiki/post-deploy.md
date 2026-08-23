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

## Collapse the stored link moderation

**Gated on** `2d6190f`, which replaced the `{status, scope, by, at}` moderation
record on a community link with a single value. `User` decodes strictly, so a row
still carrying the record shape raises on every read of that member — this is a
repair, not a tidy-up, and it runs **immediately after the deploy**, ahead of the
`api` backfill below. Running it against the earlier build would have that build
write the record shape straight back.

**Run** from the deployed tree, count first, then apply:

```sh
/opt/archon/backend/.venv/bin/python /opt/archon/backend/scripts/collapse_link_moderation.py
/opt/archon/backend/.venv/bin/python /opt/archon/backend/scripts/collapse_link_moderation.py --apply
```

Only the rows the app cannot decode are touched, so nothing else can be writing
them. Idempotent.

**Proves it worked**: both return 0.

```sql
SELECT count(*) FROM objects WHERE type = 'user'
  AND jsonb_path_exists("full", '$.community_links[*].moderation.status');
SELECT count(*) FROM objects WHERE type = 'user'
  AND jsonb_path_exists("api", '$.community_links[*].moderation.status');
```

**Owes afterwards**: nothing to tell anyone — a member whose link was hidden or
pinned keeps that decision, and the record it was stored in was never displayed.
Delete this section.

## Backfill the `api` projection

**Gated on** `2d6190f`, the last commit to change the `api` projection's shape. A
projection is computed at write time, so every row saved before that commit went
live carries a NULL or pre-narrowing `api` and is wrong for the public API.
`init_db` adds the column on deploy; only a re-save fills it. Deploying an
earlier commit of the series and running this then would satisfy the proof
queries below on the old shape and delete this section with nothing left to
re-trigger it.

**Run** from the deployed tree, count first, then apply:

```sh
/opt/archon/backend/.venv/bin/python /opt/archon/backend/scripts/reproject_public.py
/opt/archon/backend/.venv/bin/python /opt/archon/backend/scripts/reproject_public.py --apply
```

It re-saves users, tournaments, decks and leagues (sanctions and promos are
permanently NULL at `api`). Safe against the live backend and idempotent.

**Proves it worked**: `SELECT count(*) FROM objects WHERE type = 'tournament' AND
"api" IS NULL AND deleted_at IS NULL` returns 0, and the same query for `user`
returns exactly the count of users without a `vekn_id`.

A NULL check alone cannot see a *stale* projection, so two shape queries must
also return 0 — a deck still carrying the constant the narrowing removed, and a
link whose moderation is still a record rather than one value:

```sql
SELECT count(*) FROM objects WHERE type = 'deck' AND "api" ? 'public';
SELECT count(*) FROM objects WHERE type = 'user'
  AND jsonb_path_exists("api", '$.community_links[*].moderation.status');
```

**Owes afterwards**: nothing to tell anyone — no consumer can reach the column
until the API app ships. Delete this section.
