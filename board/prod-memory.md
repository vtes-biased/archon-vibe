# Production memory thrashing

Doc-impact: `wiki/dev.md` (Deployment — memory breakdown and working headroom);
`wiki/architecture.md` only if pool sizing changes.

## Evidence (2026-09-23, owner-run, read-only)

- `free -m`: 945 total, 750 used, 61 free, 373 buff/cache, **194 available**;
  swap **323 MB used** of 4095.
- `/proc/pressure/memory` at sample time: all averages 0.00, but cumulative
  `some total=15211262975` µs (≈4.2 h) and `full total=13612888908` µs (≈3.8 h)
  since boot — episodes are total stalls (thrashing), not a steady squeeze.
  Uptime not yet captured, so the rate is unknown.
- `vmstat 5 6`: si/so 0 during the sample; since-boot average ≈9 kB/s each way.
- RSS: backend `uvicorn` **350 MB** (single worker); postgres backends ~113 MB
  each, mostly the 96 MB shared_buffers counted repeatedly — the unit's
  `MemoryCurrent` is 281 MB; `archon-bot` 23 MB; the public-API `uvicorn` is
  absent from the top 15 (likely swapped out).
- systemd reports `MemoryCurrent=[not set]` for the three archon units: no
  per-unit accounting for them.
- The backend logs "Snapshots unchanged at 36683 objects, skipped" every 15 min.
  Ruled out: generation streams, a full rebuild costs +10 MB, a skip 20 ms.

## Prod baseline (2026-09-23, owner-run)

Up since 2026-08-24 16:54 (29.5 days): `full total` 13,614 s ≈ 7.7 min/day on
average, possibly bursty. 210 MB available, 326 MB swap. `archon-backend` last
entered active 2026-09-22 09:35 UTC, so its daily restart falls near 09:35-09:40
UTC — clear of the 03:00 backup and 05:00 TWDA sync. Next: a day of per-minute
`/tmp/psi.log` samples before the deploy, a day after.

## Beta attribution (2026-09-23, same 36,683-object corpus)

One boot of the old code: imports 134 MB (fpdf alone 34), idle 156, member
fetch +36, `_build_users_by_vekn_id` +65 (19k decoded users for a uid lookup),
settled at 292 MB, HWM 333. Standalone: rating pass 2 +72 MB, TWDA fetch +69 MB.
glibc retains freed heap (`malloc_trim(0)` returns it), so each peak stays
resident until the daily `RuntimeMaxSec` restart, and every boot re-runs the
VEKN chain. The cuts in the landing commit, re-measured on beta: imports 103 MB,
uid map no measurable peak, TWDA +22, full rating recompute +44 (0 users
changed, so the rewrite is equivalent).

## What prod still has to show

Whether the stall episodes line up with the backend's boot chain (its restart
time moves daily with `RuntimeMaxSec`) or with backup/restore-verify, and
whether they stop once the deploy carrying the cuts is live. The prod unit
names may differ from beta's `new-archon-*`.

Current tuning (keep or change explicitly): `postgresql_shared_buffers: 96MB`,
`postgresql_max_connections: 20`, `DB_POOL_MAX_SIZE: 8`,
`PUBLIC_API_DB_POOL_MAX_SIZE: 4`, swapfile enabled.

## Measurement commands (owner executes on prod)

Uptime, a baseline, and when the backend last booted:

```
ssh ubuntu@46.226.104.123 'uptime -s; cat /proc/pressure/memory; free -m; systemctl list-units --no-legend "*archon*backend*" | cut -d" " -f1 | xargs -r systemctl show -p Id -p ActiveEnterTimestamp'
```

Around the 03:00 UTC backup (run before ~02:55 and after ~03:15), and around a
deploy or a Wednesday 06:00 UTC restore-verify:

```
ssh ubuntu@46.226.104.123 'date -u; cat /proc/pressure/memory; ps -eo rss,comm --sort=-rss | head -8'
```

The delta of `full total` across a window attributes the stall to what ran in it.
