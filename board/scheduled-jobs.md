> Elaborated context for a line in `BOARD.md`. Deleted with the line.

Doc-impact: `wiki/architecture.md`, `wiki/hazards.md`.

# The daily jobs that never fire

## The mechanism

Two facts that are individually reasonable and jointly fatal:

- APScheduler 3.x fires `IntervalTrigger(hours=N)` at **start + N**, not
  immediately. Firing immediately is a 4.0 breaking change, and we are on the 3.x
  `AsyncIOScheduler` API — 3.11.3 is what the deployed venv holds.
- The service unit sets `RuntimeMaxSec=1d`, primarily to re-fetch the krcg-static
  card data without a redeploy. One template, both inventories.

The jobs are registered a few seconds into startup, so a 24-hour job's first fire
falls at T0+24h+δ and systemd kills the process at T0+24h. The kill always
precedes the fire. This is not a race that a quieter restart schedule would win:
as deployed, a 24-hour interval job **cannot** run.

## What that costs

Fourteen days of the beta journal carry `Added job` lines for all four and not one
execution:

| Job | What stops happening |
|---|---|
| `sanction_cleanup` | expired sanctions never lift at 18 months, and never hard-delete at 30 days |
| `purge_deleted` | soft-deleted rows, and the orphaned avatar, banner and push-subscription side rows behind them, are never reclaimed |
| `promo_stock_recompute` | the self-healing consistency pass never corrects a drifted stock count |
| `twda_sync` | the archive reconciliation that is the historic Hall of Fame's only live source |

The three non-TWDA jobs are byte-identical at v1.0.2, so they are already dead on
production today. The archive sync is different: at v1.0.2 it still ran, chained
inside `run_vekn_sync` and therefore inheriting that chain's startup kick — the
journal shows it daily through 2026-08-19, matching 2177 of 2211 entries each
time. Un-chaining it moved it onto its own flag for good reasons and onto its own
timer as a side effect. Deploying it is what turns a working job into a fourth
dead one.

## Why the rest still works

Only a startup kick, or a period short enough to beat the restart, survives here.

- `vekn_sync` — explicit `asyncio.create_task` at startup; it runs minutes after
  each daily restart, which is why the corpus is current.
- `snapshot_generation` — a 15-minute trigger, plus its own startup kick.
- `rating_recompute` — its own 24-hour job never fires, but the function is called
  inside the VEKN chain, so the work happens anyway.
- `oauth_cleanup`, `vekn_push` — hourly, well inside the window.

The pattern to take from that list: the daily cadence we believed we had is
delivered by `RuntimeMaxSec=1d` plus two hand-written startup kicks, not by the
scheduler.

## Choosing the fix

Three shapes, and they are not equivalent:

- **A startup kick per job**, matching what `vekn_sync` and `snapshot_generation`
  already do. Cheapest and most local, but it re-runs the work on every restart —
  for the archive sync that is a 12 MB fetch and up to `MAX_CREATES_PER_RUN`
  reconstructions each time, which is exactly the burst the cap exists to prevent.
- **An explicit `next_run_time`** on each job. Fixes the first fire without
  re-running at startup, and leaves the trap in place for the next job someone adds.
- **A `CronTrigger` at a fixed hour.** The only one that survives an arbitrary
  restart schedule, and the only one under which "daily" means a time of day rather
  than an offset from the last restart. Recommended.

Whichever shape wins, the archive sync carries an ordering constraint that was
deleted along with the chain and is not currently expressed anywhere: a
reconstruction must not race the vekn-linked copy of the same event into the
corpus, which is why it used to run *after* the tournament sync.

## Proving it

The done-condition is deliberately observational rather than a test. The defect
lives in the interaction between a library's trigger semantics and a systemd
directive; nothing runnable in CI sees both. A restart cycle on beta does.
