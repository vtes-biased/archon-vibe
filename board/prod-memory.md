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
- The backend logs "Snapshots unchanged at 36683 objects, skipped" every 15 min
  — prime suspect for the resident size.

Current tuning (keep or change explicitly): `postgresql_shared_buffers: 96MB`,
`postgresql_max_connections: 20`, `DB_POOL_MAX_SIZE: 8`,
`PUBLIC_API_DB_POOL_MAX_SIZE: 4`, swapfile enabled.

## Measurement commands (owner executes on prod)

Uptime and a baseline:

```
ssh ubuntu@46.226.104.123 'uptime -s; cat /proc/pressure/memory; free -m'
```

Around the 03:00 UTC backup (run before ~02:55 and after ~03:15), and around a
deploy or a Wednesday 06:00 UTC restore-verify:

```
ssh ubuntu@46.226.104.123 'date -u; cat /proc/pressure/memory; ps -eo rss,comm --sort=-rss | head -8'
```

The delta of `full total` across a window attributes the stall to what ran in it.
