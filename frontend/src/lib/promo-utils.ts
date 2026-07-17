// Display helpers for the promo catalog (gallery, inventory, modals).
import type { Promo, PromoKind, TournamentRank } from '$lib/types';
import * as m from '$lib/paraglide/messages.js';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

/** Full URL for a promo image (image_path is a versioned server path). */
export function promoImageUrl(promo: Promo): string | null {
  return promo.image_path ? `${API_BASE}${promo.image_path}` : null;
}

/** Short pill label for a rank-gating badge ("" never renders a badge). */
export function rankBadgeLabel(rank: TournamentRank): string {
  if (rank === 'National Championship') return m.promo_rank_national();
  if (rank === 'Continental Championship') return m.promo_rank_continental();
  return rank;
}

export function promoKindLabel(kind: PromoKind): string {
  switch (kind) {
    case 'card':
      return m.promo_kind_card();
    case 'pack':
      return m.promo_kind_pack();
    default:
      return m.promo_kind_other();
  }
}

export interface HoldingRow {
  uid: string;
  assigned: number;
  remaining: number;
}

/** One display row per holder. Pure supply sources (negative remaining with
 * nothing credited in — IC/BCP roots) are supply bookkeeping, not holders. */
export function holdingRows(promo: Promo): HoldingRow[] {
  return Object.entries(promo.holdings ?? {})
    .filter(([, h]) => !(h.remaining < 0 && h.assigned === 0))
    .map(([uid, h]) => ({ uid, assigned: h.assigned, remaining: h.remaining }));
}
