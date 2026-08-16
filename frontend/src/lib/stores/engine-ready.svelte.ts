// A module-level `let` engine reference is invisible to Svelte's reactivity, so a `$derived` that
// calls a sync engine helper would run once cold and never re-run once WASM finishes loading. Read `engineReady()` inside such a derivation to subscribe.
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

/** When true the app is degraded — permission controls fail-closed (vanish), optimistic mutations
 * fall to server-only, and standings/validation return empty — so the UI must say so. */
export function engineLoadFailed(): boolean {
  return loadFailed;
}

/** Flipped by `initEngine()` when WASM instantiation throws. */
export function markEngineLoadFailed(): void {
  loadFailed = true;
}
