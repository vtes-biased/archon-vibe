import type { Sanction } from "$lib/types";

/** The letters that carry no NFD decomposition, so dropping combining marks leaves them untouched.
 * Third copy of `fold_ascii` in `engine/src/cards.rs` and `geonames.fold_ascii`; all three must agree. */
const FOLD: Record<string, string> = {
  '\u0142': 'l',
  '\u00f8': 'o',
  '\u0111': 'd',
  '\u00f0': 'd',
  '\u0127': 'h',
  '\u0131': 'i',
  '\u0167': 't',
  '\u00e6': 'ae',
  '\u0153': 'oe',
  '\u00fe': 'th',
  '\u00df': 'ss',
};
const FOLD_RE = new RegExp(`[${Object.keys(FOLD).join('')}]`, 'g');

/** Normalize a string for accent-insensitive search: lowercase, strip combining marks, fold the
 * survivors to ASCII ("Pawel" finds "Pawe\u0142"). */
export function normalizeSearch(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(FOLD_RE, (c) => FOLD[c]!);
}

/** Splits on any run of non-alphanumerics, applied to BOTH the indexed field and the query, so every
 * search is word-prefix ("vin" finds Vincent, "inc" finds nobody) \u2014 matching an email as one substring would re-admit mid-name hits. */
export function searchTokens(s: string): string[] {
  return normalizeSearch(s).split(/[^\p{L}\p{N}]+/u).filter(Boolean);
}

/** Every query term must word-prefix one of `tokens`. Empty terms match all. */
export function matchesAllTerms(tokens: string[], terms: string[]): boolean {
  return terms.every((term) => tokens.some((tok) => tok.startsWith(term)));
}

export function formatScore(gw: number, vp: number, tp: number): string {
  const s = gw > 0 ? `${gw}GW${vp}` : `${vp}VP`;
  return `${s} ${tp}TP`;
}

/** Offset (ms) of an IANA timezone at a given instant. */
function tzOffsetMs(timeZone: string, date: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone, hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(date);
  const get = (type: string) => +(parts.find((p) => p.type === type)?.value ?? "0");
  const hour = get("hour");
  const asUtc = Date.UTC(
    get("year"), get("month") - 1, get("day"),
    hour === 24 ? 0 : hour, get("minute"), get("second"),
  );
  return asUtc - date.getTime();
}

/** Interprets a naive ISO datetime (no offset) as wall-clock time in the given IANA timezone —
 * Tournament.start/finish are stored this way, so plain `new Date(iso)` would misread them as browser-local. Strings with an offset parse as-is. */
export function zonedDate(iso: string, timeZone: string): Date {
  if (/(Z|[+-]\d{2}:?\d{2})$/.test(iso)) return new Date(iso);
  const asUtc = new Date(iso + "Z");
  if (isNaN(asUtc.getTime())) return new Date(iso);
  // two passes: the offset near the target instant, corrected for DST edges
  const approx = asUtc.getTime() - tzOffsetMs(timeZone, asUtc);
  return new Date(asUtc.getTime() - tzOffsetMs(timeZone, new Date(approx)));
}

/** Sanctions visible on member-directory surfaces. Cautions stay private to their tournament (even
 * IC/Ethics see them only inside it); warnings/SA/DQ are member-visible for 18 months, suspension/probation are membership-level. */
export function visibleSanctions(sanctions: Sanction[]): Sanction[] {
  return sanctions.filter(s => s.level !== "caution");
}
