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

## Tombstone the decks of players who left their event

Gated by the commit that made `Unregister` and `RemovePlayer` delete the player's
decks (`7f124e63`). Before it a departure left the decks behind, and under the
All mode an orphan still publishes at finish; running earlier lets the count refill
until the deploy.

A winner's deck is never such an orphan — `RemovePlayer` needs zero rounds, so
no native winner was ever removed — and an archive reconstruction's roster is its
winner alone, so both are excluded rather than trusted. Count them:

```sql
SELECT count(*) FROM objects d
JOIN objects t ON t.type = 'tournament' AND t.uid = d."full"->>'tournament_uid'
WHERE d.type = 'deck' AND d.deleted_at IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM jsonb_array_elements(t."full"->'players') p
      WHERE p->>'user_uid' = d."full"->>'user_uid')
  AND d."full"->>'user_uid' IS DISTINCT FROM t."full"->>'winner'
  AND t."full"->'external_ids'->>'twda' IS NULL;
```

Then tombstone them through the model, so the projections drop and every holder's
next catch-up evicts its copy ([sync](sync.md#access-levels)). Save this as
`/tmp/tombstone_orphan_decks.py` on the box:

```python
import asyncio
from datetime import UTC, datetime
import msgspec
from src import db
from src.models import DeckObject, ObjectType

QUERY = """
SELECT d."full" FROM objects d
JOIN objects t ON t.type = 'tournament' AND t.uid = d."full"->>'tournament_uid'
WHERE d.type = 'deck' AND d.deleted_at IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM jsonb_array_elements(t."full"->'players') p
      WHERE p->>'user_uid' = d."full"->>'user_uid')
  AND d."full"->>'user_uid' IS DISTINCT FROM t."full"->>'winner'
  AND t."full"->'external_ids'->>'twda' IS NULL
"""


async def main():
    await db.init_db()
    async with db.get_connection() as conn:
        rows = await (await conn.execute(QUERY)).fetchall()
    now = datetime.now(UTC)
    for (row,) in rows:
        deck = db.decode_json(row, DeckObject)
        await db.save_object_from_model(
            ObjectType.DECK, msgspec.structs.replace(deck, deleted_at=now, modified=now)
        )
    print(f"tombstoned {len(rows)}")
    await db.close_db()


asyncio.run(main())
```

and run it with the service environment:

```sh
sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \
  cd /opt/archon/backend && PYTHONPATH=/opt/archon/backend .venv/bin/python /tmp/tombstone_orphan_decks.py'
```

The count query then answers 0. Report the number to the owner and delete this
section. No issue reported this, so there is nobody to tell.

## Evict past private decks from their organizers' devices

Gated by the commit that withholds a finished event's private decks from its
organizers (`49be3df0`). Its own finish path re-saves the decks it withholds,
but events finished before it never had that re-save, so their organizers keep a
local copy: the overlay stops sending those decks, and nothing tombstones them.
Touching the rows moves `modified_at` (the `objects` BEFORE-UPDATE trigger stamps
it), and every organizer's next catch-up then streams a member tombstone for each.
Running it earlier is wasted: the old overlay would re-send the decks at `full`
on the next connect.

```sql
UPDATE objects d SET modified_at = d.modified_at
FROM objects t
WHERE d.type = 'deck' AND d.deleted_at IS NULL
  AND (d."full"->>'private')::boolean
  AND t.type = 'tournament' AND t.uid = d."full"->>'tournament_uid'
  AND t."full"->>'state' = 'Finished';
```

The `UPDATE`'s row count is the record. Nothing to tell anyone; delete this
section once it has run.

## Watch the co-opted-by inference on production

Gated by "Serve a backend restart within seconds" (`4d4c22f1`), which moves the
member sync's co-opted-by reads out from under the 30s guard
([architecture](architecture.md#scheduled-background-tasks)). Before it is live
they time out on production, so an earlier sync measures the old code.

The next VEKN member sync on production must log `Inferred coopted_by:`. Report it
to the owner and delete this section.
