// VTES icon font mappings (krcg-static ankha2.otf / vtes-clans.otf).
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


export function disciplineIcon(trigram: string): string | undefined {
  return DISCIPLINE_ICONS[trigram];
}

export function typeIcon(type: string): string | undefined {
  return TYPE_ICONS[type];
}

/** Advanced-vampire glyph in the Ankha VTES font (render with `.vtes-d`). */
export const ADVANCED_ICON = '|';

// Circled-number badge for a crypt group ("3" → "③"). Groups are 1–7; the
// group-independent "any" gets no badge.
export function groupCircle(group: string): string {
  const n = Number(group);
  return Number.isInteger(n) && n >= 1 && n <= 7 ? String.fromCharCode(0x245f + n) : '';
}

