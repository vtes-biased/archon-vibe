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

## Count the sanctions that predate the scope binding

Gated by `4fe04791`. Rows written before it can hold a tournament level with no
tournament — `backend/scripts/migrate_from_archon.py` falls back to a null one on
import — or a VEKN-wide level carrying one. Both are now refused on the issue and
the edit paths, so what is left is history. Run it only once that commit is live:
until then an unbound DQ still bleeds into every event, and the count reads as
work to do rather than as a closed record.

```sql
SELECT "full"->>'level' AS level,
       ("full"->>'tournament_uid' IS NOT NULL) AS has_tournament,
       count(*) AS rows
FROM objects
WHERE type = 'sanction'
  AND "full"->>'deleted_at' IS NULL
  AND ( ("full"->>'level' IN ('caution','warning','standings_adjustment','disqualification')
         AND "full"->>'tournament_uid' IS NULL)
     OR ("full"->>'level' IN ('suspension','probation')
         AND "full"->>'tournament_uid' IS NOT NULL) )
GROUP BY 1, 2
ORDER BY 1;
```

Nothing to rewrite either way: an imported record stays as it was filed, and the
rows are inert once the bleed is closed. Report the counts to the owner and delete
this section.

## Retract the decks production already unpublished

Gated by `8780030f`. Before it the catch-up skips a NULL member row, so the sweep
below would bump a cursor no client acts on.

Rows whose member projection went NULL before that commit were never announced:
their holders' IndexedDB still carries the deck at `public: true`, and no later
frame mentions them, since catch-up only asks for `modified_at > since`. The fix
retracts on write and on catch-up; neither reaches a row that stopped being
visible in the past.

Bump the cursor on exactly those rows so the member catch-up tombstones them.
Raw SQL is right here rather than `reproject_public.py`: no projection is
changing, only `modified_at`, which the BEFORE-UPDATE trigger stamps on any write
([sync](sync.md#access-levels)). Run it once, off-peak.

```sql
UPDATE objects SET type = type
WHERE type = 'deck' AND "member" IS NULL AND deleted_at IS NULL;
```

Every connected member then gets one tombstone per private deck on its next
catch-up — inert for a deck it never held, an eviction for one it did. Confirm on
a member client that a previously-unpublished decklist has left its profile deck
list, report the row count to the owner, and delete this section. No issue
reported this, so there is nobody to tell.
