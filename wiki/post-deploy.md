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
