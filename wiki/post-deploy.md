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

## Confirm the judge directory sync runs on production

**Gated on** the commit setting `judge_sync = "true"` in
`deploy/group_data/prod.py`. The first run was triggered by hand from the admin
panel; the daily 05:30 UTC job only exists once a deploy carries the flag.

**Run** nothing: after the first 05:30 UTC following that deploy, read the
vekn-status panel.

**Proves it worked**: *Judge directory sync* shows green with a run after the
deploy, and `preview_judge_sync.py` on the box prints `0 members would change`.

**Owes afterwards**: telling the VTES Exams maintainers the integration is live, and that
leaving the public directory or letting an accreditation lapse now removes the
Archon title. Delete this section.

## Ask organisers to re-enter their promo reports

**Gated on** the commit declaring `promos` and `stock_source_uid` on
`TournamentActionRequest`. Until it is live every `ReportPromos` still fails with
"promos required", so asking earlier only earns a second failure. Every report
since the feature shipped on 17 July was refused, and so was every raffle prize
(`prize_promo_uid`).

**Run** nothing: the reply on gh-55 is posted and the issue closed.

**Proves it worked**: within a few days, on production,
`SELECT count(*) FROM objects WHERE type = 'tournament' AND
jsonb_array_length(coalesce("full"->'promos_distributed', '[]'::jsonb)) > 0;`
answers above 0.

**Owes afterwards**: nothing. Delete this section once the count is above 0.

## Verify the Discord tournament section on a server that hides channels by default

**Gated on** `709c0f1c` (View Channels allowed to `@everyone` on the tournament
channels, onboarding default channels managed by `/setup` and `/teardown`). The
install link points at the production bot, so nothing earlier runs this code.

**Run** on a test server whose `@everyone` lacks View Channels and whose
onboarding is on with at least one prompt: re-authorise the bot for Manage
Server (install integer `8861518896`, [discord](discord.md)), `/setup`, start a
round, `/teardown`.

**Proves it worked**: a member who opted into nothing sees #announcement,
#lobby and their table channel, cannot post in #announcement and cannot see
#judges; the onboarding prompts are unchanged, and after `/teardown` the default
channels are back as they were. Any failed check goes through `/intake` as a fix.

**Owes afterwards**: stating in [discord](discord.md) (Onboarding) whether
default channels reach existing members and whether a table channel needs
onboarding to show. Delete this section.

## Rewrite `objects` into the row and prove a cold pass on production

**Gated on** the commit *Store object projections in the row and read ahead 1 MB*:
its first boot sets `STORAGE MAIN`, and a rewrite before that leaves every value
where it was.

**Run**, in this order, in a quiet daytime slot with no event running, outside
00:00–04:00 UTC and with `sar -d` under 10 ms:

1. On the box, `cat /sys/block/xvda/queue/max_sectors_kb`. Under about 350 KB the
   500-read proof below cannot pass, whatever else is true: the rewritten table is
   about 170 MB and the device splits every read at that size. Run the rest anyway
   and take the figures to `/intake`.
2. `just setup-prod`, then `FORCE=1 just reboot-prod`. On the box,
   `cat /sys/block/xvda/queue/read_ahead_kb` answers 1024.
3. The rewrite. Requests wait on its lock and fail at their own 5 s, for minutes on
   a slow spell; beta held it for 4.7 s.

   ```sh
   sudo -u postgres psql -X -d archon <<'SQL'
   SET lock_timeout = 0;
   SET statement_timeout = 0;
   SELECT attname, attstorage FROM pg_attribute WHERE attrelid = 'objects'::regclass
     AND attname IN ('public', 'member', 'api', 'full');
   SELECT count(*), max(modified_at) FROM objects;
   VACUUM (FULL, ANALYZE) objects;
   SELECT count(*), max(modified_at) FROM objects;
   SELECT pg_size_pretty(pg_relation_size(oid)) AS heap,
          pg_size_pretty(pg_relation_size(reltoastrelid)) AS toast
     FROM pg_class WHERE oid = 'objects'::regclass;
   SQL
   ```

4. The cold pass: it evicts only the table's files, so nothing else on the box goes
   cold and the count stays the pass's own.

   ```sh
   relations="oid = 'objects'::regclass
     OR oid = (SELECT reltoastrelid FROM pg_class WHERE oid = 'objects'::regclass)
     OR oid IN (SELECT indexrelid FROM pg_index WHERE indrelid =
       (SELECT reltoastrelid FROM pg_class WHERE oid = 'objects'::regclass))"
   sudo -u postgres psql -X -q -At -d archon -c "CREATE EXTENSION IF NOT EXISTS pg_buffercache"
   sudo -u postgres psql -X -q -At -d archon -o /dev/null -c "SELECT pg_buffercache_evict(bufferid)
     FROM pg_buffercache WHERE relfilenode IN
       (SELECT pg_relation_filenode(oid) FROM pg_class WHERE $relations)"
   files=$(sudo -u postgres psql -X -q -At -d archon -c "SELECT
     current_setting('data_directory') || '/' || pg_relation_filepath(oid)
     FROM pg_class WHERE $relations")
   sync
   for f in $files; do
     sudo dd of="$f" oflag=nocache conv=notrunc,fdatasync count=0 status=none
   done
   before=$(awk '$3 == "xvda" {print $4}' /proc/diskstats)
   sudo -u postgres psql -X -q -d archon <<'SQL'
   SET statement_timeout = 0;
   DO $$ DECLARE r record; BEGIN
     FOR r IN SELECT type, "public"::text, "member"::text, "api"::text, "full"::text
              FROM objects WHERE deleted_at IS NULL LOOP NULL; END LOOP;
   END $$;
   SQL
   echo "device reads: $(( $(awk '$3 == "xvda" {print $4}' /proc/diskstats) - before ))"
   sudo -u postgres psql -X -q -At -d archon -c "SELECT count(*) * 8 / 1024 || ' MB'
     FROM pg_buffercache WHERE relfilenode IN
       (SELECT pg_relation_filenode(oid) FROM pg_class WHERE $relations)"
   sudo -u postgres psql -X -q -At -d archon -c "DROP EXTENSION pg_buffercache"
   ```

**Proves it worked**: all four columns read `m`; the row count and newest
`modified_at` are unchanged but for a live write; the read-ahead answers 1024 after
the reboot; the pass makes under 500 device reads and leaves under 50 MB. Beta
answers about 400 and 31 MB by this recipe at 1 MB, 1,441 at 128 KB.

**Owes afterwards**: delete this section. A failed proof goes through `/intake`,
and so does a pass that still stalls production: the fallback is patching the
previous files from changed rows only, whose prototype took 2.2 s of CPU and
21–27 MB locally and about 130 cold pages for 50 rows.
