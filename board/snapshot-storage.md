Doc-impact: `wiki/sync.md`, `wiki/hazards.md`, `wiki/dev.md`.

## Cause

A cold pass makes about 31k out-of-line TOAST lookups, 84% of them non-contiguous,
so it reads one page at a time. Production's volume answers in 1–5 ms normally and
50–280 ms in spells that come and go at no load, outside the 00:00–04:00 UTC window
`wiki/hazards.md` gives too. A pass took 12 s warm and 615 s at worst. TOAST reads
skip the seq-scan ring, so they also flush `shared_buffers`. Production on
2026-11-01: heap 93 MB, TOAST 141 MB, indexes 34 MB, `shared_buffers` 96 MB.

## Measured on beta, 2026-11-01 (36k objects, read_ahead_kb 128 unless stated)

| Cold pass | Device reads | `shared_buffers` |
|---|---|---|
| Today's layout | 8,779 | 105 MB |
| Today's layout, 1 MB read-ahead | 5,354 | 103 MB |
| Rewritten, default storage | 3,134 | 89 MB |
| `pg_prewarm` then pass (rejected) | 1,697 | 105 MB |
| `STORAGE MAIN` | 1,443 | 31 MB |
| `MAIN`, 512 KB read-ahead | 439 | 30 MB |
| `MAIN`, 1 MB read-ahead | 286 | 30 MB |

After 1,000 tournament saves, `MAIN` read 4% more and default storage 12% more.
Cold narrow queries: catch-up 536 to 837 reads, open-tournament scan 248 to 423,
country filter unchanged.

## Procedure, proven on beta

`ALTER COLUMN … SET STORAGE MAIN` on `public`, `member`, `api` and `full` moves
nothing by itself; `VACUUM FULL objects` then pulls existing values into the row
(4.7 s under its lock, row count and newest `modified_at` unchanged; heap 136 MB,
TOAST 30 MB, 5,464 values still out of line). Beta's `objects` is already rewritten.

## Traps

- Production's rewrite: a quiet daytime slot outside the slow window, latency checked
  first, `lock_timeout` and `statement_timeout` at 0 for the session. The database
  sets 5 s and 15 s, and the slow disk can hold the lock for far longer than beta did.
- `schema.sql` runs at every boot: an `ALTER` there must not take an exclusive lock on
  each start if the setting is already in place.
- Read-ahead was set by hand on beta and restored to 128; production needs it
  persisted, on `xvda`, through `deploy/setup.py`.
- `idle_in_transaction_session_timeout` is 60 s: any wait between FETCHes stays well
  under it.

## Fallback

If cold passes still stall production: patch the previous files from changed rows
only. The prototype took 2.2 s of CPU and 21–27 MB locally, and about 130 cold pages
for 50 rows.
