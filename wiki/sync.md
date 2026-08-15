# Sync

PostgreSQL → FastAPI → SSE → browser → IndexedDB. Every UI read comes from
IndexedDB; the stream is how it gets there.

## Access levels

Three levels decide what each viewer receives. They are *visibility*, a separate
axis from the authorization predicates in [access](access.md).

| Level | Viewer | Gets |
|---|---|---|
| `public` | no token, or no `vekn_id` | Prince/NC users with base64-obfuscated contact, the event-page fields of every tournament, leagues minus their organizer roster, no sanctions |
| `member` | has a `vekn_id` | all users without contact, all sanctions, tournaments with standings and filtered decks |
| `full` | IC, NC of the same country, organizer | everything, including rounds, finals, `checkin_code` |

`access_levels.py` computes all three projections at **write time**:

| Type | `public` | `member` | `full` |
|---|---|---|---|
| user | NC/Prince only, with contact + community links; IC without contact | all users — no contact, no `deceased_by_uid`, no `github_login`/`github_id`; `deceased_at` included; anyone with non-empty community links gets those included | everything except `calendar_token` |
| tournament | the event-page fields — config, venue/address/map, description, rules flags, `banner_path`: everything an unauthenticated visitor needs to decide whether to attend | all except `checkin_code`, `vekn_pushed_at`, `vekn_results_stale`, `twda_status` | everything |
| sanction | none | full data | full data |
| deck | none | full data when `public = true`, else none | full data |
| league | full data **except `organizers_uids`** | full data | full data |
| promo | catalog only, no `holdings` | same as public | everything including `holdings` |

"None" means the column is NULL and the object is invisible at that level.

The tournament public projection is an **allowlist** (`_TOURNAMENT_PUBLIC_FIELDS`),
with one conditional: on an online event `venue_url` is the *join* link rather than
a venue website — the form defaults it to a Discord invite — so it is withheld, and
the calendar withholds it the same way.

The tournament member projection is the mirror image, a **denylist**
(`_TOURNAMENT_MEMBER_EXCLUDE`): any new Tournament field is member-visible by
default, so an organizer-only secret must be added to that list or it leaks.

A league's `organizers_uids` is stripped at public level because ordinary members
have no public projection at all — a published organizer uid would resolve to
nothing client-side and render as a raw uid fragment.

**Booleans need an explicit decision.** Omitting a field withholds it, but omitting
a `bool` *misinforms*: after JSON, absent and `false` are indistinguishable, so the
client reads a missing flag as `false`. Never rely on omission to hide one.

**A projection change only affects rows saved afterwards.** Existing rows keep
their stored columns until something writes them again, so changing a projection
function silently leaves the corpus on the old shape.
`backend/scripts/reproject_public.py` re-saves every tournament and league to
rebuild the columns and bump `modified_at`, which is what forces synced clients to
re-fetch. Reuse that pattern post-deploy for any projection change — a raw SQL
column rewrite cannot run the Python projections and leaves clients on stale rows.

### Access entitlement

`entitled_level(viewer, *, obj_type, uid, country, org_uids, obj_user_uid)` in
`broadcast.py` is the **single source of truth** for per-object access, called by
both the live broadcast and the tournament-scoped catch-up. IC → full; NC of the
same country → full; explicit organizer → full; a member's own profile or deck →
full; any member → member; otherwise public. One exception: **NC gets full on promo
objects regardless of country**, because the IC→NC→organizer inventory chain is not
country-scoped — Princes and organizers stay at member.

Adding a full-access branch here wires only the **live** path. A non-country,
non-own-object full grant must *also* be added to the overlay frames in `main.py`,
or a resync re-delivers the lower projection.

## What members actually receive

Access is enforced per row, not per viewer, so the member projection of a
tournament ships the **entire** object — all rounds, finals and per-player results
— to **every** member, excluding only `checkin_code`, `vekn_pushed_at`,
`vekn_results_stale` and `twda_status`. During a live event, full structural data
sits in every member's IndexedDB.

Two real server-side boundaries exist inside the member level:

- **Decks** are a separate object type with their own per-deck member projection.
  A deck ships only when the engine sets its `public` flag. That row *is* access
  control.
- The four excluded tournament fields above.

Everything else is a **frontend display default**, not an access boundary:
`standings_mode`, the "my tables" view, and the ongoing-event hiding of per-player
results are rendered client-side from data the client already holds.

| Field | Server boundary? | Display default |
|---|---|---|
| Config | — always shipped | shown |
| Players | no — full per-player data shipped | per-player results hidden mid-event |
| Standings | no | per `standings_mode` |
| Decks | **yes** — per-deck `public` flag | — |
| Finals | no — shipped | hidden until finished |
| My tables | no — all tables shipped | only the viewer's own |
| Rounds | no — shipped | hidden |
| `checkin_code`, `vekn_pushed_at`, `vekn_results_stale`, `twda_status` | **yes** — stripped | — |

This is an accepted trade-off. Viewer-specific visibility cannot be expressed in
pre-computed per-row columns, and frontend hiding suits the threat model — a local
event attendee is not expected to crack open IndexedDB to influence standings.
Making a display default a real boundary would need a per-player overlay, more
complexity than the risk warrants. **Treat the matrix as UI defaults, not a
security guarantee.**

### Anonymous display gates

A further frontend layer gates on authentication. Logged-out visitors see a reduced
UI, but the `public` projection on the wire is unchanged: officials' contact
details still flow over SSE into IndexedDB for anonymous viewers, base64-obfuscated.
Officials are meant to be reasonably contactable so newcomers can join the
association; the obfuscation is a harvest speed-bump, not access control. **Do not
"fix" this by stripping the public projection** — that reverses a deliberate
decision.

| Surface | Logged-out display | On the wire? |
|---|---|---|
| Officials directory | hidden | yes, public projection |
| Members tab | sign-in prompt | partial — officials and link-holders only |
| Tournament list | current and upcoming only | yes, full list in IndexedDB |
| League list | active only | yes |
| Finished tournament detail | accessible by direct link | yes |

The `.ics` feeds carry venue and address for anonymous subscribers too, which is
not an exception: both are public-projection fields —
[architecture](architecture.md#calendar).

## Streaming

Two object streamers read the pre-computed columns and yield raw JSONB text
strings with no Python deserialization. **SSE serves raw JSON via
`SELECT col::text`** — never reintroduce a parse → Struct → reserialize cycle; that
was the original performance sink, and zero re-serialization on the stream path is
the design intent.

**`stream_objects_new()`** (SSE catch-up, rating recompute) uses keyset pagination:
`WHERE (modified_at, uid) > (%s, %s)`, tie-safe across batch seams, `ORDER BY
modified_at, uid LIMIT batch_size`. A pooled connection is acquired and **released
before each yield**, so a slow client never pins a pool slot through its catch-up
and the heap holds at most one batch. The ORDER BY is load-bearing: the client's
`since` high-water mark must advance monotonically.

**`stream_objects_snapshot(conn)`** is an unordered whole-corpus scan — one pass for
*all* types and *all three* levels, yielding `(type, public, member, full)`. A full
snapshot captures every non-deleted row and needs no ordering, so dropping the
ORDER BY lets Postgres pick a bitmap or sequential heap scan (physical-page order,
sequential I/O) over the index-order random I/O that punished the latency-bound
production disk. It filters `deleted_at IS NULL` — fresh clients need no tombstones
— and streams through a server-side cursor DECLAREd in an explicit transaction,
since autocommit forbids a bare one. Its batch size is far below the ordered
streamer's because each row now carries three projections.

> Plan checks must `EXPLAIN` the `DECLARE … CURSOR FOR`, not the bare `SELECT`. A
> named cursor is costed with `cursor_tuple_fraction` (default 0.1), which biases
> toward low-startup plans and can report a different scan than the one that runs.

### Credentials

`/stream` and `/snapshot` accept credentials two ways, resolved by
`_resolve_viewer()`: the browser's `EventSource` cannot set headers, so it passes
`token=` as a query parameter; the Discord bot sends an `Authorization: Bearer`
header, resolved revocation-aware with `oauth_access` and `user:impersonate`
support.

**An invalid credential yields 401, never a silent downgrade.** Only a wholly
absent credential gives anonymous → `public`. Clients react: the bot checks expiry
before connecting and refreshes on 401; the webapp ensures a fresh token before
each reconnect and, on a 401, refreshes once then retries, dropping to anonymous
via a full clear-then-refill resync if the refresh is dead.

### The SSE endpoint

Catch-up emits batch frames chunked so no single `data:` line exceeds 200 KB. The
browser's EventSource has no per-line cap, but the Discord bot's aiohttp
StreamReader rejects lines over 512 KB. An object larger than the budget is emitted
alone, never split across lines.

After catch-up, a **personal overlay** sends `full`-level data for the viewer's own
objects and their role-based full-access objects. The stream then enters the live
phase, relaying single-object events:

```
data: {"type":"tournament","data":{...},"ts":"2026-06-03T12:00:00.123456"}
```

Note the envelope differences from catch-up batches: singular `type`, a single
`data` object rather than an array, and a `ts` field.

**Tournament-scoped stream** — `/stream?tournament=<uid>`, used by the Discord bot.
Catch-up delivers only that tournament, its sanctions and its participant
identities; the live phase filters to the same set plus its judge calls. Access
rules are unchanged — `entitled_level()` applies per object, just restricted to one
tournament's scope. The bot opens one scoped stream per watched tournament rather
than streaming the whole corpus.

Scoped streams carry no access-version handshake **by design**: they replay full
(small) state on every connect so they are never stale, and they receive no decks,
so the private-deck leak the fingerprint guards against cannot occur. Entitlement
shifts reach the bot through the live re-evaluation and the next full replay. Only
a move to *incremental* scoped catch-up would warrant revisiting this.

*Participant identities* — the bot has no User store but needs seated players'
names, and the scope filter drops generic user broadcasts. So the scoped stream
emits the **`member`-level** User (name, nickname, no contact — deliberately not
`entitled_level`, so contacts never leak into the Discord process) for every player
and organizer alongside the tournament. Catch-up seeds them; live, a tournament
delivery flags a refresh and the loop pushes any not-yet-sent identities, so late
registrants still resolve.

**Frame ordering trap**: on the live path the tournament frame precedes the
participant User frames, so reconcile logic using the name cache for a
just-added organizer or player is one message stale. Catch-up is safe.

### Broadcast and backpressure

One `broadcast_precomputed()` handles all object types. `BroadcastData` carries
`tournament_uid` — the tournament a sanction or deck belongs to — so scoped
connections can be routed without re-reading the DB. It is **not** auto-populated
for decks, which have no `organizers_uids` field; the deck-ops processor stamps
`org_uids` manually after save, and that is the correct pattern.

Each connection has a bounded `CoalescingQueue` (maxsize 30) keeping only the
**latest frame per `(type, uid)`**, so successive whole-object snapshots of one
tournament supersede each other and a stalled client accumulates ~1 object instead
of ~30 stale copies. Ephemeral events carry no key and are never coalesced.

On `QueueFull` the connection is marked closed and evicted from the broadcast set;
the generator sees the flag, **ends the stream**, and the browser's `EventSource`
auto-reconnects with `?since=<cursor>` and catches up. This is deliberate: a
dropped event must not leave a client OPEN on a queue that no longer receives
broadcasts, silently deaf. Lossless catch-up depends on the cursor being accurate.

### Ephemeral events

Broadcast directly to specific connections, with no DB storage and no IndexedDB
write.

| Event | Target | Purpose |
|---|---|---|
| `judge_call` | organizers + IC | a player requests a judge at their table |

Payload `{tournament_uid, table, table_label, player_name}`. The frontend
accumulates calls in component state, auto-dismisses after 120s and plays a chime.

## The sync cursor

The client reconnects with `?since=<cursor>` and the server filters
`modified_at > since`. The cursor is a high-water mark over the **`modified_at`
column** — DB clock, naive `TIMESTAMP`, set by a `BEFORE` trigger.

**Two timestamps, do not confuse them:**

| Field | Source | Format | Use |
|---|---|---|---|
| `modified` (in payload) | app clock, set in Python pre-write | `…123456Z`, tz-aware | display and audit only |
| `modified_at` (column) | DB clock, `BEFORE` trigger | `…123456`, naive | **authoritative sync ordering** |

Live payloads carry only `modified`, so the authoritative `modified_at` is
surfaced separately as the envelope `ts`. The frontend advances its cursor from
`ts`, never from `item.modified` — the app-clock value would skip events under any
clock skew and break string-comparison ordering, since `"…Z" > "…"` is lexically
true.

The snapshot meta **also** carries `generated_at`, the DB-clock instant the
snapshot was generated, distinct from `timestamp`. The client echoes it back. It is
**not** a data cursor and never filters `modified_at`; it is a *freshness* signal.
The server's resync guards key off `max(since, generated_at)` so they measure how
long the client has actually been away rather than when the data last changed —
without it, a system with no writes for over three days yields a `since` older than
the stale guard and every client loops on a forced resync.

The client-side cursor advances on **both** `sync_complete` **and every applied
live event**, with a monotonic guard. Advancing only on `sync_complete` left the
catch-up window growing unbounded across a long live session, eventually tripping
the server's three-day stale-`since` guard. Catch-up batches carry no `ts`; they
are buffered and the cursor moves when their `sync_complete` arrives.

## Resync

Triggered when a viewer's data level changes: the delta carries only content
changes, so an object whose *visibility* changed without its content changing
cannot reach the client any other way.

### Access-version fingerprint (primary, connect-time)

The connect handshake asks the precise question — *is the client based on the
entitlements it currently has?* — rather than comparing timestamps.
`compute_access_version(viewer)` hashes everything determining **which** objects
and which projection a viewer is entitled to:

```
fp = hash( DATA_SCHEMA_VERSION,          # global wire-shape lever
           base_level,                   # full | member | public
           sorted({IC,NC} ∩ roles),      # overlay-granting roles only
           country if NC else None,      # scopes the NC overlay
           sorted(organizer_tournament_uids) )   # member-only
```

- **Backend-only and opaque.** The client stores and echoes it, never computes or
  parses it, so the input set stays server-evolvable with zero client
  coordination, and a lying client can only over- or under-resync *itself*.
- **Self-maintaining.** Derived from current truth at connect — no write paths to
  enumerate, no silent-missed-bump leak. The organizer set is the only DB input,
  riding the GIN index on `("full"->'organizers_uids')`, and only members pay for
  the query: IC sees full everywhere, and public/anonymous viewers have no overlay.
- **`DATA_SCHEMA_VERSION`** is the one global lever. Bump it on a wire-shape change
  that does not also bump the frontend `DB_VERSION` — a model field rename or
  removal, a projection-policy change. One bump flips every client's fingerprint
  into exactly one resync. A change that *does* ride a `DB_VERSION` bump self-heals
  client-side and needs no lever.

Transport: `/snapshot` returns the fingerprint in an `X-Access-Version` **response
header**, computed per request from the resolved viewer — it cannot live in the
snapshot body, which is one shared per-level file while the fingerprint is
per-user. The client reads the header before opening `/stream`, so the first
connect echoes a matching `av` and doesn't spuriously resync. It persists the
fingerprint in IndexedDB and sends it as `/stream?av=<fp>`, since EventSource
cannot set headers. The server recomputes and compares; absent or different means
resync. A targeted push frame carries the new `av`, so the client can update
without reconnecting.

**On mismatch** the server emits `{"type": "resync"}` and **returns immediately**.
The browser clears IndexedDB and re-fetches the snapshot at its current level, so
streaming the corpus after the resync line is wasted work that also discards a
pooled connection on the client's mid-fetch teardown.

**Staleness guard** — orthogonal to entitlement, so the fingerprint cannot replace
it. The three-day freshness guard over `max(since, generated_at)` catches a client
away long enough that a soft-deleted object may have been hard-purged by the 30-day
job, so the since-delta would miss the deletion.

**Resync backoff** — the first resync reconnects immediately, but consecutive
resyncs with no intervening `sync_complete` route through exponential backoff, so a
persistent cause cannot spin a full-speed clear-and-reconnect loop. The streak
resets on `sync_complete`, which makes it a **load-bearing invariant that the
server always closes a catch-up stream with `sync_complete`**, even for an empty
delta — otherwise a healthy client accrues a false streak and self-throttles.

### Targeted overlay invalidation (no resync)

`broadcast_personal(...)` pushes **one object to one user** at that user's
*currently* entitled projection — the per-user counterpart to the shared per-level
frame. It re-derives `entitled_level` for the object now, so an entitlement
transition is delivered as a single update:

- **promote** → push the object at full;
- **demote, lower projection non-null** → push the lower projection, and the
  overwrite drops the full-only fields;
- **demote, lower projection null** — a private deck at member level — → push a
  **tombstone** so the client evicts just that object. This is the leak fix: the
  member projection of a private deck is null, so the since-catch-up could neither
  re-send nor evict it.

Every targeted frame carries the recomputed access version. Organizer add/remove
uses this: the new organizer gets the tournament and its private decks at full, and
the removed organizer gets the tournament downgraded plus a tombstone per private
deck — no full resync. An **offline** organizer change is still caught by the
fingerprint's organizer-set term at the next connect, which is why the resync
remains the offline fallback.

**Triggers** — VEKN operations that gain or lose a `vekn_id`; organizer add/remove;
gaining or losing an **overlay-granting** role (`NC`/`IC` — the closed set the level
functions branch on; any other role change moves no projection *the viewer can
see*, so it does not move the fingerprint, though a Prince's own projection change
reaches other viewers as an ordinary object update); and a `DATA_SCHEMA_VERSION`
bump.

## Snapshots

On first connect, with no `since`, the frontend fetches a pre-computed gzip
snapshot instead of streaming from scratch. Snapshots regenerate every 15 minutes,
one file per level, avoiding a DB connection held open for an initial stream of
thousands of objects. `/snapshot` streams the gzip from disk in chunks, holding one
fd open per response so the atomic-rename regeneration stays consistent mid-stream;
the file is never read into the heap, so hundreds of concurrent reconnects don't
spike memory.

**All three files come from ONE pass** over `objects`, selecting the three
projection columns of each row together and writing three gzip streams as it goes,
pinned to one relaxed-`statement_timeout` session. The previous per-(type, level)
shape issued `len(ObjectType) × 3` queries whose big-type plans each scanned the
whole heap. Mutual consistency is free: a DECLAREd cursor holds one MVCC snapshot
for its whole lifetime even under READ COMMITTED, so REPEATABLE READ isn't needed.
A row is simply omitted from a file whose projection column is NULL.

### File format (`version: 2`)

Gzip **JSONL** — one JSON object per line, no enclosing array, no grouping by type:

```
{"type":"header","version":2,"timestamp":"…","generated_at":"…"}
{"type":"user","data":{…}}
{"type":"eof","count":30216}
```

Line-delimited so the client ingests it as a stream — response body →
`DecompressionStream` → `TextDecoderStream` → split → parse one line → buffer →
save batch → drop — holding one batch rather than the compressed bytes *plus* the
decompressed text *plus* the parsed object graph. Type grouping is what a one-pass
unordered read gives up, so each line self-describes; object lines are built by
string concatenation around the raw `{level}::text` column, so no row is
deserialized server-side.

`version` is checked against the client's constant and a mismatch refuses the file
outright. The **`eof` trailer is load-bearing**: ingest writes rows as it reads, so
a truncated file can no longer be caught by "did the parse succeed". The client
sets an in-progress marker *before* clearing the stores and removes it only when
`eof` lands with a matching count; a marker surviving into the next boot means the
stores hold a partial snapshot — which otherwise looks perfectly valid — and the
client clears and refetches.

**Both meta fields carry the same value: the DB-clock instant generation started**,
read before any row. This is a correctness requirement, not a simplification. The
cursor takes its MVCC snapshot at some instant *after* that one, so a max over the
rows actually read can exceed the `modified_at` of a row the file missed; that row
then falls below the client's `since` and is never delivered, with no way for the
client to notice — and for a tombstone, the 30-day purge eventually makes the ghost
unrepairable. Anchoring the cursor before the read makes any such row either
present in the file or strictly after the cursor. The cost is that the first
catch-up re-delivers rows modified during generation, which is exactly what
catch-up is for. Residual, inherent to any timestamp cursor: `modified_at` is
transaction-*start* time, so a write straddling the anchor can commit after it with
an earlier stamp; the window is one short write transaction.

### Data export

`GET /snapshot?download=1` serves the same content re-enveloped as a single-entry
`.zip` attachment holding the same-named `.jsonl`, with no `Content-Encoding` so
the browser writes the archive to disk rather than inflating it. Zip over the
stored `.gz` because Windows opens it natively; the generator inflates and
re-deflates through `zipfile` into a non-seekable sink drained every 64 KB, so the
heap stays bounded and the archive streams. IC gets a download button behind a
confirm modal warning that the file carries member PII.

It is an *export*, not a backup: up to 15 minutes stale, no soft-deleted
tombstones, no static card data. `pg_dump` remains the backup tool.

## Frontend storage

One `tournaments` store holds all data levels — there is no separate details store.
A DB-version upgrade deletes all stores and recreates them fresh, triggering a full
resync. **Exception**: unsynced offline-tournament data — the offline tournament
row, its temp player stubs, offline sanctions and decks, and the `offline_*`
metadata — is rescued within the upgrade transaction and written back, since it
isn't re-fetchable from SSE. Both the upgrade path and the sync manager's
clear-all-stores path wipe the stores, and **both must rescue the full offline
set**.

Minimal indexes only:

| Store | Indexes |
|---|---|
| users | `by-name`, `by-country-name` |
| sanctions | `by-user`, `by-tournament` |
| tournaments | `by-state`, `by-start`, `by-country`, `by-format` |
| decks | `by-tournament`, `by-user` |
| leagues | `by-country`, `by-start` |
| promos | none — small catalog |

A generic `ObjectSpec` array (`SPECS`) handles all types uniformly in the sync
manager, and a single `isSynced` flag tracks state.

**Universal soft-delete**: on a tombstone the client **hard-deletes** the row from
its store, otherwise it saves. No type is exempt, **users included** — every
deletable member is VEKN-less, and tournament participation requires a `vekn_id`,
so a deleted user is never a live player reference. Server-side `deleted_at` is
only a retention window so the deletion can be streamed to catch-up clients;
persisting tombstones client-side buys nothing. Legacy pre-VEKN imported events may
then render a raw uid for a deleted nameless player — cosmetic, accepted.

## Offline lifecycle

The device-lock model itself is [architecture](architecture.md#online-and-offline).
The sync-side mechanics:

**Lock-loss reconciliation** — the three offline-skip filters (snapshot batch, live
SSE, flush buffer) check for lock loss before dropping a tournament update. A
tournament is lock-lost when the local device holds it offline but the
authoritative copy shows `offline_mode === false` or a different
`offline_device_id`, meaning a force-unlock or takeover already happened
server-side. The handler then clears local offline state, warns about data loss,
and falls through to apply the authoritative copy — so a previously isolated device
gets the memo on reconnect.

**Self-echo suppression on go-online** — when a device brings *its own* tournament
online, the resulting `offline_mode=false` broadcast would echo back and trip the
lock-loss path before the HTTP response clears local state. Two layers prevent it:
the server self-excludes the initiating device from the tournament broadcast by
matching the `device_id` query parameter, while still delivering the resolved
users, decks, sanctions and ratings frames; and while go-online is in flight the
client short-circuits lock-loss detection for that uid, so **the HTTP response is
the sole authority** on the outcome during that window and a concurrent
force-unlock is reported once, through the status codes below, not twice.

**Server-managed field re-pull** — before saving the device's offline snapshot, the
server re-stamps a fixed set of fields from the authoritative locked row:
`banner_path`, `external_ids`, `checkin_code`, `vekn_pushed_at`,
`vekn_results_stale`. These are never written by the WASM engine and can change
server-side during the offline window — VEKN sync writes `external_ids` and
`vekn_pushed_at`, a re-uploaded banner writes `banner_path`, another organizer's SA
or DQ can flip `vekn_results_stale`. Trusting the device's stale values would
revert them. "Server wins" for non-engine fields, same as `organizers_uids`. **Any
new backend-only Tournament field must join this list**, or an offline round-trip
silently reverts it; the online action path is safe because the engine preserves
unknown JSON keys.

**Atomicity** — the tournament snapshot, offline sanctions and offline decks all
persist inside the SAME locked transaction, with broadcasts fired post-commit. A
connection drop mid-push therefore leaves the server row still offline and the whole
push retryable, never a committed online row with the offline objects silently
lost. The response carries the recomputed authoritative row plus a summary — players
matched, accounts created, decks synced — which the client surfaces as a toast.

**Status guards** — `go-online` returns **410 Gone** if the server is no longer in
offline mode, or **409 Conflict** if another device force-took the lock. The client
catches both, clears orphaned local offline state and raises the lock-lost warning.
This stops a stale device blind-overwriting authoritative state with its snapshot,
and stops a 409 wedging the device offline. Reclaiming after a 409 is a deliberate
separate force-takeover, never a silent clobber from this path.

An offline deck **deletion** travels in the same payload as a soft-delete tombstone
row, because the payload is upsert-only and a locally hard-deleted deck would
otherwise resurrect.

## Tournament-embedded, online-only fields

Some tournament fields are not processed by the engine and have no offline path.
They live on the `Tournament` struct, sync via normal CRUD-on-save, and reach
members automatically because the member projection is a denylist.

| Field | What |
|---|---|
| `timer`, `table_extra_time` | round timer state; clients compute the countdown locally |
| `announcements` | organizer broadcasts, capped to the last 20 at 280 chars each |

**Do not add a new synced object type for data that belongs to a single
tournament, is online-only and needs no engine processing** — embed it in
`Tournament` instead. The pattern is: field on Tournament, backend route inside
`tournament_transaction` → save → broadcast, no Rust engine, no optimistic update,
no new type.

## Non-synced side tables

Not all persistent server state flows through the projection pipeline.

| Side table | Why it stays off |
|---|---|
| `avatars`, `banners` | binary blobs, served directly with a path string on the object |
| `promo_images` | same, but served unauthenticated and cached cache-first by the service worker for offline raffle display |
| `push_subscriptions` | send credentials — routing them through the pipeline would broadcast per-device push endpoints to every client |
| `oauth_*` | OAuth state and token management |
| `promo_ledger` | append-mostly inventory audit trail, officials-only, online-only back office |

When adding state: display data keyed by uid that every authorized client needs
goes on the `objects` path; server-side-only credentials and blobs go in a side
table.

## Online-only REST reads

"All UI reads come from IndexedDB" has exactly one sanctioned exception: the promo
ledger audit view reads `GET /api/promos/ledger` directly. A surface qualifies only
when **all four** hold:

1. **Online-only** — never needed at a venue or during an offline tournament.
2. **Officials-only** — not player- or tournament-facing display.
3. **Back-office** — administrative bookkeeping, not gameplay or event flow.
4. **Small role-scoped dataset shipped whole** — one response, no server-side
   pagination; filtering and aggregation happen client-side.

A tournament- or player-facing view meets none of these. Do not cite this carve-out
to bypass offline-first for display data.

Authoritative aggregates derived from carve-out data are **not** part of the
carve-out: remaining promo stock is server-computed and streamed through the normal
objects pipeline, because a total derived client-side diverges with local sync
state.

## Adding a new object type

1. **Backend model** in `models.py`, extending `BaseObject`.
2. **Projections** in `access_levels.py`: `compute_<type>_public/member/full()`
   plus the dispatch dicts.
3. **CRUD wrappers** in `db.py` — thin wrappers over `save_object_from_model` and
   `get_object_full`; populate `BroadcastData.tournament_uid` if the type belongs
   to a tournament, needed for scoped connections.
4. **Entitlement** in `entitled_level()` — add a branch only for non-standard
   visibility, and mirror it in the overlay frames if it is a non-country,
   non-own-object full grant.
5. **Broadcast** after mutations. No registration step: the stream types derive
   from `list(ObjectType)` and snapshot generation reads whatever the single corpus
   scan returns, so both pick up the new type automatically.
6. **Frontend type** in `types.ts`.
7. **IndexedDB store** in `db.ts` — bump the version, which triggers a full clear.
8. **Add to `SPECS`** in `sync.ts`.

A backend-first deploy is safe: a snapshot line whose type isn't in `SPECS` yet is
counted toward the `eof` total and then ignored, so an older bundle still
bootstraps. **Do not "fix" that by counting only recognised types** — that turns
every unknown type into a phantom truncation and bricks the bootstrap for every
client that hasn't updated.
