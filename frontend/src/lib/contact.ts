/**
 * Contact-field de-obfuscation.
 *
 * Anonymous viewers receive officials' contact_email / contact_phone cloaked as
 * base64 in the public projection (see backend access_levels.py) so the
 * plaintext never appears in /sync/snapshot?level=public — deterring naive bulk
 * harvesters. Authenticated viewers (member/full) get plaintext. This decoder
 * handles both: cloaked values are decoded, plaintext passes through unchanged.
 *
 * Keep the prefix and scheme in sync with access_levels.py.
 */
const OBFUSCATED_PREFIX = "#b64#";

export function deobfuscateContact(value: string | null | undefined): string {
  if (!value) return "";
  if (!value.startsWith(OBFUSCATED_PREFIX)) return value;
  try {
    const b64 = value.slice(OBFUSCATED_PREFIX.length);
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return value; // malformed → show as-is rather than break rendering
  }
}
