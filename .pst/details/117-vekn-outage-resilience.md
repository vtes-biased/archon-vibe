# 117 — VEKN API outage resilience

Goal: the app must function fully if vekn.net is unreachable for hours or days, warn users
where it matters (unpushed member/event), and resync gracefully on recovery.

## Investigation findings (2026-06-10)

### What already works (no ticket needed)

**Push side (Archon → VEKN)** — eventual delivery by construction:
- Local save + SSE broadcast happen *before* any push attempt; push failure never loses or
  blocks local data (e.g. `routes/vekn.py` sponsor: save → broadcast → push).
- Pending work is flagged on the objects themselves: `vekn_synced=false` (member),
  `external_ids.vekn` null (tournament event), `vekn_pushed_at` null (results).
- `batch_push()` (`vekn_push.py:294`) retries all three flag-queues hourly
  (`VEKN_PUSH_INTERVAL_HOURS`, gate `VEKN_PUSH`). Per-item try/except — one bad item
  doesn't sink the batch. Results push auto-creates the missing calendar event first.
- So a multi-day outage self-heals: first hourly batch after recovery drains the backlog.

**Pull side (VEKN → Archon)** — non-destructive by construction:
- `sync_all_members()` only creates/updates from fetched rows; members missing from a
  partial fetch are left untouched — never deleted or role-stripped.
- `fetch_all_members()` skips a failed prefix (`continue`) → partial roster is safe;
  full-outage auth failure raises before any row is processed → cycle skipped entirely.
- `vekn_tournament_sync` has no delete path; failed event fetches are skipped.
- Failed sync cycle: error logged in `main.py`, stale data kept, retried in 6h
  (`VEKN_SYNC_INTERVAL_HOURS`). APScheduler default `max_instances=1` → no overlap pile-up.
- Nothing else depends on vekn.net at runtime: auth is Discord/email, VEKN ID allocation
  on sponsor is local (prefix+increment), bot goes through the backend only.

### Gaps (the children)

| # | Gap | Severity |
|---|-----|----------|
| 118 | Real-time pushes awaited inline in request handlers → tournament create / finish action / sponsor / member create stall 30–120s while VEKN times out (aiohttp connect=30, total=120) | p2 |
| 119 | `vekn_push.py` saves drop their `BroadcastData` → clients keep stale vekn flags until reconnect; badges wouldn't clear live | p2 |
| 120 | No user-visible warning when a member/event push is pending — failures are log-only; fields already reach frontend (`types.ts`) but unused | p2 |
| 121 | `batch_push` has no fail-fast: full outage → every pending item serially re-times-out; also `asyncio.TimeoutError` (aiohttp total timeout) isn't wrapped into `VEKNAPIError` | p3 |
| 122 | Push functions save whole stale object snapshots (worst in batch: rows loaded up front, saved much later) → lost-update on interim edits | p3 |
| 123 | No observability: no last-success/last-error tracking for sync/push jobs; a days-long outage is invisible except in logs | p3 |

### Key code refs
- Client + timeouts: `backend/src/vekn_api.py:60-130` (`VEKNAPIClient`, `_authenticate`,
  `ClientTimeout(total=120, connect=30, sock_read=60)`)
- Push: `backend/src/vekn_push.py` (whole file); inline call sites
  `routes/tournaments.py:521,993`, `routes/vekn.py:253`, `routes/users.py:155`
- Pull: `backend/src/vekn_sync.py:746` (`sync_all_members`),
  `backend/src/vekn_api.py:497` (`fetch_all_members`)
- Scheduling: `backend/src/main.py:261-340` (lifespan jobs)
- Existing tests: `backend/tests/test_vekn_push.py` (archondata format only — no
  network-failure coverage; add some with 118/121)

## Resolution (2026-06-11)

All six children landed. Closing the epic.

- **118** fire-and-forget real-time pushes (asyncio.create_task) — done earlier
- **119** broadcast vekn_push.py saves so badges clear live — done earlier
- **120** frontend pending-sync badges (VITE_VEKN_PUSH gated) — done earlier
- **121** fail-fast circuit + timeout wrapping:
  - `VEKNAPIConnectionError(VEKNAPIError)` in `vekn_api.py` marks batch-fatal
    failures (transport/timeout/auth). `_authenticate` raises it for missing/bad
    creds + HTTP errors; `create_event`/`upload_results`/`create_member` now
    catch `(aiohttp.ClientError, TimeoutError)` (aiohttp total-timeout is
    `TimeoutError`, NOT a `ClientError`) → wrap into it.
  - push functions re-raise `VEKNAPIConnectionError` (swallow only data-class
    `VEKNAPIError`); `batch_push` aborts the whole run on the first one and sets
    `stats["aborted"]=True`. Per-item data errors still skip+continue.
- **122** lost-update: push functions re-fetch the User/Tournament immediately
  before writing the vekn flags, so a minutes-late backlog drain writes onto a
  fresh snapshot instead of the stale one. Narrows clobber window to µs.
- **123** observability: `vekn_status.py` (in-process last success/error per job)
  + `GET /admin/vekn-status` (IC-gated). `run_vekn_sync`/`run_vekn_push` record
  outcomes. UI widget added to the existing IC AdminSection (profile page):
  per-job status dot + last success / last error, loads on expand and after a
  manual run. `getVeknStatus()` in api.ts (justified GET — in-process state, not
  a synced object type). 10 i18n keys across all 5 locales.

Tests: 2 fail-fast regression tests in `test_vekn_push_batch.py` (connection
error aborts; data error skips+continues). Full backend suite green (207);
frontend svelte-check clean.
Docs: VEKN_SYNC.md "Outage resilience" subsection + one-line ARCHITECTURE.md note.
