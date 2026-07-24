# Nightly DB statement timeouts on the new prod stack (#507)

## Symptom

`canceling statement due to statement timeout` on the new stack, Jul 22 2026:
snapshot generation x3 (01:54 / 02:09 / 02:24 UTC) + VEKN batch push x1 (02:39).
The cancelled statements (from PG syslog):

- snapshot: `SELECT "public"::text, modified_at, uid FROM objects WHERE "public" IS NOT NULL AND type=$1 AND deleted_at IS NULL ORDER BY modified_at ASC, uid ASC LIMIT $2`
- push: `SELECT "full" FROM objects WHERE ... vekn_synced = false` (candidate scan)

## Diagnosis — disk I/O latency, NOT the causes first assumed

The original ticket blamed a collision with the nightly legacy-merge + backup.
**Disproved on the box** (all read-only, `ubuntu@46.226.104.123`):

- **Box is `Etc/UTC`.** The legacy merge (`archon-legacy-sync.timer`, 04:00 UTC)
  and cluster backup (`postgres-backup.timer`, ~03:13 UTC) both run AFTER the
  01:54–02:39 failure window. Neither was running during it.
- **`lock_timeout = 5000` fired nothing.** A lock-blocked statement dies at 5s
  with *lock timeout*; these died at 30s with *statement timeout* → time was
  spent EXECUTING, not waiting on a lock. Rules out the merge / a table lock /
  held row locks. (VEKN push also confirmed clean: its HTTP calls run OUTSIDE the
  `tournament_transaction` FOR UPDATE; the lock is a brief per-row save only.)
- **`sar` for the window: CPU 72–97% idle, RAM 78% free, no OOM, no swap thrash.**
  Not CPU-, memory-, or compute-bound. No heavy batch job on either stack.
- **`sar -d`: disk `await` = 20–55 ms/IO (55ms at 02:10, the worst window) at
  only 1–26% `%util` and tiny throughput.** The disk isn't busy — each I/O is
  just very slow (Xen `xvda`, hypervisor-level latency / noisy neighbour).

Mechanism: a cache-cold snapshot batch needs ~1000+ random heap reads (index in
`(type, modified_at, uid)` order ≠ heap order; plus `::text` detoast of large
JSONB) × ~30 ms each ≈ 30 s → trips the guard. The two DBs share one 128 MB
buffer while their combined working set is ~335 MB (`archon` 160 MB + `archondb`
175 MB), so they evict each other and every miss is a slow cold read. Snapshots
at 00:54 / 01:09 / 01:24 succeeded (warmer cache / lower latency); the later ones
hit a latency spike.

The legacy ranking query that also timed out (`get_ranked_members`) was a red
herring: its index EXISTS and is used (EXPLAIN: bitmap index scan, cost ~763,
~239 rows) — it died on the same cold-read × slow-disk, and only 2× all night.

## Fix (this commit — code)

Root cause is hosting disk latency, not a plan/lock/query bug, so: let the two
trusted, off-request, fail-safe batch jobs ride out a latency spike instead of
inheriting the 30 s *user-request* guard.

- `db.batch_read_connection()` — pooled connection with `statement_timeout=120s`,
  RESET on release (autocommit pool has no reset hook). Mirrors legacy archon's
  own `SET statement_timeout='120s'` on its bulk member-stream reads.
- `stream_objects_new(..., conn=)` — snapshot pins every batch to one
  relaxed-timeout session; SSE catch-up keeps the per-batch pool release.
- `snapshots.generate_snapshots` + `vekn_push.batch_push` use it.
- Merge's own pre-merge `pg_dump` (`migrate_from_archon.backup_new_db`) gets
  `nice -n10 ionice -c3` to yield to the live stacks (the box's `mq-deadline`
  ignores the ioclass — correct + future-proof, harmless).

The snapshot was already fail-safe (temp file + atomic rename → a slow-but-
completing gen serves the last good file meanwhile); 120 s just lets it finish.

## Residual / deploy notes (not code)

- **Config drift:** prod inventory already has `effective_cache_size: 384MB` and
  `shared_buffers: 96MB`, but the running cluster shows PG stock 4GB / 128MB —
  the PG memory tuning was never applied. A postgresql-role redeploy applies 384MB
  (reload) — corrects the planner's 4× cache overestimate that biases it toward
  random index-order heap access. `shared_buffers` stays small BY DESIGN (rely on
  OS page cache on the tiny box); do NOT grow it.
- **Durable cure:** Phase-4 legacy decommission frees the whole box + cache for
  the new stack — removes the cross-DB eviction entirely.
- **#514** — switch the full-snapshot read to a sequential heap scan (drop the
  ORDER BY) so it stops doing cold random I/O on this disk.
