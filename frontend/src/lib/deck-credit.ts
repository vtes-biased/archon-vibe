import { getUserByVekn } from '$lib/db';
import type { DeckAttribution } from '$lib/types';

/** The designer's name to show beside a decklist, or '' when the credit names
 * nobody. A member's name is resolved now rather than stored, so a rename
 * follows; the two free-text kinds carry their own and never reach `/v1`. */
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
