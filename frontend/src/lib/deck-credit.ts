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
    case 'Named':
    case 'Archive':
      return attribution.name;
    default:
      return '';
  }
}
