> Elaborated context for one line in `BOARD.md`. Deleted with the line.

# The update stream dies without notice and nothing notices

**Doc-impact:** `wiki/sync.md` — the heartbeat contract and the recovery rule,
recorded beside the queue-overflow decision they extend.

## What was observed (production, 2026-08-23)

The owner created a member and changed a role from a long-lived tab. Both writes
landed; neither appeared in the members list. Only a hard reload fixed it.

- `POST /api/users/` → 201 at 09:55:50, member stored (`modified_at` 09:55:48).
- Role change on 5360022 stored at 07:13:10 (`["Judge", "Rulemonger"]`).
- Live `user` frames are written to IndexedDB immediately, unbuffered
  (`sync.ts:481`), so the absence proves no frame arrived.
- The tab was deaf for **2h45m+**, straight through a backend restart
  (uvicorn pid 271460 → 292272, between 08:07:55 and 09:18:51).

No banner, no warning. The status chip read "online" throughout.

## Why nothing recovered

Reconnection hangs entirely off `EventSource.onerror` (`sync.ts:508`). That fires
only when the browser *observes* a failure. A socket that dies silently — sleep,
wifi change, NAT timeout — leaves `readyState` at OPEN forever: nothing arrives,
nothing errors. The 5-attempt / ~31s budget (`sync.ts:117`) and its terminal
branch (`sync.ts:603`) were never reached, which is why no banner appeared.

The restart could not help either: by then the client socket was already a
zombie, so the RST went nowhere the client could see. Restart duration is
irrelevant here — no retry was ever in flight.

**The heartbeat is invisible.** `main.py:1253` emits `: keepalive` every 30s and
nginx holds the stream open (`proxy_read_timeout 1d`). But `: keepalive` is an
SSE *comment*, and native `EventSource` discards comment lines without
dispatching anything to JS. No client watchdog can be built on it as it stands.
There is no watchdog in `sync.ts` at all.

**The chip cannot express this.** `isOnline = navigator.onLine`
(`+layout.svelte:24`), rendered at `:249` as
`isOnline ? (isSyncing ? syncing : online) : offline`. Stream health is not an
input. `syncError` drives only the banner (`:144`) and was never set.

## Three interdependent parts

1. Server emits the heartbeat as a real event, not a `:` comment.
2. Client watchdog forces a reconnect after ~2 missed heartbeats, and does not go
   permanently terminal while connectivity is present.
3. Chip derives from stream health, not `navigator.onLine`.

Fixing 3 without 2 only makes the tab honest about being broken.

## Constraint

`wiki/hazards.md:288` — any reconnect must route through the existing backoff, or
a persistent cause spins a full-speed clear-and-reconnect loop. The watchdog is
exactly the kind of path that could trip this.

## Precedents this extends

- `wiki/sync.md:258` already decided this principle one layer up: on queue
  overflow the server ends the stream so a client is never left "OPEN on a queue
  that no longer receives broadcasts, silently deaf". Same failure mode, a layer
  the decision does not reach.
- `wiki/discord.md:109` — the bot hit the identical wedge ("no error and no
  reconnect, since `sock_read` never fires") and bounded it with a timeout. The
  browser is the one consumer with no read timeout at all.

## Offline tournaments

`handleError` already retries indefinitely when a tournament is offline-locked
(`sync.ts:593`) — the existing seam for that distinction. No new one is needed.
