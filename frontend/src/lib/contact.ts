/** Officials' contact_email/contact_phone are cloaked as base64 in the public projection
 * (backend access_levels.py) as a harvester speed-bump; member/full get plaintext. Keep the prefix and scheme in sync with access_levels.py. */
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
