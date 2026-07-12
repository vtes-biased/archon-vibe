import type { Sanction } from "$lib/types";

/** Normalize a string for diacritic/accent-insensitive search (lowercase + strip combining marks). */
export function normalizeSearch(s: string): string {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
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

/**
 * Interpret a naive ISO datetime (no offset) as wall-clock time in the given
 * IANA timezone and return the real instant. Tournament.start/finish are stored
 * this way (wall-clock in tournament.timezone) — plain `new Date(iso)` would
 * misread them as browser-local. Strings carrying an offset parse as-is.
 */
export function zonedDate(iso: string, timeZone: string): Date {
  if (/(Z|[+-]\d{2}:?\d{2})$/.test(iso)) return new Date(iso);
  const asUtc = new Date(iso + "Z");
  if (isNaN(asUtc.getTime())) return new Date(iso);
  // two passes: the offset near the target instant, corrected for DST edges
  const approx = asUtc.getTime() - tzOffsetMs(timeZone, asUtc);
  return new Date(asUtc.getTime() - tzOffsetMs(timeZone, new Date(approx)));
}

/**
 * Sanctions visible on member-directory surfaces (profile page, member list).
 * Cautions stay private to the tournament where they were issued — they never
 * surface in the directory, not even for managers (IC/Ethics see them inside
 * the tournament instead). Warnings, standings adjustments and DQs are
 * member-visible for 18 months (the window is applied by
 * getActiveSanctionsForUser), and suspension/probation are membership-level.
 */
export function visibleSanctions(sanctions: Sanction[]): Sanction[] {
  return sanctions.filter(s => s.level !== "caution");
}
