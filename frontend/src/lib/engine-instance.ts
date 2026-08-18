import { engineReady, markEngineReady, markEngineLoadFailed } from './stores/engine-ready.svelte';
import { engineErrorFromThrown } from './error-codes';

export type WasmEngine = import('../../../engine/pkg/archon_engine').WasmEngine;

// wasm-bindgen's default init resolves `new URL(wasmUrl, import.meta.url)` against the chunk it's
// bundled into, doubling the path and 404ing — hand it wasmUrl explicitly instead (see initEngine).
import wasmUrl from '../../../engine/pkg/archon_engine_bg.wasm?url';

/** wasm-bindgen throws the Err arm as a JS string (the engine's `{code,params,message}` JSON), so
 * re-throw it as a typed `EngineError`. The catch wraps only the call, not the `JSON.parse` of a success. */
export function callEngine<T>(fn: () => T): T {
  try {
    return fn();
  } catch (e) {
    throw engineErrorFromThrown(e) ?? e;
  }
}

let wasmEngine: WasmEngine | null = null;
let initPromise: Promise<void> | null = null;
let initError: Error | null = null;

export async function initEngine(): Promise<WasmEngine> {
  if (wasmEngine) return wasmEngine;
  if (initError) throw initError;

  if (!initPromise) {
    initPromise = (async () => {
      try {
        const wasm = await import('../../../engine/pkg/archon_engine');
        // Root the base-relative wasmUrl against the origin: fetch() would otherwise resolve it
        // against the current page, which 404s on deep routes (e.g. /tournaments/<uid>).
        await wasm.default({ module_or_path: new URL(wasmUrl, location.origin).href });
        wasmEngine = new wasm.WasmEngine();
        markEngineReady();
      } catch (e) {
        initError = e instanceof Error ? e : new Error(String(e));
        markEngineLoadFailed();
        throw initError;
      }
    })();
  }

  await initPromise;
  return wasmEngine!;
}

/** `wasmEngine` is a plain module `let` Svelte can't track; reading `engineReady()` here registers
 * a reactive dependency so sync wrappers re-run once the engine loads, instead of computing once cold. */
export function getEngineReactive(): WasmEngine | null {
  engineReady();
  return wasmEngine;
}
