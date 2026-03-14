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
| user | NC/Prince only (with contact) | all users (no contact) | everything except `calendar_token` |
| tournament | minimal fields | all except `checkin_code`, `vekn_pushed_at` | everything |
| sanction | `None` | full data | full data |
| deck | `None` | full data if `public=true`, else `None` | full data |
| league | full data | full data | full data |

`None` means column is NULL in DB — object invisible at that level.

### SSE Endpoint

```python
_STREAM_TYPES = ["user", "tournament", "sanction", "deck", "league"]

for obj_type in _STREAM_TYPES:
    async for json_strings, batch_max in stream_objects_new(
        obj_type=obj_type, level=level.value, since=effective_since
    ):
        joined = ",".join(json_strings)
        yield f'data: {{"type":"{obj_type}s","data":[{joined}]}}\n\n'
```

No per-viewer filtering at read time — projections are pre-computed. After the catch-up phase, a **personal overlay** sends `full`-level data for the viewer's own objects and role-based full-access objects (NC/Prince same country, organizers).

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

### Generic Broadcast

Single `broadcast_precomputed()` function (in `broadcast.py`) with per-viewer filtering handles all object types.

### Snapshot-Based Initial Sync

On first connect (no `since` timestamp), the frontend fetches a pre-computed gzip snapshot (`GET /snapshot`) instead of streaming from scratch. Snapshots are regenerated every 15 minutes by a background task (`snapshots.py`), one per access level (public/member/full). This avoids holding a DB connection open for the full initial stream of potentially thousands of objects.

After the snapshot loads, the SSE stream picks up from the snapshot's timestamp, delivering any changes that occurred since generation.

## Frontend: IndexedDB

### Single Tournament Store

One `tournaments` store holds all data levels. No separate `tournament_details` store.
Version 11 upgrade: deletes all stores and recreates fresh → triggers full resync.

### Index Strategy

Minimal indexes only:

| Store | Indexes |
|-------|---------|
| users | `by-name`, `by-country-name` |
| sanctions | `by-user`, `by-tournament` |
| tournaments | `by-state`, `by-start`, `by-country`, `by-format` |
| decks | `by-tournament`, `by-user` |
| leagues | `by-country`, `by-start` |

### Changes Log (Offline-Ready)

Generalized for all object types:

```typescript
changes: {
  store: string;        // "users" | "sanctions" | "tournaments" | "decks" | "ratings" | "leagues"
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
  { batchType: 'decks', singleType: 'deck', save, saveBatch, del },
  { batchType: 'leagues', singleType: 'league', save, saveBatch, del },
];
```

### Universal Soft-Delete

All objects have `deleted_at`. If `item.deleted_at` → delete from store, else → save.

### Sync State

Single `isSynced` flag (no separate `isInitialSync`).

## Optimistic Updates

### Tournament Actions (WASM Engine)

1. Load current tournament + decks from IndexedDB
2. Process via WASM `processTournamentEvent()` → returns `{tournament, deck_ops}` → save both to IndexedDB → UI reacts
3. Send to backend async
4. SSE delivers authoritative state (tournament + deck objects) → overwrites IndexedDB

```typescript
export async function tournamentAction(uid, action, data) {
  const current = await getTournament(uid);
  const result = await processTournamentEvent(current, event, actor, sanctions, decks);
  // result: { tournament, deck_ops }
  await saveTournament(result.tournament);
  // apply deck_ops to IndexedDB
  await logChange('tournaments', 'update', uid, { event });
  apiRequest(...).catch(() => { /* SSE will correct */ });
  return result.tournament;
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
| finals | ✓ | ✗ | ✗ |
| rounds | ✗ | ✗ | ✗ |

`decklists_mode`: Winner → winner's deck only, Finalists → finalist decks, All → all decks.

`standings_mode` (ongoing only): Private → empty, Cutoff/Top 10/Public → full standings (frontend applies display rules).

## Adding a New Object Type

1. **Backend model** in `models.py` (extend `BaseObject`)
2. **Projection functions** in `access_levels.py`: `compute_<type>_public/member/full()` + add to dispatch dicts
3. **CRUD wrappers** in `db.py`: thin wrappers calling `save_object_from_model("<type>", obj)` and `get_object_full(uid, Type)`
4. **Add to `_STREAM_TYPES`** in `main.py` (SSE catch-up loop)
5. **Add to `OBJECT_TYPES`** in `snapshots.py`
6. **Broadcast** via `broadcast_precomputed()` (from `broadcast.py`) after mutations
7. **Frontend type** in `types.ts`
8. **IndexedDB store** in `db.ts` (bump version → full clear)
9. **Add to `SPECS`** in `sync.ts`
