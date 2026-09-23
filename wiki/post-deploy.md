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

## Watch the co-opted-by inference on production

Gated by "Serve a backend restart within seconds" (`4d4c22f1`), which moves the
member sync's co-opted-by reads out from under the 30s guard
([architecture](architecture.md#scheduled-background-tasks)). Before it is live
they time out on production, so an earlier sync measures the old code.

The next VEKN member sync on production must log `Inferred coopted_by:`. Report it
to the owner and delete this section.

## Check the old VEKN sheets after the first tournament sync

Gated by `7836e944`. The sync rebuilds any rounds-less import whose standings differ,
so the first scheduled tournament sync after the deploy (or the admin *Run now*)
rewrites the legacy sheets on its own; running the check before that reads the
old imports. Nothing to run but the queries.

```sql
SELECT "full"->'external_ids'->>'vekn' AS vekn
FROM objects
WHERE type = 'tournament' AND "full"->'external_ids' ? 'vekn'
  AND jsonb_array_length("full"->'standings')
      <> (SELECT count(DISTINCT s->>'user_uid')
          FROM jsonb_array_elements("full"->'standings') s);

SELECT count(*) FILTER (WHERE (s->>'gw')::float = 0) AS winners_at_zero,
       count(*) AS winners
FROM objects t, jsonb_array_elements(t."full"->'standings') s
WHERE t.type = 'tournament' AND t."full"->'external_ids' ? 'vekn'
  AND t."full"->>'start' < '2011' AND s->>'user_uid' = t."full"->>'winner';

SELECT t."full"->'external_ids'->>'vekn' AS vekn
FROM objects t, jsonb_array_elements(t."full"->'standings') s
WHERE t.type = 'tournament' AND t."full"->'external_ids' ? 'vekn'
  AND t."full"->>'start' < '2011'
  AND (t."full"->>'max_rounds')::int > 0
  AND (s->>'gw')::float > (t."full"->>'max_rounds')::int;
```

The first returns no rows — vekn events 9915, 7713, 8754, 5793, 6580, 9166 and
2804 among them — and so does the third; legacy sheets carry no round count, so
it covers the few pre-2011 sheets in the newer format. The second reads about 520 winners at 0 prelim GW out of about
2,980, against about 65 before. Report both to the owner and delete this section.
