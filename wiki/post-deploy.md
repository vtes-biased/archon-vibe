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

## Prove unpinned content links carry no country

**Migration** `content-link-country`

Gated by the commit that dropped the country from content-type community links
([architecture](architecture.md#community-links)). The entry nulls the country of
every content link not pinned national. The old rows decode, but they are wrong
rather than redundant: a stored country steers an unpinned link's moderation to
that country's NC instead of its owner's, and is what read as an audience
restriction to the member who set it.

Nothing to run: the entry rewrote the rows before the process served. It worked
when this answers 0:

```sql
SELECT count(*) FROM objects o, jsonb_array_elements(o."full"->'community_links') link
WHERE o.type = 'user' AND o."full"->'community_links' <> '[]'::jsonb
  AND link->>'type' IN ('blog', 'bluesky', 'facebook', 'instagram', 'other',
    'reddit', 'spotify', 'twitch', 'website', 'x', 'youtube')
  AND link->>'country' IS NOT NULL
  AND coalesce(link->>'moderation', '') <> 'national';
```

Nothing else is owed.
