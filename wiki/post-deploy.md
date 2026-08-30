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

## Rewrite the stored `user:impersonate` scope

**Gated on** the commit that renames the scope to `event:run` — findable as
`git log -1 --format=%h --grep='Rename the impersonation scope'`. The rename is a
value change, not a schema one: `OAuthScope` no longer decodes
`"user:impersonate"`, so any stored row still carrying it fails to decode the
moment the new code reads it. Running this **before** the deploy breaks the
running code instead, which is why it is here and not in a migration.

**Run it immediately after the deploy, not at leisure.** Between the two, an
existing member token's `oauth_tokens` row no longer decodes, and the lookup
raises rather than answering 401 — the window is a 500 for anyone holding a live
grant, so keep it to minutes.

Three tables carry the string, each inside a `data` JSONB array. Run on beta
first, then production once beta is verified:

```sql
UPDATE oauth_clients  SET data = jsonb_set(data, '{scopes}', (
    SELECT jsonb_agg(CASE WHEN v = '"user:impersonate"'::jsonb
                          THEN '"event:run"'::jsonb ELSE v END)
    FROM jsonb_array_elements(data->'scopes') v))
  WHERE data->'scopes' @> '["user:impersonate"]'::jsonb;

UPDATE oauth_consents SET data = jsonb_set(data, '{scopes}', (
    SELECT jsonb_agg(CASE WHEN v = '"user:impersonate"'::jsonb
                          THEN '"event:run"'::jsonb ELSE v END)
    FROM jsonb_array_elements(data->'scopes') v))
  WHERE data->'scopes' @> '["user:impersonate"]'::jsonb;

UPDATE oauth_tokens   SET data = jsonb_set(data, '{scopes}', (
    SELECT jsonb_agg(CASE WHEN v = '"user:impersonate"'::jsonb
                          THEN '"event:run"'::jsonb ELSE v END)
    FROM jsonb_array_elements(data->'scopes') v))
  WHERE data->'scopes' @> '["user:impersonate"]'::jsonb;
```

**Proves it worked** — all three answer 0:

```sql
SELECT count(*) FROM oauth_clients  WHERE data->'scopes' @> '["user:impersonate"]'::jsonb;
SELECT count(*) FROM oauth_consents WHERE data->'scopes' @> '["user:impersonate"]'::jsonb;
SELECT count(*) FROM oauth_tokens   WHERE data->'scopes' @> '["user:impersonate"]'::jsonb;
```

**Owes afterwards**: refresh tokens live thirty days, so a client can still
present a JWT whose `scope` claim reads `user:impersonate` after the rows are
rewritten. On the access path the middleware compares that claim as a raw string,
so it stops matching and the token degrades to identity-only; on refresh the scope
no longer parses and the endpoint answers 400, which is one of the two statuses
[the bot clears its stored pair on](discord.md#the-tournament-bot) — so it re-authorizes
rather than retrying. Tell whoever runs the Discord bot to expect that once.
Delete this section once both databases answer 0.

## Trim the production box

**Gated on** the commit that prunes the provisioning role — findable as
`git log -1 --format=%h --grep='Trim the production box'`. Ansible runs from the
laptop checkout, not from a release, so the gate is that commit being in the
checkout the play runs from, and every command below is owner-executed.

**Run**: `just dry-foundation-prod` first and read the check-mode diff. The one
judgment call is the purge's autoremove list: a metapackage such as
`ubuntu-server` riding along with the six pruned packages is expected, a cascade
beyond that is a stop. The real run deletes `/var/log/syslog*`, `kern.log*` and
`mail.*` — journal duplicates — while `auth.log*` stays as the only pre-cap auth
history. Then `just foundation-prod && just database-prod`; the `max_connections`
change restarts PostgreSQL, a few seconds of downtime.

**Proves it worked**: `journalctl --disk-usage` at or under 256 MB,
`/var/cache/apt/archives` holding no `.deb`, no `.cache/uv` under `/root` or
`/opt/archon`, no units for rsyslog, multipathd, fwupd, ModemManager or udisks2,
`SHOW max_connections` answering 20 with the archon database's `datconnlimit`
back at `-1`, and roughly a gigabyte back on `df -h /`.

**Owes afterwards**: nothing to tell anyone. Delete this section.

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

**Owes afterwards**: the organizers did see it — the Finished panel has carried a
"TWDA submission failed" notice since v1.0.3 — and at least one reacted by having
the winning deck put into the archive by hand, so **check each event against the
archive before refiring it**: a re-submission over a deck a human already filed
opens a pull request against an entry that is already there. Answer the reporters
whose events this covers, then delete this section.

## Prove the deck round stamps landed

**Migration** `deck-round-stamp`

**Gated on** the commit that stamps a multideck deck with the round it was played
in — findable as `git log -1 --format=%h --grep='Stamp a multideck deck'`. There
is nothing to run: the entry rewrote every stored `deck.round` from the player's
i-th counted round to the tournament's own round index before the process served.
Its guard is a single date literal, and deliberately so: every row the rewrite
touches leaves the guard behind it, and no row the new build writes can ever enter
it, so the entry is a strict one-shot whose safety rests on nothing the engine
does. A guard that instead asked whether a stamp *looks* stale would have to know
that a stamp survives a soft-cancel, and would re-stamp correct decks at every
process start when it did not.

That date is the **commit** date, so a multideck deck uploaded on production
between this commit and the deploy keeps its old per-player slot. Deploying
promptly is what keeps that window shut; anything that falls in it is one
organizer re-upload.

**Run**: nothing. To read the guard without the app,
`uv run python -m backend.src.migrations --dsn "$DATABASE_URL"`.

**Proves it worked**: that report answers `deck-round-stamp: 0 row(s) to rewrite`
on every long-lived database — it counts what is still pending, so it answers 0
both before the rewrite has anything to do and after it is done. The rewrite
itself is proved by the shape the old per-player slot produced whenever a round
was voided being absent: no player holding two decks stamped with one round.

```sql
SELECT "full"->>'tournament_uid', "full"->>'user_uid', "full"->>'round'
FROM objects
WHERE type = 'deck' AND deleted_at IS NULL AND "full"->>'round' IS NOT NULL
GROUP BY 1, 2, 3 HAVING count(*) > 1;
```

**Owes afterwards**: nothing to tell anyone. Delete this section and the
`deck-round-stamp` entry in `backend/src/migrations.py` in one commit.
