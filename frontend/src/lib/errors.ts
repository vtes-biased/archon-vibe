/**
 * Map any thrown value to a user-facing message.
 *
 * Three traps this untangles:
 * - The WASM engine rejects by throwing a plain JS string (every export is
 *   `Result<String, String>`, so wasm-bindgen throws the `Err` string). That means
 *   `e instanceof Error` is FALSE for an engine rejection — the old
 *   `e instanceof Error ? e.message : fallback` shape silently DROPPED the engine's
 *   reason for a generic message. Here we surface the string.
 * - `fetch()` rejects with a `TypeError` on a transport failure (offline mid-flight,
 *   DNS, CORS, server down). Its `.message` ("Failed to fetch" / "Load failed") is
 *   cryptic and untranslated, so we map it to a friendly localized message.
 * - `ApiError` carries the server's (often engine-sourced) reason in `detail`.
 */
import { ApiError } from './api';
import * as m from './paraglide/messages.js';

/** True when `e` is a fetch() network rejection (offline, DNS, CORS, server down). */
export function isNetworkError(e: unknown): boolean {
  return e instanceof TypeError;
}

/**
 * Resolve a thrown value to the clearest message we can show the user.
 * `fallback` is only used for genuinely typeless/empty throws.
 */
export function toUserMessage(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.detail ?? e.message;
  if (typeof e === 'string') return e || fallback;        // WASM engine rejection
  if (isNetworkError(e)) return m.error_network_unreachable();
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}
