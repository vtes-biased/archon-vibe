// Country code → default UI/content language. Reference data shared by the
// community and profile views (best-effort default; the user can always pick
// another language). Not exhaustive — unlisted countries fall back at the call site.
export const COUNTRY_LANGUAGE: Record<string, string> = {
  US: 'en', GB: 'en', AU: 'en', CA: 'en', NZ: 'en', IE: 'en', ZA: 'en',
  FR: 'fr', BE: 'fr', CH: 'fr', MC: 'fr',
  ES: 'es', MX: 'es', AR: 'es', CO: 'es', CL: 'es', PE: 'es', VE: 'es', EC: 'es', UY: 'es', PY: 'es', BO: 'es', CR: 'es', PA: 'es', GT: 'es', HN: 'es', SV: 'es', NI: 'es', CU: 'es', DO: 'es', PR: 'es',
  PT: 'pt', BR: 'pt',
  IT: 'it',
  DE: 'de', AT: 'de', LI: 'de',
  PL: 'pl', FI: 'fi', SE: 'sv', NL: 'nl', NO: 'no', DK: 'da',
  JP: 'ja', CN: 'zh', TW: 'zh', KR: 'ko', RU: 'ru',
  CZ: 'cs', HU: 'hu', RO: 'ro', BG: 'bg', HR: 'hr', GR: 'el', TR: 'tr',
  TH: 'th', VN: 'vi',
};
