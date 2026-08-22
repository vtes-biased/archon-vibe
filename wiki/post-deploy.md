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

## Backfill the `api` projection

**Gated on** the commit adding the fourth `api` column — a projection is computed
at write time, so every row saved before that commit went live carries a NULL
`api` and is invisible to the public API. `init_db` adds the column on deploy; only
a re-save fills it.

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

**Owes afterwards**: nothing to tell anyone — no consumer can reach the column
until the API app ships. Delete this section.
