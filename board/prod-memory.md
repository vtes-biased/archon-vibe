# Production memory thrashing

Doc-impact: `wiki/dev.md` (Deployment — memory breakdown and working headroom);
`wiki/architecture.md` only if pool sizing changes.

## Evidence (2026-09-23, owner-run, read-only)

- `free -m`: 945 total, 750 used, 61 free, 373 buff/cache, **194 available**;
  swap **323 MB used** of 4095.
- `/proc/pressure/memory` at sample time: all averages 0.00, but cumulative
  `some total=15211262975` µs (≈4.2 h) and `full total=13612888908` µs (≈3.8 h)
  since boot — episodes are total stalls (thrashing), not a steady squeeze.
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
samples before the deploy, a day after.

## Beta attribution (2026-09-23, same 36,683-object corpus)

One boot of the old code: imports 134 MB (fpdf alone 34), idle 156, member
fetch +36, `_build_users_by_vekn_id` +65 (19k decoded users for a uid lookup),
settled at 292 MB, HWM 333. Standalone: rating pass 2 +72 MB, TWDA fetch +69 MB.
glibc retains freed heap (`malloc_trim(0)` returns it), so each peak stays
resident until the daily `RuntimeMaxSec` restart, and every boot re-runs the
VEKN chain. The cuts in the landing commit, re-measured on beta: imports 103 MB,
uid map no measurable peak, TWDA +22, full rating recompute +44 (0 users
changed, so the rewrite is equivalent).

## Landed

`4e76ad6f` (the streaming cuts, `wiki/dev.md` rule) and `19413c3b` (review
fixes) are on main, **not yet deployed to prod**, and so is the follow-up that
trims the heap after every job, builds the city index per member sync, drops
krcg's card DB from the deck proxy and **moves the VEKN chain off boot to 04:00
UTC** — so a restart no longer pays the chain's peak, and step 5 reads after
04:00. Prod units: `archon-backend`,
`archon-bot`, `archon-public-api`; no systemd memory accounting, so read RSS
from `/proc`.

Current tuning (keep or change explicitly): `postgresql_shared_buffers: 96MB`,
`postgresql_max_connections: 20`, `DB_POOL_MAX_SIZE: 8`,
`PUBLIC_API_DB_POOL_MAX_SIZE: 4`, swapfile enabled.

## Resume here (owner executes every prod command)

The pre-deploy sampler log was lost: it wrote to `/tmp`, which the 2026-09-25
reboot wiped. The "before" is therefore the 29.5-day average above (≈7.7 min/day
of full stalls); no second pre-deploy day is being collected. Commands go through
each developer's `archon.vekn.net` alias, and the journal of system units needs
`sudo`.

1. **Deploy** a release carrying `19413c3b` and `f0fd0ca7` to prod (owner's call
   on timing).
2. **Start the sampler** right after, into `/var/tmp` so a reboot keeps the log
   (the sampler itself stops at a reboot):

   ```
   ssh archon.vekn.net 'nohup sh -c "while :; do echo \$(date -u +%FT%TZ) \$(grep full /proc/pressure/memory | cut -d\" \" -f5) \$(free -m | awk \"/Mem/{print \\\$7}\"); sleep 60; done" > /var/tmp/psi.log 2>&1 &'
   ```

3. **Collect a day later** — prints the log, stops the sampler, lists the job runs:

   ```
   ssh archon.vekn.net 'cat /var/tmp/psi.log; pkill -f "psi.log"; sudo journalctl -u archon-backend --since "-25h" --no-pager | grep -E "Running job|starting|complete" | cut -c1-160'
   ```

4. **Attribute.** Per-minute deltas of `total`; match each jump against: 01:00
   sanction cleanup, 01:30 purge, 02:00 promo stock, 02:30 rating recompute,
   03:00 backup, 04:00 VEKN chain, 05:00 TWDA sync, Wednesday 06:00
   restore-verify, the hourly VEKN push, and the backend's daily `RuntimeMaxSec`
   restart (drifting; it no longer runs the VEKN chain).
5. **Backend settled size and peak**, once the 04:00 UTC chain has run:

   ```
   ssh archon.vekn.net 'grep -E "VmRSS|VmHWM" /proc/$(systemctl show archon-backend -p MainPID --value)/status; free -m'
   ```

6. **Close the line**: the Deployment section of `wiki/dev.md` gets the
   backend's settled RSS and HWM, the box's memory breakdown and working
   headroom; delete the board line and this file. If stalls remain, name what
   drives them — a further cut is an ordinary `/intake` line.
