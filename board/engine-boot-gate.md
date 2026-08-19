# Gate boot on the WASM engine

## Why there is nothing to protect

Every `getEngineReactive()` fallback is fail-closed or fail-wrong, never
fail-useful. Cold, `checkPermission` hides every permission-gated control,
`displayStandings` blanks the standings, `attestedPlayerCount` reads zero, and
`normalizeSearch` folds with a mark-strip that misses `Ł`. `engineLoadFailed()`
has exactly one consumer, the layout banner — so the "degraded mode" is a red
notice over an app whose buttons have vanished and whose numbers are blank, which
is itself the thing [dogmas](../wiki/dogmas.md) forbids.

Six bugs have come out of the window. Four shipped: the cached member index and
card token map folding cold, the raffle count, the decklist export sort, and the
printed seating sheet an organizer tapes to the door. Two are still live and are
the reason this is ranked as correctness:

- `checkTableVpsSync` (`engine.ts`) returns `null` for both "table is scorable"
  and "engine not up" — the only **fail-open** one of the set.
- `finalsQualification` (`engine.ts`) fabricates a `closed` verdict cold.

## Why gating cannot brick the offline case

`archon_engine_bg.<hash>.wasm` is emitted into `_app/immutable/assets/` by the
`?url` import and is in SvelteKit's `build` array, so `cache.addAll(ASSETS)`
precaches it — **atomically**. The service worker installs with shell *and* wasm
or not at all; there is no servable shell without a servable engine. A version
bump precaches in the background while the old worker serves, so the refetch is
never on the user's critical path. Offline, a failed install leaves the old
worker serving a consistent old pair.

The gate therefore waits on the network exactly once per device: the first visit.
Warm boot is a Cache Storage hit plus a compile that Chrome's wasm code cache
already skips (streaming compile, 526 KB, over the 128 KB threshold), overlapped
with parsing the 1.6 MB entry chunk.

## The shape

In `+layout.svelte`: `const engineInit = initEngine()` at script top level —
**not** `onMount`, which costs a hydration round-trip of latency for nothing.
Shell, nav and banners stay rendered; only `{@render children()}` goes inside
`{#await engineInit}` splash `{:then}` children `{:catch}` error screen.
`syncManager.connect()` stays in `onMount` so sync runs in parallel.

**The retry control must be `location.reload()`.** `initError` is sticky in
`engine-instance.ts`, so a button re-calling `initEngine()` re-throws forever.

A top-level `await` in `engine-instance.ts` is the wrong shape and must not be
used: the module sits in the entry graph, so a rejection kills SvelteKit start —
blank page, no error UI, no retry.

## What goes

All 21 cold-engine branches — 20 in `engine.ts` plus `normalizeSearch`'s ternary
in `utils.ts` — `getEngineReactive` (replaced by a non-null `getEngine()` that
throws if cold), the nullable return types,
`stores/engine-ready.svelte.ts` with its three `engineReady()` consumers and the
`engineLoadFailed()` banner, and the `normalizeSearch` cold-window entry in
`wiki/hazards.md`.

This also retires the reason to generate the engine's static reference tables
(library type order, sanction reference, community link reference, the fold map)
into TypeScript at build time: with the gate they are never read cold, so there
is no second line to file.

## What stays

The async `await initEngine()` in `db.ts` (`getUserIndex`) and `cards.ts`
(`searchCards`). Those are **ordering**, not guards: both build a session-cached
index and both are reachable from the sync the layout starts in `onMount`, which
runs outside the gated subtree. Their `.catch(() => {})` can go — a permanently
failed engine now renders the error screen instead of a working search.

Two go, both reached only from inside the gate: `social-text.ts`'s, since
`generateResultsText` has no caller but `CopyResultsButton.svelte` and
`ToolsSheet.svelte`, and `RoundsTab.svelte`'s in `printRound`. The comment above
`printRound`'s `window.open` stays — the popup must still be opened on the click,
which is a browser rule the gate does not touch.

## Order

Ahead of the raffle-pool line, whose "distinct not-known-yet state rather than a
disabled zero" requirement this deletes. Doing the raffle first builds a tri-state
that this then removes.
