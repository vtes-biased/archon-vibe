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
  dai: 'y', spi: 'z', tem: '?', str: 'à', obt: '$', mal: 'â',
  obl: 'n', // oblivion uses same glyph as necromancy
  // Superior (uppercase trigrams)
  AUS: 'A', OBE: 'B', CEL: 'C', DOM: 'D', DEM: 'E', FOR: 'F',
  SAN: 'G', THN: 'H', ANI: 'I', PRO: 'J', CHI: 'K', VAL: 'L',
  MEL: 'M', NEC: 'N', OBF: 'O', POT: 'P', QUI: 'Q', PRE: 'R',
  SER: 'S', THA: 'T', VIS: 'U', VIC: 'V', ABO: 'W', MYT: 'X',
  DAI: 'Y', SPI: 'Z', TEM: '!', STR: 'á', OBT: '£', MAL: 'ã',
  OBL: 'N',
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
};

/** Clan name → VTES Clans font character (modern icons preferred) */
export const CLAN_ICONS: Record<string, string> = {
  'Abomination': 'A', 'Ahrimane': 'B', 'Akunanse': 'C',
  'Banu Haqim': 'n', 'Assamite': 'n',
  'Baali': 'E', 'Blood Brother': 'F',
  'Brujah': 'o', 'Brujah antitribu': 'H',
  'Caitiff': 'I', 'Daughter of Cacophony': 'J',
  'Ministry': 'r', 'Follower of Set': 'r', 'Followers of Set': 'r',
  'Gangrel': 'p', 'Gangrel antitribu': 'M',
  'Gargoyle': 'N', 'Giovanni': 'O', 'Guruhi': 'P',
  'Harbinger of Skulls': 'Q', 'Ishtarri': 'R',
  'Kiasyd': 'S', 'Lasombra': 'w',
  'Malkavian': 'q', 'Malkavian antitribu': 'V',
  'Nagaraja': 'W', 'Nosferatu': 's', 'Nosferatu antitribu': 'Y',
  'Osebo': 'Z', 'Pander': 'a', 'Ravnos': 'b',
  'Salubri': 'c', 'Salubri antitribu': 'd', 'Samedi': 'e',
  'Toreador': 't', 'Toreador antitribu': 'g',
  'Tremere': 'u', 'Tremere antitribu': 'i',
  'True Brujah': 'j', 'Tzimisce': 'k',
  'Ventrue': 'v', 'Ventrue antitribu': 'm',
  'Hecata': 'O', 'The Ministry': 'r',
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

/**
 * Get the font character for a clan.
 */
export function clanIcon(clan: string): string | undefined {
  return CLAN_ICONS[clan];
}
