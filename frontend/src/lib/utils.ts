/** Normalize a string for diacritic/accent-insensitive search (lowercase + strip combining marks). */
export function normalizeSearch(s: string): string {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

export function formatScore(gw: number, vp: number, tp: number): string {
  const s = gw > 0 ? `${gw}GW${vp}` : `${vp}VP`;
  return `${s} ${tp}TP`;
}
