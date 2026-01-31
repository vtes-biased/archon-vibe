# Sync Architecture

SSE streaming sync: PostgreSQL → FastAPI → SSE → Browser → IndexedDB.

## Data Levels

Three access levels determine what data each SSE viewer receives:

| Level | Viewer | Description |
|-------|--------|-------------|
| `public` | No token or no vekn_id | Only Prince/NC users (with contact info), minimal tournaments, no sanctions |
| `member` | Has vekn_id | All users (no contact info), all sanctions, tournaments with standings/my_tables/filtered decks |
| `full` | IC, NC/Prince (same country), organizer | Everything including rounds, finals, checkin_code |

## Backend Streaming

### Generic `stream_objects()`

Single generic function replaces per-type duplicates:

```python
# backend/src/db.py
async def stream_objects[T](
    table: str, type_: type[T], since: str | None = None, batch_size: int = 1000
) -> AsyncIterator[tuple[list[T], str | None]]:
```

Uses server-side cursors with `WHERE modified > %s` (strict `>`, not `>=`) to avoid duplicates on incremental sync.

### Per-Type Filtering

Each object type has a filter function applied per-viewer during both initial sync and real-time broadcast:

- `_filter_user()` — strips contact info for members, skips non-Prince/NC users for public
- `_filter_sanction()` — members+ only
- `_filter_tournament()` — full/member/minimal based on access level, `standings_mode`, `decklists_mode`
- `_filter_rating()` — public (no filtering)

### SSE Endpoint (spec-based loop)

```python
_stream_specs = [
    (stream_users, "users", _filter_user),
    (stream_sanctions, "sanctions", _filter_sanction),
    (stream_tournaments, "tournaments", _filter_tournament),
    (stream_ratings, "ratings", _filter_rating),
]

for stream_fn, event_type, filter_fn in _stream_specs:
    async for batch, batch_max in stream_fn(since=effective_since):
        filtered = [filter_fn(item, viewer) for item in batch if filter_fn(item, viewer) is not None]
        yield SSE(type=event_type, data=filtered)
```

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

### Generic Broadcast

Single `_broadcast()` function with per-viewer filtering replaces 4 separate broadcast functions.

## Frontend: IndexedDB

### Single Tournament Store

One `tournaments` store holds all data levels. No separate `tournament_details` store.
Version 11 upgrade: deletes all stores and recreates fresh → triggers full resync.

### Index Strategy

Minimal indexes only:

| Store | Indexes |
|-------|---------|
| users | `by-name`, `by-country-name` |
| sanctions | `by-user` |
| tournaments | `by-state`, `by-start`, `by-country`, `by-format` |
| ratings | `by-user`, `by-country` |

### Changes Log (Offline-Ready)

Generalized for all object types:

```typescript
changes: {
  store: string;        // "users" | "sanctions" | "tournaments" | "ratings"
  type: 'create' | 'update' | 'delete';
  uid: string;
  timestamp: string;
  event?: unknown;      // tournament action payload
  data?: unknown;       // object snapshot
}
```

Entries cleared when SSE confirms the update (matching uid).

## Frontend: Sync Manager

### Spec-Based Buffers

Generic `ObjectSpec` array handles all types uniformly:

```typescript
const SPECS = [
  { batchType: 'users', singleType: 'user', save, saveBatch, del },
  { batchType: 'sanctions', singleType: 'sanction', save, saveBatch, del },
  { batchType: 'tournaments', singleType: 'tournament', save, saveBatch, del },
  { batchType: 'ratings', singleType: 'rating', save, saveBatch, del },
];
```

### Universal Soft-Delete

All objects have `deleted_at`. If `item.deleted_at` → delete from store, else → save.

### Sync State

Single `isSynced` flag (no separate `isInitialSync`).

## Optimistic Updates

### Tournament Actions (WASM Engine)

1. Load current tournament from IndexedDB
2. Process via WASM `processTournamentEvent()` → save to IndexedDB → UI reacts
3. Send to backend async
4. SSE delivers authoritative state → overwrites IndexedDB

```typescript
export async function tournamentAction(uid, action, data) {
  const current = await getTournament(uid);
  const updated = await processTournamentEvent(current, event, actor);
  await saveTournament(updated);
  await logChange('tournaments', 'update', uid, { event });
  apiRequest(...).catch(() => { /* SSE will correct */ });
  return updated;
}
```

### Non-Tournament Mutations

Apply to IndexedDB optimistically → send to server → SSE corrects if needed.

## Tournament Field Visibility (Member Level)

| Field | Finished | Ongoing (player) | Ongoing (non-player) |
|-------|----------|-------------------|----------------------|
| Config fields | ✓ | ✓ | ✓ |
| organizers_uids | ✓ | ✓ | ✓ |
| players | ✓ (full) | ✓ (no per-player results) | ✓ (no per-player results) |
| standings | ✓ | Per `standings_mode` | Per `standings_mode` |
| decks | Per `decklists_mode` | ✗ | ✗ |
| finals | ✓ | ✗ | ✗ |
| my_tables | ✓ | ✓ | N/A |
| rounds | ✗ | ✗ | ✗ |

`decklists_mode`: Winner → winner's deck only, Finalists → finalist decks, All → all decks.

`standings_mode` (ongoing only): Private → empty, Cutoff/Top 10/Public → full standings (frontend applies display rules).

## Adding a New Object Type

1. **Backend model** in `models.py` (extend `BaseObject` for `deleted_at`)
2. **DB table** + thin wrapper: `stream_<type>()` using `stream_objects()`
3. **Filter function** in `main.py`: `_filter_<type>(obj, viewer) -> obj | None`
4. **Add to `_stream_specs`** in SSE endpoint
5. **Broadcast function** using `_broadcast()`
6. **Frontend type** in `types.ts`
7. **IndexedDB store** in `db.ts` (bump version → full clear)
8. **Add to `SPECS`** in `sync.ts`
