/**
 * Map any thrown value to a user-facing message.
 *
 * Resolution order (shape mapper + structured codes):
 * - `EngineError` (typed WASM rejection or coded JS pre-check) → localized
 *   message from its stable code; unknown code falls back to its English
 *   message. `internal` maps to a generic localized message (detail is logged,
 *   not shown).
 * - `ApiError` → same code mapping when the 400 body carried `code`/`params`;
 *   otherwise the server's `detail` verbatim (legacy path).
 * - plain string → legacy WASM passthrough: any engine surface not yet wrapped
 *   throws the wire JSON or free text as a JS string primitive
 *   (`e instanceof Error` is FALSE) — parse a code out of it if possible.
 * - `TypeError` → fetch() transport failure (offline mid-flight, DNS, CORS,
 *   server down): its message ("Failed to fetch") is cryptic and untranslated,
 *   so map to a friendly localized one.
 */
import { ApiError } from './api';
import { EngineError, engineErrorFromThrown, errorCodeToMessage } from './error-codes';
import * as m from './paraglide/messages.js';

export { EngineError } from './error-codes';

/** True when `e` is a fetch() network rejection (offline, DNS, CORS, server down). */
export function isNetworkError(e: unknown): boolean {
  return e instanceof TypeError;
}

function engineMessage(code: string, params: Record<string, string>, english: string | undefined, fallback: string): string {
  if (code === 'internal') {
    console.error('[engine] internal error:', params.detail ?? english);
    return errorCodeToMessage(code) ?? fallback;
  }
  return errorCodeToMessage(code, params) ?? english ?? fallback;
}

/**
 * Resolve a thrown value to the clearest message we can show the user.
 * `fallback` is only used for genuinely typeless/empty throws.
 */
export function toUserMessage(e: unknown, fallback: string): string {
  if (e instanceof EngineError) return engineMessage(e.code, e.params, e.message, fallback);
  if (e instanceof ApiError) {
    if (e.code) return engineMessage(e.code, e.params ?? {}, e.detail ?? e.message, fallback);
    return e.detail ?? e.message;
  }
  if (typeof e === 'string') {
    const engine = engineErrorFromThrown(e);
    if (engine) return engineMessage(engine.code, engine.params, engine.message, fallback);
    return e || fallback; // legacy WASM free-text rejection
  }
  if (isNetworkError(e)) return m.error_network_unreachable();
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}
