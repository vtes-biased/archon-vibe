/**
 * Reactive flag for WASM engine readiness.
 *
 * `getEngineSync()` reads a module-level `let` that Svelte's reactivity cannot
 * track, so a `$derived` that calls a sync engine helper would run once with a
 * cold engine and never re-run once WASM finishes loading. Read `engineReady()`
 * inside such a derivation to subscribe to readiness and recompute when the
 * engine lands.
 */
let ready = $state(false);
let loadFailed = $state(false);

/** Read inside `$derived`/`$effect` to re-run when the engine becomes ready. */
export function engineReady(): boolean {
  return ready;
}

/** Flipped by `initEngine()` once the WASM module is instantiated. */
export function markEngineReady(): void {
  ready = true;
  loadFailed = false;
}

/**
 * Reactive flag: the WASM engine failed to load. When true the app is degraded —
 * permission controls fail-closed (vanish), optimistic mutations fall to
 * server-only, and standings/validation return empty — so the UI must say so.
 */
export function engineLoadFailed(): boolean {
  return loadFailed;
}

/** Flipped by `initEngine()` when WASM instantiation throws. */
export function markEngineLoadFailed(): void {
  loadFailed = true;
}
