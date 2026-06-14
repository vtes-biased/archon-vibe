# Sync Architecture

SSE streaming sync: PostgreSQL → FastAPI → SSE → Browser → IndexedDB.

## Data Levels

Three access levels determine what data each SSE viewer receives:

| Level | Viewer | Description |
|-------|--------|-------------|
| `public` | No token or no vekn_id | Only Prince/NC users (with contact info), minimal tournaments, no sanctions |
| `member` | Has vekn_id | All users (no contact info), all sanctions, tournaments with standings/filtered decks |
| `full` | IC, NC/Prince (same country), organizer | Everything including rounds, finals, checkin_code |

## Backend Streaming

### Unified `stream_objects_new()`

Single generic function reading pre-computed access-level columns:

```python
# backend/src/db.py
async def stream_objects_new(
    obj_type: str | None = None,
    level: str = "full",          # "public" | "member" | "full"
    since: str | None = None,
    batch_size: int = 1000,
) -> AsyncIterator[tuple[list[str], str]]:
    # Yields (batch_of_raw_json_strings, max_modified_at)
```

**Keyset pagination**: Uses `WHERE (modified_at, uid) > (%s, %s)`. DB connections acquired/released per batch. Yields raw JSONB text strings — no Python deserialization.

### Access-Level Projections (computed at write time)

`backend/src/access_levels.py` computes three projections per object at **write time**:

| Type | `public` | `member` | `full` |
|------|----------|----------|--------|
| user | NC/Prince only (with contact + community_links); IC only (community_links, no contact) | all users (no contact, no `deceased_by_uid`); `deceased_at` included; any user with non-empty community_links gets community_links included | everything except `calendar_token` |
| tournament | minimal fields | all except `checkin_code`, `vekn_pushed_at` | everything |
| sanction | `None` | full data | full data |
| deck | `None` | full data if `public=true`, else `None` | full data |
| league | full data | full data | full data |

`None` means column is NULL in DB — object invisible at that level.

### Credential Transport

`/stream` and `/snapshot` accept credentials via two transports, resolved by `_resolve_viewer()`:

| Caller | Transport | Mechanism |
|--------|-----------|-----------|
| Browser (`EventSource`) | `token=` query param | Native `EventSource` cannot set headers; resolved via `_resolve_user_from_token` (JWT decode + DB lookup) |
| Discord bot | `Authorization: Bearer <token>` header | Resolved via `get_current_user` (revocation-aware, handles `oauth_access` tokens + `user:impersonate` scope) |

**Invalid credential → 401** (not silent downgrade): a supplied-but-invalid/expired/revoked credential raises HTTP 401 regardless of transport. Only a wholly absent credential yields anonymous → `public`. Clients react: the bot proactively checks expiry (`_access_token_expired`) before connecting and refreshes on 401; the webapp calls `ensureSyncToken()` before each (re)connect and on a 401 refreshes once then retries; a dead refresh drops to anonymous via a full clear-then-refill resync.

### SSE Endpoint

```python
_STREAM_TYPES = list(ObjectType)      # catch-up object order
_SSE_LINE_BUDGET = 200_000            # bytes per `data:` line
```

Catch-up emits batch frames via `_sse_object_lines()`, which chunks each object-type batch so no single `data:` line exceeds `_SSE_LINE_BUDGET` (200 KB). Reason: the browser EventSource has no per-line cap, but the Discord bot's aiohttp StreamReader rejects lines over 512 KB. A single object larger than the budget is emitted alone (never split across lines).

No per-viewer filtering at read time — projections are pre-computed. After the catch-up phase, a **personal overlay** sends `full`-level data for the viewer's own objects and role-based full-access objects (NC/Prince same country, organizers).

**Tournament-scoped stream** — `/stream?tournament=<uid>` opens a scoped connection (used by the Discord bot). The catch-up delivers only that tournament + its sanctions (`_scoped_catchup_frames`); the live phase filters to that tournament's object, its sanctions, and its judge calls via `SSEConnection.tournament_uid` + `_scope_matches`. Access rules are unchanged — `entitled_level()` (see below) applies per object, just restricted to one tournament's scope. The bot opens one scoped stream per watched tournament instead of streaming the whole corpus.

The stream then enters the **live phase**, relaying single-object events from `broadcast_precomputed()`:

```
data: {"type":"tournament","data":{...},"ts":"2026-06-03T12:00:00.123456"}
```

Note the envelope differences from the catch-up batches: singular `type` (`tournament` not `tournaments`), a single `data` object (not an array), and a `ts` field. See **Sync Cursor** below for what `ts` is and why it must not be confused with the payload's own `modified`.

### Sync Cursor (`since`)

The client reconnects with `?since=<cursor>`; the server filters `modified_at > since` (`stream_objects_new`) and re-streams everything newer. The cursor is therefore a high-water mark over the **`modified_at` column** (DB clock, naive `TIMESTAMP`, set by a `BEFORE` trigger), which is also what `sync_complete.timestamp` and the snapshot `meta.timestamp` report.

**Two timestamps, do not confuse them:**

| Field | Source | Format | Use |
|-------|--------|--------|-----|
| `modified` (in payload) | app clock, set in Python pre-write | `…123456Z` (tz-aware) | display/audit only |
| `modified_at` (column) | DB clock, `BEFORE` trigger | `…123456` (naive) | **authoritative sync ordering** |

Because live event payloads only carry `modified`, the authoritative `modified_at` is surfaced separately as the envelope `ts` field (plumbed `save_object … RETURNING modified_at` → `BroadcastData.modified_at` → `broadcast_precomputed`). The frontend advances its cursor from `ts`, never from `item.modified` — using the app-clock payload value would skip events under any clock skew and break string-comparison ordering (`"…Z" > "…"` is lexically true).

### Ephemeral SSE Events

Not all SSE events are CRUD events. Ephemeral events are broadcast directly to specific connections without DB storage or IndexedDB writes.

| Event type | Target | Stored | IndexedDB | Purpose |
|------------|--------|--------|-----------|---------|
| `judge_call` | organizers + IC | No | No | Player calls for judge at table |

`judge_call` payload:
```json
{ "tournament_uid": "...", "table": 2, "table_label": "Table 3", "player_name": "..." }
```

Frontend handles in `JudgeCallBanner.svelte` — accumulates calls in component state, auto-dismisses after 120s, plays audio chime.

### Resync Mechanism

Triggered when a viewer's data level changes (role or vekn_id change).

**Backend**:
- `resync_after` field on User, set via `set_user_resync_after()` (uses DB `now()`)
- `MINIMUM_SYNC_EPOCH` constant bumped on releases requiring global resync
- On SSE connect: if `since` is stale (threshold > since), send `{"type": "resync"}` + full stream

**Frontend**:
- On `resync` event: clear all IndexedDB stores + sync timestamp
- Full data follows automatically

**Triggers**:
- VEKN operations: `/claim`, `/sponsor`, `/link`, `/force-abandon`, `/abandon`
- User update: roles or vekn_id changed
- Release bump: `MINIMUM_SYNC_EPOCH` in main.py

### Access Entitlement

`entitled_level(viewer, *, obj_type, uid, country, org_uids, obj_user_uid) → "public"|"member"|"full"` in `broadcast.py` is the **single source of truth** for per-object access. It is called by both the live broadcast (`broadcast_precomputed`) and the tournament-scoped catch-up (`_scoped_catchup_frames`). Logic: IC → full; NC/Prince same country → full; explicit organizer → full; member with own profile/deck → full; any member → member; otherwise public.

### Generic Broadcast

Single `broadcast_precomputed()` function (in `broadcast.py`) with per-viewer filtering handles all object types. `BroadcastData` carries `tournament_uid` (the tournament a sanction/deck belongs to) so `_scope_matches` can route events to tournament-scoped connections without re-reading the DB.

Each connection has a bounded `asyncio.Queue` (maxsize 100). On `QueueFull` (a slow/stalled consumer), the connection is marked `closed` and evicted from the broadcast set; the SSE generator sees the flag, **ends the stream**, and the browser's `EventSource` auto-reconnects with `?since=<cursor>` and catches up. This is deliberate: a dropped event must not leave the client OPEN on a queue that no longer receives broadcasts (silently "deaf"). Lossless catch-up depends on the cursor being accurate — see **Sync Cursor** above.

### Snapshot-Based Initial Sync

On first connect (no `since` timestamp), the frontend fetches a pre-computed gzip snapshot (`GET /snapshot`) instead of streaming from scratch. Snapshots are regenerated every 15 minutes by a background task (`snapshots.py`), one per access level (public/member/full). This avoids holding a DB connection open for the full initial stream of potentially thousands of objects. The same `_resolve_viewer()` credential logic applies (see **Credential Transport** above).

After the snapshot loads, the SSE stream picks up from the snapshot's timestamp, delivering any changes that occurred since generation.

## Frontend: IndexedDB

### Single Tournament Store

One `tournaments` store holds all data levels. No separate `tournament_details` store.
A DB-version upgrade deletes all stores and recreates fresh → triggers full resync.
Exception: unsynced offline-tournament data (the offline tournament row, its temp
player stubs, offline sanctions/decks, and the `offline_*` metadata) is rescued
within the upgrade transaction and written back, since it isn't re-fetchable from SSE.

### Index Strategy

Minimal indexes only:

| Store | Indexes |
|-------|---------|
| users | `by-name`, `by-country-name` |
| sanctions | `by-user`, `by-tournament` |
| tournaments | `by-state`, `by-start`, `by-country`, `by-format` |
| decks | `by-tournament`, `by-user` |
| leagues | `by-country`, `by-start` |

### Offline Mode

Offline tournaments use a device-lock model (no changes log needed):
- Tournament locked to one device via `go-offline` endpoint
- WASM engine processes all actions locally, updating IndexedDB directly
- On `go-online`, full tournament state (including offline-created players, decks, sanctions) is sent to server
- Server overwrites its state with the primary device's authoritative data
- Temp UIDs (offline-created players) are remapped to real UIDs on sync

**Lock-loss reconciliation** — the three offline-skip filters in `sync.ts` (snapshot batch, live SSE, flush buffer) check `lostOfflineLock()` before dropping a tournament update. A tournament is "lock-lost" when the local device holds it offline but the authoritative copy shows `offline_mode===false` or `offline_device_id !== myDeviceId` (i.e. a force-unlock or force-takeover already happened on the server). When detected, `handleOfflineLockLost()` clears local offline state, toasts a data-loss warning, and falls through to apply the authoritative copy — so a previously isolated device "gets the memo" on reconnect.

**go-online 410 guard** — `POST .../go-online` returns **410 Gone** if the server is no longer in offline mode (already unlocked or already brought online by another path). The client catches 410, clears orphaned local offline state, and re-raises. This prevents a stale device from blind-overwriting the authoritative state with its snapshot; SSE delivers the current state instead.

## Frontend: Sync Manager

### Spec-Based Buffers

Generic `ObjectSpec` array handles all types uniformly:

```typescript
const SPECS = [
  { batchType: 'users', singleType: 'user', save, saveBatch, del },
  { batchType: 'sanctions', singleType: 'sanction', save, saveBatch, del },
  { batchType: 'tournaments', singleType: 'tournament', save, saveBatch, del },
  { batchType: 'decks', singleType: 'deck', save, saveBatch, del },
  { batchType: 'leagues', singleType: 'league', save, saveBatch, del },
];
```

### Universal Soft-Delete

All objects have `deleted_at`. If `item.deleted_at` → delete from store, else → save.

### Sync State

Single `isSynced` flag (no separate `isInitialSync`).

The cursor is a `lastTimestamp` high-water mark (mirrored to IndexedDB via `setLastSyncTimestamp`), seeded from the snapshot/last cursor on connect and advanced on **both** `sync_complete` **and every applied live event** (from the envelope `ts`, with a monotonic guard). Advancing only on `sync_complete` — the old behavior — left the catch-up window growing unbounded across a long live session, eventually tripping the server's 3-day stale-`since` full-resync guard. Catch-up batches don't carry `ts`; they're buffered and the cursor moves when their `sync_complete` arrives.

## Optimistic Updates

### Tournament Actions (WASM Engine)

1. Load current tournament + decks from IndexedDB (`current` = pre-action snapshot)
2. Process via WASM `processTournamentEvent()` → returns `{tournament, deck_ops}` → save both to IndexedDB → UI reacts
3. Send to backend async (serialized per tournament)
4. **On success:** SSE delivers authoritative state (tournament + deck objects) → overwrites IndexedDB
5. **On rejection:** roll back to the pre-action snapshot (see below)

```typescript
export async function tournamentAction(uid, action, data) {
  const current = await getTournament(uid);                  // pre-action state
  const result = await processTournamentEvent(current, event, actor, sanctions, decks);
  await saveTournament(result.tournament);                   // optimistic
  // apply deck_ops to IndexedDB
  enqueueServerAction(uid, async () => {
    try {
      await apiRequest(`/api/tournaments/${uid}/action`, ...);
    } catch (e) {
      // A rejected action emits NO SSE event and does not advance modified_at,
      // so the catch-up stream never re-delivers it — nothing self-corrects.
      // Server actions are transactional, so authoritative == pre-action state:
      // restore it locally (no GET — reads are offline-first from IndexedDB).
      await rollbackTournamentAction(uid, current, decks, hadDeckOps);
      // HTTP errors are toasted by apiRequest; toast network failures too.
    }
  });
  return result.tournament;
}
```

**Why rollback, not "SSE will correct":** a rejection produces no SSE event for that object, so deferring to the next sync would leave the bad optimistic state in IndexedDB indefinitely. Rollback also self-heals the one ambiguous case (network error *after* the server committed): there `modified_at` did advance, so the authoritative SSE — live or via the `since` catch-up — overwrites the rollback. This relies on **overwrite** apply semantics (`db.put` by uid, no field-merge); a merge would preserve the stale optimistic fields and never reconcile.

### Non-Tournament Mutations

Apply to IndexedDB optimistically → send to server → SSE corrects if needed. (These have no rollback path; a rejected mutation surfaces via the `apiRequest` error toast.)

## Tournament Field Visibility (Member Level)

| Field | Finished | Ongoing (player) | Ongoing (non-player) |
|-------|----------|-------------------|----------------------|
| Config fields | ✓ | ✓ | ✓ |
| organizers_uids | ✓ | ✓ | ✓ |
| players | ✓ (full) | ✓ (no per-player results) | ✓ (no per-player results) |
| standings | ✓ | Per `standings_mode` | Per `standings_mode` |
| finals | ✓ | ✗ | ✗ |
| rounds | ✓ | ✓ | ✓ |

`decklists_mode`: Winner → winner's deck only, Finalists → finalist decks, All → all decks.

`standings_mode` (ongoing only): Private → empty, Cutoff/Top 10/Public → full standings (frontend applies display rules).

## Adding a New Object Type

1. **Backend model** in `models.py` (extend `BaseObject`)
2. **Projection functions** in `access_levels.py`: `compute_<type>_public/member/full()` + add to dispatch dicts
3. **CRUD wrappers** in `db.py`: thin wrappers calling `save_object_from_model("<type>", obj)` and `get_object_full(uid, Type)`; populate `BroadcastData.tournament_uid` if the type belongs to a tournament (needed for tournament-scoped SSE connections)
4. **Access entitlement** in `broadcast.entitled_level()`: add a branch if the type has non-standard visibility rules (own object, country-scoped, etc.)
5. **Add to `_STREAM_TYPES`** in `main.py` (SSE catch-up loop)
6. **Add to `OBJECT_TYPES`** in `snapshots.py`
7. **Broadcast** via `broadcast_precomputed()` (from `broadcast.py`) after mutations
8. **Frontend type** in `types.ts`
9. **IndexedDB store** in `db.ts` (bump version → full clear)
10. **Add to `SPECS`** in `sync.ts`
