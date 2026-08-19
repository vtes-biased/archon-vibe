// Content languages: the whole of ISO 639-1, not a shortlist. A member writes in
// whatever language they speak, and the five interface locales are a separate and
// much smaller vocabulary. The backend validates only the two-letter shape.
const ISO_639_1 = [
  "aa", "ab", "ae", "af", "ak", "am", "an", "ar", "as", "av", "ay", "az",
  "ba", "be", "bg", "bi", "bm", "bn", "bo", "br", "bs",
  "ca", "ce", "ch", "co", "cr", "cs", "cu", "cv", "cy",
  "da", "de", "dv", "dz",
  "ee", "el", "en", "eo", "es", "et", "eu",
  "fa", "ff", "fi", "fj", "fo", "fr", "fy",
  "ga", "gd", "gl", "gn", "gu", "gv",
  "ha", "he", "hi", "ho", "hr", "ht", "hu", "hy", "hz",
  "ia", "id", "ie", "ig", "ii", "ik", "io", "is", "it", "iu",
  "ja", "jv",
  "ka", "kg", "ki", "kj", "kk", "kl", "km", "kn", "ko", "kr", "ks", "ku", "kv", "kw", "ky",
  "la", "lb", "lg", "li", "ln", "lo", "lt", "lu", "lv",
  "mg", "mh", "mi", "mk", "ml", "mn", "mr", "ms", "mt", "my",
  "na", "nb", "nd", "ne", "ng", "nl", "nn", "no", "nr", "nv", "ny",
  "oc", "oj", "om", "or", "os",
  "pa", "pi", "pl", "ps", "pt",
  "qu",
  "rm", "rn", "ro", "ru", "rw",
  "sa", "sc", "sd", "se", "sg", "si", "sk", "sl", "sm", "sn", "so", "sq", "sr",
  "ss", "st", "su", "sv", "sw",
  "ta", "te", "tg", "th", "ti", "tk", "tl", "tn", "to", "tr", "ts", "tt", "tw", "ty",
  "ug", "uk", "ur", "uz",
  "ve", "vi", "vo",
  "wa", "wo",
  "xh",
  "yi", "yo",
  "za", "zh", "zu",
];

const names = new Map<string, string>();

/** A language named in itself, so a reader recognises their own at a glance. */
export function languageName(code: string): string {
  const cached = names.get(code);
  if (cached) return cached;
  let label = code;
  try {
    label = new Intl.DisplayNames([code], { type: "language" }).of(code) ?? code;
  } catch {
    label = code;
  }
  names.set(code, label);
  return label;
}

let sorted: { value: string; label: string }[] | null = null;

/** Every content language, endonym-sorted. Built on first use — the picker that
 * needs it is behind a modal, and the page filter only ever names what it holds. */
export function allLanguages(): { value: string; label: string }[] {
  sorted ??= ISO_639_1.map((value) => ({ value, label: languageName(value) })).sort(
    (a, b) => a.label.localeCompare(b.label),
  );
  return sorted;
}
