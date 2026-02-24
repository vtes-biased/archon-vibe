/**
 * VTES icon font mappings (from krcg-static ankha2.otf and vtes-clans.otf).
 *
 * Discipline trigrams (lowercase = inferior, uppercase = superior) → font character.
 * Card type names → font character.
 * Clan names → font character.
 */

/** Discipline trigram → Ankha VTES font character */
export const DISCIPLINE_ICONS: Record<string, string> = {
  // Inferior (lowercase trigrams)
  aus: 'a', obe: 'b', cel: 'c', dom: 'd', dem: 'e', for: 'f',
  san: 'g', thn: 'h', ani: 'i', pro: 'j', chi: 'k', val: 'l',
  mel: 'm', nec: 'n', obf: 'o', pot: 'p', qui: 'q', pre: 'r',
  ser: 's', tha: 't', vis: 'u', vic: 'v', abo: 'w', myt: 'x',
  dai: 'y', spi: 'z', tem: '?', str: '+', obt: '$', mal: '<',
  obl: 'ø',
  // Superior (uppercase trigrams)
  AUS: 'A', OBE: 'B', CEL: 'C', DOM: 'D', DEM: 'E', FOR: 'F',
  SAN: 'G', THN: 'H', ANI: 'I', PRO: 'J', CHI: 'K', VAL: 'L',
  MEL: 'M', NEC: 'N', OBF: 'O', POT: 'P', QUI: 'Q', PRE: 'R',
  SER: 'S', THA: 'T', VIS: 'U', VIC: 'V', ABO: 'W', MYT: 'X',
  DAI: 'Y', SPI: 'Z', TEM: '!', STR: '=', OBT: '£', MAL: '>',
  OBL: 'Ø',
  // Virtues (Imbued)
  inn: '#', def: '@', mar: '&', jud: '%', ven: '(', vin: ')', red: '*',
  viz: ')',
};

/** Card type → Ankha VTES font character */
export const TYPE_ICONS: Record<string, string> = {
  'Action': '0',
  'Action Modifier': '1',
  'Political Action': '2',
  'Ally': '3',
  'Combat': '4',
  'Equipment': '5',
  'Reflex': '6',
  'Reaction': '7',
  'Retainer': '8',
  'Event': '[',
  'Master': '9',
  'Conviction': '¤',
  'Power': '§',
  'Flight': '^',
  'Merged': 'µ',
};

/** Full discipline name → lowercase trigram (for lookups) */
export const DISCIPLINE_NAME_TO_TRIGRAM: Record<string, string> = {
  'Abombwe': 'abo', 'Animalism': 'ani', 'Auspex': 'aus',
  'Blood Sorcery': 'tha', 'Celerity': 'cel', 'Chimerstry': 'chi',
  'Daimoinon': 'dai', 'Dementation': 'dem', 'Dominate': 'dom',
  'Fortitude': 'for', 'Maleficia': 'mal', 'Melpominee': 'mel',
  'Mytherceria': 'myt', 'Necromancy': 'nec', 'Obeah': 'obe',
  'Obfuscate': 'obf', 'Oblivion': 'obl', 'Obtenebration': 'obt',
  'Potence': 'pot', 'Presence': 'pre', 'Protean': 'pro',
  'Quietus': 'qui', 'Sanguinus': 'san', 'Serpentis': 'ser',
  'Spiritus': 'spi', 'Striga': 'str', 'Temporis': 'tem',
  'Thanatosis': 'thn', 'Thaumaturgy': 'tha', 'Valeren': 'val',
  'Vicissitude': 'vic', 'Visceratika': 'vis',
};

/**
 * Get the font character for a discipline trigram.
 * Input can be "for", "FOR", "Fortitude", etc.
 */
export function disciplineIcon(trigram: string): string | undefined {
  return DISCIPLINE_ICONS[trigram];
}

/**
 * Get the font character for a card type.
 */
export function typeIcon(type: string): string | undefined {
  return TYPE_ICONS[type];
}

