// EngineError/ApiError with a code → localized message; unknown code falls back to English. Plain
// string → legacy WASM passthrough (parse a code if possible).
import { ApiError } from './api';
import { EngineError, NetworkError, engineErrorFromThrown, errorCodeToMessage } from './error-codes';

export { EngineError } from './error-codes';

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
  if (e instanceof NetworkError) return e.message;
  if (e instanceof TypeError) {
    console.error(e);
    return fallback;
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}
