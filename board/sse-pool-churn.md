# Abandoned stream connects burn production database connections

Doc-impact: `wiki/sync.md`, `wiki/hazards.md`.

## What production logged

Three occurrences in the ~27 hours of `archon-backend` journal covering
2026-08-16 00:00 → 2026-08-17 03:00, the only window pulled. Every one has the
identical shape: a stream connect opens, the warning lands 3–8 ms later, the
connection is discarded, and the client reconnects successfully within 20 ms–2 s.
None of the three produced a `Sync complete` for the dying connection.

```
Aug 16 08:56:03,286  SSE connection opening: user=anon full-corpus
Aug 16 08:56:03,307  psycopg WARNING - error ignored in rollback on
                     <psycopg.AsyncConnection [ACTIVE] (user=archonvibe database=archon)>:
                     sending query failed: another command is already in progress
Aug 16 08:56:03,307  psycopg.pool WARNING - closing returned connection
Aug 16 08:56:03,308  psycopg.pool WARNING - discarding closed connection: [BAD]
Aug 16 08:56:03,308  SSE connection closed (user=anon full-corpus)
```

The other two are byte-identical but for the user and the address:

- `Aug 17 01:06:32,585` → warning at `,588` → closed at `,591`; user
  `019f1a00-7a7b-7200-8f07-46856185c3f1` (member, an organizer), reconnecting at
  `,607` and completing a normal delta at `,686`.
- `Aug 17 01:56:01,441` → warning at `,449` → closed at `,451`; user
  `01a00d6e-ccd4-76c9-8bdc-c71882104a65`, seconds after a Discord OAuth callback —
  so an entitlement change had just moved that viewer's access version.

The journal rotates; these five lines are the whole observed evidence.

## Mechanism

The client hangs up while a pooled query is still in flight. asyncio cancels the
task, psycopg tries to roll back a connection whose command is still `ACTIVE`,
cannot, and the pool discards it and opens a fresh one.

Two places on the stream path are exposed, and the `anon` occurrence proves it is
not just one of them:

- **The catch-up batches.** `stream_objects_new` acquires and releases a pooled
  connection around every yield, which stops a slow reader *pinning* a slot across
  its read — but that is a different protection. It does nothing about a
  cancellation landing *inside* a batch fetch, which is what a hang-up delivers.
- **The connect handshake.** Resolving the viewer and computing the access version
  read the database before the response generator runs, and for a member-level
  viewer the access version additionally queries the organized-tournament set.
- **The personal overlay**, built on a pooled connection for member-level viewers.

None of it is shielded.

The `Aug 16 08:56:03` occurrence is `user=anon`, and that settles the scope. The
viewer is resolved *before* the "opening" log line, so it cannot be the query still
`ACTIVE` 21 ms later. And the access version does no database work at all for an
anonymous viewer — its only query is guarded by `viewer and level == "member"`, and
`base_data_level` is synchronous. An anonymous connect therefore issues **no
handshake query whatever**, and takes no overlay either. The command being rolled
back can only be a catch-up batch.

So shielding the handshake alone would leave this exact occurrence firing. The two
member-level occurrences (3–8 ms) fit either the organized-tournament query or the
first batch, and there is no need to decide which: the scope is every pooled query
on the stream path.

## The remedy is already a recorded decision

`wiki/public-api.md` states it: a reader hanging up mid-stream "otherwise cancels a
query in flight and the pool discards a connection it cannot roll back", so each
batch query is shielded. That decision was implemented exactly once —
`backend/src/public_api/v1.py:45` is the only `asyncio.shield` in the backend:

```python
async def _fetch(sql, params):
    # Shielded: a reader hanging up mid-query costs the pool the connection.
    async def run():
        async with get_connection() as conn:
            cur = await conn.execute(sql, params)
            return await cur.fetchall()

    return await asyncio.shield(run())
```

The app's own stream, which every client hits on every reconnect, never got it.

## What the wiki gets half-right

`wiki/sync.md` says the forced-resync branch returns immediately because "streaming
the corpus after the resync line is wasted work that also discards a pooled
connection on the client's mid-fetch teardown". That is **true** — for a client
being told to resync. The early return means it never enters the catch-up loop, so
there is no batch left to cancel mid-fetch.

What the page leaves unsaid is that this spares only the resyncing client. An
ordinary connect — no entitlement change, just a since-delta — runs the same
catch-up loop with the same exposure and no early return to save it. That is where
the observed discards come from: the `anon` occurrence reached a batch, so it was
not on the resync path at all.

So the correction owed is not a deletion. The early return is a targeted
optimisation that happens to spare one path; it is not the general protection, and
the page should stop reading as though it were. The shield is the general
protection.

## Why it is worth fixing rather than tolerating

No data is at risk: the pool is autocommit, so a cancelled read leaves nothing
partial behind, and the pool self-heals.

The cost is availability on the hottest endpoint. Production runs
`DB_POOL_MAX_SIZE: 8` (`ansible/inventories/prod/group_vars/all/vars.yml`), not the
library default of 20 — so each abandoned connect burns one slot of eight and pays a
fresh Postgres connect and authentication to refill it. Three a day is noise; the
concern is the burst. The first resync after an access-version change reconnects
with **no delay** by design, so anything that re-levels a group of viewers at once
produces precisely the simultaneous connect-and-abandon pattern that turns three a
day into a spike against eight slots.

## The second cost: a cursorless connect streams the whole corpus

Measured on prod 2026-08-25. `stream_updates` sets `effective_since = since` and
passes it straight to `stream_objects_new`. A connect carrying **no** `since` at
all therefore streams every object the viewer may see, from the database, over one
pooled connection:

```
Aug 25 04:09:38  Sync complete (user=019f19ff-… full-corpus):
                 19106 user, 0 sanction, 9591 tournament, 4823 deck, 21 league, 0 promo in 5.321s
Aug 25 04:09:49  Sync complete (user=019f19ff-… full-corpus):   (the same viewer, 11 s later)
                 19106 user, 0 sanction, 9591 tournament, 4823 deck, 21 league, 0 promo in 3.197s
Aug 25 04:48:53  Sync complete (user=019f1a00-… full-corpus):
                 19106 user, 0 sanction, 9591 tournament, 4823 deck, 21 league, 0 promo in 12.905s
```

33,541 objects, three to thirteen seconds, one of eight slots each time. The
`full-corpus` label is not the diagnosis — it is `main.py`'s word for any stream
that is not bot-scoped — but the per-type counts are, since they are the whole
corpus rather than a delta.

`wiki/sync.md` says a first connect with no `since` fetches the pre-computed
snapshot "instead of streaming from scratch". That is a **frontend convention with
no server-side guard**: the server serves the corpus to whoever asks. Any client
that has lost its cursor — cleared storage, a private window, a new device, a
failed snapshot fetch, an errored ingest — takes the database path instead, and the
production log shows it happening several times an hour on an ordinary day.

The server already knows the cheap answer. `main.py:1142`, on the forced-resync
branch, yields `{"type":"resync"}` and returns, under the comment *"streaming the
corpus after it is wasted, and a mid-fetchall teardown discards the pooled
connection"* — the exact reasoning, applied to the exact shape of request, that a
bare cursorless connect never reaches.

**This is why the two costs are one line.** The long stream is what gives a hang-up
time to land mid-query; the shield is what stops that hang-up costing a connection.
Fixing either alone leaves the European Championship exposed: shielding without the
guard still pins eight slots for seconds at a time under a mass reconnect, and the
guard without the shield still discards a connection whenever a delta is cancelled.

The trap to avoid when implementing: answering a cursorless connect with `resync`
sends the client to `/snapshot`, which **503s until a snapshot file exists**. A
client that loops connect → resync → failed snapshot → connect is worse than the
corpus stream it replaced.

## Verification

Reproduce locally rather than waiting on production: hang up a few milliseconds into
a stream connect that is mid catch-up against a local backend — an anonymous connect
carrying a `since` old enough to produce batches is the cleanest shape, since it
isolates the loop from the handshake — and watch for
`discarding closed connection`. Absence of that line, with the connection returned
to the pool, is the proof. A production log check afterwards can only ever show
absence of evidence, so it is a confirmation, not the gate.

For the cursorless path, connect with no `since` and assert the response is the resync directive rather than a corpus stream, then confirm a snapshot-less backend does not put the client in a loop.
