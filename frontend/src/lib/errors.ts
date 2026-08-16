// EngineError/ApiError with a code → localized message; unknown code falls back to English. Plain
// string → legacy WASM passthrough (parse a code if possible). TypeError → network failure.
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

/** `fallback` is only used for genuinely typeless/empty throws. */
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
