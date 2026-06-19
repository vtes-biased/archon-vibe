---
name: sync-resync-branch-zero-delay-loop
description: sync.ts resync onmessage branch reconnects with ZERO delay — tight-loop risk for any persistent resync trigger; cold-start trigger fixed, branch itself unguarded
metadata:
  type: project
---

The `resync` onmessage branch in `frontend/src/lib/sync.ts` (the `if (message.type === 'resync')` block: clear buffers → `clearAllStores()` → `disconnect()` → `void this.connect()`) reconnects with **zero backoff delay**.

**Why:** The original cold-start tight loop (fresh deploy, `VEKN_SYNC_ENABLED=true`, `/snapshot` 503s during the multi-minute first-sync warm-up → client opened a tagless `/stream` → server av-handshake always mismatches → forced `resync` → clear + zero-delay reconnect → repeat at hundreds req/s) was fixed by making `connect()` early-return to `handleError(true)` when `fetchSnapshot` returns null on a first connect (no tagless stream is ever opened). That `transient` path retries the SNAPSHOT with capped exponential backoff (1s→120s), `Infinity` attempts. So the cold-start TRIGGER is closed.

But the resync branch's zero-delay reconnect is still **unguarded for any OTHER resync cause** — a persistent av mismatch the client can never echo back to a match (`compute_access_version` in db.py always returns non-null), repeated staleness rejection, or a server-side av-computation bug. Any of these loops at full speed again: clear → snapshot reload → stream opens → server resyncs again → repeat. The per-iteration snapshot fetch throttles it somewhat, but `clearAllStores()` + full snapshot reload on a hot loop is its own resource sink.

Also: `fetchSnapshot` collapses 503 (warm-up) and genuinely-broken-snapshot (500, corrupt gzip, parse/decompress throw) to the same `null`. The `transient` path now retries BOTH forever and silently — a broken snapshot never reaches the terminal `'Failed to connect after multiple attempts'` error, so a broken-snapshot incident is invisible client-side.

**How to apply:** When touching the resync branch or any new resync trigger, route the reconnect through backoff (e.g. count consecutive resyncs, past a small threshold call `void this.handleError(true)` instead of bare `void this.connect()`, or add a fixed floor delay) — never a zero-delay `connect()`. For broken-vs-warm-up snapshot ambiguity, consider a non-terminal telemetry signal after N transient attempts so prolonged stalls surface without stopping retries. Related: [[sync-cursor-timestamp-trap]], [[destructive-store-wipe-offline-rescue]].
