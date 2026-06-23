import type { Sanction } from "$lib/types";

/** Normalize a string for diacritic/accent-insensitive search (lowercase + strip combining marks). */
export function normalizeSearch(s: string): string {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

export function formatScore(gw: number, vp: number, tp: number): string {
  const s = gw > 0 ? `${gw}GW${vp}` : `${vp}VP`;
  return `${s} ${tp}TP`;
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
