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
    exclude_deleted: bool = False, # snapshot path drops tombstones; SSE keeps them
) -> AsyncIterator[tuple[list[str], str]]:
    # Yields (batch_of_raw_json_strings, max_modified_at)
```

**Keyset pagination**: Uses `WHERE (modified_at, uid) > (%s, %s)` (tie-safe across batch seams), `ORDER BY modified_at, uid LIMIT batch_size`. A pooled connection is acquired then **released before each yield**, so a slow SSE client never pins a pool slot across its catch-up and app heap holds at most one batch — not the whole resultset. Yields raw JSONB text strings — no Python deserialization. Snapshot generation reuses it with `exclude_deleted=True`.

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

**Tournament-scoped stream** — `/stream?tournament=<uid>` opens a scoped connection (used by the Discord bot). The catch-up delivers only that tournament, its sanctions, and its **participant identities** (`_scoped_catchup_frames`); the live phase filters to that tournament's object, its sanctions, and its judge calls via `SSEConnection.tournament_uid` + `_scope_matches`. Access rules are unchanged — `entitled_level()` (see below) applies per object, just restricted to one tournament's scope. The bot opens one scoped stream per watched tournament instead of streaming the whole corpus.

*No access-version handshake (by design, not an omission)*: scoped streams carry no `av` and skip the fingerprint compare. The fingerprint exists to detect a *visibility-only* change a browser's `since`-delta on a stale shared-snapshot corpus would miss — but a scoped stream **replays its full (small) state every connect** (`since` is ignored), so it's never stale, and it **receives no decks** (`_scope_matches` passes only tournament + sanctions), so the private-deck leak the fingerprint/tombstones guard cannot occur. Entitlement shifts reach the bot via the live per-object `entitled_level` re-eval + the next full replay — no resync mechanism needed. (If the bot ever moved to *incremental* scoped catch-up, that — not `av` — would be the reason to revisit; a #197-class efficiency call, separate from entitlement correctness.)

*Participant identities*: the bot needs each seated player's name/nickname to render seating (it has no User store), but `_scope_matches` drops generic `user` broadcasts. So identities ride **alongside the tournament**: `_participant_user_frames()` emits the `member`-level User object for every player + organizer (deliberately the `member` column for *all* of them, **not** `entitled_level` — member carries name/nickname but no contact info, so this never leaks participant contacts to the Discord process). Catch-up seeds them; live, a tournament delivery sets `SSEConnection.needs_participant_refresh` and the async stream loop then pushes identities for any participants not yet sent (`sent_participant_uids`), so players who register *after* the bot connects still resolve. The bot caches `uid → {name, nickname}` and falls back to it (after a Discord `@mention`, then the per-tournament `display_name`) in `announcements.player_display`.

The stream then enters the **live phase**, relaying single-object events from `broadcast_precomputed()`:

```
data: {"type":"tournament","data":{...},"ts":"2026-06-03T12:00:00.123456"}
```

Note the envelope differences from the catch-up batches: singular `type` (`tournament` not `tournaments`), a single `data` object (not an array), and a `ts` field. See **Sync Cursor** below for what `ts` is and why it must not be confused with the payload's own `modified`.

### Sync Cursor (`since`)

The client reconnects with `?since=<cursor>`; the server filters `modified_at > since` (`stream_objects_new`) and re-streams everything newer. The cursor is therefore a high-water mark over the **`modified_at` column** (DB clock, naive `TIMESTAMP`, set by a `BEFORE` trigger), which is also what `sync_complete.timestamp` and the snapshot `meta.timestamp` report.

The snapshot meta **also** carries `generated_at` — the DB-clock instant the snapshot was generated (`SELECT now()`), distinct from `timestamp` (= max `modified_at` in it). The client echoes it back as `?generated_at=<…>`. It is **not** a data cursor (it never filters `modified_at`); it is a *freshness* signal. The server's resync guards key off `max(since, generated_at)` so they measure how long the client has actually been away, not when the data last changed — without it, a system with no writes for >3 days yields a `since` older than the stale-guard window and every client loops on a forced resync (`since` is a data timestamp masquerading as a wall-clock one).

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

Triggered when a viewer's data level changes — the delta only carries content changes, so an object whose *visibility* changed (without its content changing) can't reach the client any other way.

#### Access-version fingerprint (primary, connect-time)

The connect handshake asks the precise question — *"is the client based on the entitlements it currently has?"* — rather than comparing timestamps. `compute_access_version(viewer)` (`db.py`) hashes everything that determines **which** objects (and which projection) a viewer is entitled to:

```
fp = hash( DATA_SCHEMA_VERSION,                  # global wire-shape lever (replaces MINIMUM_SYNC_EPOCH)
           base_level,                           # base_data_level: full | member | public
           sorted({IC,NC,PRINCE} ∩ roles),       # overlay-granting roles only
           country if (NC or Prince) else None,  # scopes the official overlay
           sorted(organizer_tournament_uids) )   # member-only; from the GIN-indexed org query
```

- **Backend-only + opaque.** The client stores the fingerprint and echoes it; it never computes or parses it, so the input set stays server-evolvable (add/remove inputs with zero client coordination) and a lying client can only over/under-resync *itself*.
- **Self-maintaining.** Derived from current truth at connect — no write paths to enumerate, no silent-missed-bump leak. The org-set is the only DB input; it rides the GIN index on `("full"->'organizers_uids')` and only members pay the query (IC sees full everywhere; public/anon have no overlay).
- **`DATA_SCHEMA_VERSION`** is the one global lever: bump it on a wire-shape change that does **not** also bump the frontend `DB_VERSION` (a `models.py` field rename/remove, an `access_levels` projection-policy change). One bump flips every client's fp → exactly one resync. (A change that *does* ride a `DB_VERSION` bump self-heals client-side and needs no lever.)

**Transport**:
- **Seed** — `/snapshot` returns the fingerprint in an `X-Access-Version` response header (per-request, computed from the resolved viewer). It can't live in the snapshot *body* (one shared per-level file; the fp is per-user). The client reads the header via `fetch()` before opening `/stream`, so the first connect echoes a matching `av` and doesn't spuriously resync.
- **Echo** — the client persists the fp (IDB `metadata` key `last_sync_access_version`) and sends it as `/stream?av=<fp>` (EventSource can't set headers).
- **Compare** — the server recomputes the current fp from the resolved `stream_user`; `av` absent or `!=` current → resync. Tournament-scoped (bot) streams carry no `av` and skip the compare.
- **Live refresh** — a targeted-push frame (below) carries the new `av`, so the client updates its stored fp without a reconnect.

**On `av` mismatch** (or the staleness guard below): emit `{"type": "resync"}` and **return immediately**. The browser clears IndexedDB and re-fetches the snapshot (served at the viewer's *current* level), so streaming the corpus after the resync line is wasted and discards a pooled connection on the client's mid-`fetchall` teardown. Tournament-scoped (bot) streams skip the resync line (they replay full state every connect).

**Staleness guard** (orthogonal to entitlement, so the fingerprint can't replace it): the `>3-day` freshness guard (`max(since, generated_at)`) catches a client away long enough that a soft-deleted object may have been hard-purged (30-day purge), so the since-delta would miss the deletion. The old per-user `resync_after` timestamp and the global `MINIMUM_SYNC_EPOCH` are both **retired** — the fingerprint subsumes every entitlement/wire-shape resync, online changes still fire `broadcast_resync` as a live nudge, and offline changes are caught by the `av` compare at connect.

**Frontend**:
- On `resync` event: clear all IndexedDB stores + cursor keys (`last_sync_timestamp`, `last_sync_generated_at`, `last_sync_access_version`); the new snapshot re-seeds the fingerprint from its header.
- Full data follows automatically (re-snapshot → catch-up).

#### Targeted overlay invalidation (no resync)

`broadcast_personal(user_uid, *, obj_type, uid, full_dict, …, access_version)` (`broadcast.py`) pushes **one object to one user** at that user's *currently*-entitled projection — the per-user counterpart to `broadcast_precomputed`'s shared per-level frame. It re-derives `entitled_level` for the object *now*, so an entitlement transition is delivered as a single update:

- **promote** → push the object at full (upgrade the one object in IDB);
- **demote, lower projection non-null** → push the lower projection (`db.put` replaces; full-only fields drop);
- **demote, lower projection null** (a private deck → member is `None`) → push a **tombstone** (`deleted_at`) so the client evicts just that object. This is the leak fix: `compute_deck_member` is null for a private deck, so the since-catch-up could never re-send *or* evict it.

Every targeted frame carries the recomputed `access_version`. **Organizer add/remove** uses this (`_invalidate_organizer_view` in `tournaments.py`): the new organizer gets the tournament + its private decks at full; the removed organizer gets the tournament downgraded to member + a tombstone per private deck — no full resync. An **offline** organizer change is still caught by the fingerprint at the next connect (the org-set term), which is why a resync remains the offline fallback.

**Triggers** (fingerprint at connect / live nudge while connected):
- VEKN operations: `/claim`, `/sponsor`, `/link`, `/force-abandon`, `/abandon` (vekn_id gained/lost → base level changes).
- Organizer add/remove on a tournament → **targeted push** while online (no resync); fingerprint org-set term while offline.
- User update: an **access-affecting** role (`NC`/`Prince`/`IC` — the closed set `base_data_level`/`access_levels.py` branch on) gained/lost, or vekn_id changed. A non-access role (PT/Judge/…) changes no projection, so it does **not** move the fingerprint.
- Wire-shape change: bump `DATA_SCHEMA_VERSION` in `db.py`.

### Access Entitlement

`entitled_level(viewer, *, obj_type, uid, country, org_uids, obj_user_uid) → "public"|"member"|"full"` in `broadcast.py` is the **single source of truth** for per-object access. It is called by both the live broadcast (`broadcast_precomputed`) and the tournament-scoped catch-up (`_scoped_catchup_frames`). Logic: IC → full; NC/Prince same country → full; explicit organizer → full; member with own profile/deck → full; any member → member; otherwise public.

### Generic Broadcast

Single `broadcast_precomputed()` function (in `broadcast.py`) with per-viewer filtering handles all object types. `BroadcastData` carries `tournament_uid` (the tournament a sanction/deck belongs to) so `_scope_matches` can route events to tournament-scoped connections without re-reading the DB.

Each connection has a bounded `CoalescingQueue` (maxsize 30). The queue keeps only the **latest frame per `(type, uid)` key** — successive whole-object snapshots of the same tournament supersede each other, so a stalled client accumulates ~1 object instead of ~30 stale copies. Ephemeral events (judge_call, resync) carry no key and are never coalesced. On `QueueFull` (a slow/stalled consumer past the 30-distinct-key cap), the connection is marked `closed` and evicted from the broadcast set; the SSE generator sees the flag, **ends the stream**, and the browser's `EventSource` auto-reconnects with `?since=<cursor>` and catches up. This is deliberate: a dropped event must not leave the client OPEN on a queue that no longer receives broadcasts (silently "deaf"). Lossless catch-up depends on the cursor being accurate — see **Sync Cursor** above.

### Snapshot-Based Initial Sync

On first connect (no `since` timestamp), the frontend fetches a pre-computed gzip snapshot (`GET /snapshot`) instead of streaming from scratch. Snapshots are regenerated every 15 minutes by a background task (`snapshots.py`), one per access level (public/member/full). This avoids holding a DB connection open for the full initial stream of potentially thousands of objects. The same `_resolve_viewer()` credential logic applies (see **Credential Transport** above). `/snapshot` streams the gzip from disk in chunks, holding one fd open per response (so the 15-min atomic-rename regen stays consistent mid-stream) — the full file is never read into app heap, so hundreds of concurrent door-open reconnects don't spike memory. Snapshot generation (`snapshots.py`) reuses `stream_objects_new(exclude_deleted=True)` — same keyset-paginated, pool-releasing path as SSE catch-up.

After the snapshot loads, the SSE stream picks up from the snapshot's `timestamp` (`?since=`) plus its `generated_at` (`?generated_at=`), delivering any changes that occurred since generation.

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

All objects have `deleted_at`. On a tombstone (`item.deleted_at` set) the client
**hard-deletes** the row from its store; otherwise it saves. No type is exempt —
**users included**: even though tournament standings/seating store only `user_uid`
(name resolved via `getUser`), every deletable member is VEKN-less (delete refuses
VEKN-bearing members; `merge_users` and the import shells omit the id) and
tournament participation requires a `vekn_id`, so a deleted user is never a live
player reference. Server-side `deleted_at` is only a retention window so the
deletion can be streamed to catch-up clients — persisting tombstones client-side
buys nothing. (Legacy pre-VEKN imported events may then render a raw uid for a
deleted nameless player — cosmetic, accepted.)

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
