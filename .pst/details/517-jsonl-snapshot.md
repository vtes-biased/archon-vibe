# 517 — one-pass JSONL snapshot

Decisions taken 2026-07-26, on top of the ticket body. The ticket states the *what*;
this records the *how* where the implementation deviates from it, and why.

## Cursor: `generated_at`, not `max(modified_at)`

The ticket proposed taking `max(modified_at)` up front inside a REPEATABLE READ
transaction so `timestamp` could move to a header line. Rejected: there is no usable
index for that aggregate (`idx_objects_type_modified` is `(type, modified_at, uid)`;
PostgreSQL will not skip-scan it), so it costs an extra whole-heap scan in a change
whose entire point is removing scans.

Instead the cursor is the generation instant — `SELECT now()::timestamp` taken before
any row is read. Shipped ahead of this ticket as its own fix (see the closed
`meta.timestamp` ticket) because it was a live correctness bug, not a rewrite concern.
Both meta fields carry that one value.

## REPEATABLE READ is unnecessary

The ticket wanted RR so the three level files would be mutually consistent. With a
single cursor over all types and all three level columns, that falls out for free: a
`DECLARE`d cursor holds one MVCC snapshot for its whole lifetime even under READ
COMMITTED. RR would add nothing, so it is not used.

## Format

Gzip JSONL. One JSON object per line:

```
{"type":"header","version":2,"timestamp":"…","generated_at":"…"}
{"type":"user","data":{…}}
…
{"type":"eof","count":30216}
```

The ticket asks for the timestamp in a header line. The `eof` trailer is *added* on
top: streaming ingest is exactly what gives up the "a corrupt file leaves IndexedDB
untouched" property, so the client needs a sentinel to tell a complete file from a
truncated one. Header gives an early version check, trailer gives completeness.

Object lines are built by string concat around the raw `{level}::text` column, so the
no-Python-deserialization property survives.

## Transition: clean break + forced SW update

Owner's call. No dual-format window, no `?format=` negotiation — the server emits
JSONL only and the new client parses JSONL only.

Exposure is a browser holding a cached JS bundle when the new backend deploys. It is
narrower than it looks: a client with a `lastSync` cursor never fetches a snapshot at
all, so only fresh bootstraps and forced resyncs are affected. The nasty case is a
forced resync, which clears IndexedDB *before* refetching.

Mitigation: `initServiceWorker` now auto-applies a worker that was left `waiting` from
a previous visit (skipWaiting + reload) instead of waiting for the user to click the
update banner. The banner stays for updates that appear *during* a session — and the
auto-apply is suppressed when a tournament is offline-locked, same invariant the banner
already respects (`!hasOfflineLocked` in +layout.svelte). Never reload out from under an
organizer running a tournament.

## Ingest atomicity

`clearAllStores()` used to run after a successful whole-file parse. Streaming gives that
up, so a `snapshot_ingest_in_progress` marker goes into the `metadata` store *before*
the clear and is removed only when the `eof` line lands. `connect()` treats a surviving
marker as "no usable snapshot": clear and refetch. Covers truncation, mid-ingest tab
close, and a superseded connect epoch.
