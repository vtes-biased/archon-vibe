import { getUserByVekn } from '$lib/db';
import type { DeckAttribution } from '$lib/types';

/** The designer's name to show beside a decklist, or '' when the credit names
 * nobody. */
export async function creditName(attribution: DeckAttribution): Promise<string> {
  switch (attribution.kind) {
    case 'Member': {
      const user = await getUserByVekn(attribution.vekn_id);
      return user?.name ?? '';
    }
    case 'Archive':
      return attribution.name;
    default:
      return '';
  }
}

/** What the engine's `credit_from_json` accepts from a client. */
export function isSettableCredit(attribution: DeckAttribution): boolean {
  return attribution.kind === 'Owner' || attribution.kind === 'Anonymous'
    || (attribution.kind === 'Member' && !!attribution.vekn_id);
}
