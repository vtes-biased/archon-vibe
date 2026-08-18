import type { VtesCard } from '$lib/types';
import { getDB } from './db';
import { normalizeSearch, searchTokens, matchesAllTerms } from './utils';
import { initEngine } from './engine-instance';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

let cardsMap: Map<number, VtesCard> | null = null;
/** Word-prefix token cache, keyed by card id — see searchCards. */
let cardTokens: Map<number, string[]> | null = null;
let currentEtag: string | null = null;

export async function getCards(): Promise<Map<number, VtesCard>> {
  if (cardsMap && cardsMap.size > 0) return cardsMap;

  const db = await getDB();
  const stored = await db.getAll('cards');
  if (stored.length > 0) {
    cardsMap = new Map(stored.map(c => [c.id, c]));
    cardTokens = null;
    refreshCardsFromAPI().catch(() => {});
    return cardsMap;
  }

  await refreshCardsFromAPI();
  if (!cardsMap || cardsMap.size === 0) {
    throw new Error('Failed to load card database');
  }
  return cardsMap;
}

export async function getCardsJson(): Promise<string> {
  const cards = await getCards();
  const obj: Record<string, VtesCard> = {};
  for (const [id, card] of cards) {
    obj[id.toString()] = card;
  }
  return JSON.stringify(obj);
}


async function refreshCardsFromAPI(): Promise<void> {
  try {
    const headers: Record<string, string> = {};
    if (currentEtag) {
      headers['If-None-Match'] = currentEtag;
    }

    const resp = await fetch(`${API_URL}/api/cards`, { headers });

    if (resp.status === 304) return; // Not modified
    if (!resp.ok) return;

    const etag = resp.headers.get('etag');
    if (etag) currentEtag = etag.replace(/"/g, '');

    const data: Record<string, VtesCard> = await resp.json();
    const cards = Object.values(data);

    cardsMap = new Map(cards.map(c => [c.id, c]));
    cardTokens = null;

    const db = await getDB();
    const tx = db.transaction('cards', 'readwrite');
    await tx.store.clear();
    for (const card of cards) {
      tx.store.put(card);
    }
    await tx.done;
  } catch (e) {
    console.warn('Failed to refresh cards from API:', e);
  }
}

function tokensFor(card: VtesCard): string[] {
  return [
    ...searchTokens(card.printed_name),
    ...searchTokens(card.unique_name),
    // The engine's parser keys: aliases and ordinals.
    ...card.name_variants.flatMap(searchTokens),
  ];
}

/** Word-prefix on every term, the same rule the member search uses — plain substring matching made
 * short queries mostly noise (e.g. "an" returned 856 cards, 728 of them only mid-word matches). */
export async function searchCards(query: string, limit = 20): Promise<VtesCard[]> {
  if (!query || query.length < 2) return [];
  // `cardTokens` is cached for the session, so it must be folded by the engine, not by
  // normalizeSearch's cold fallback. Swallowed: a permanently failed engine leaves the
  // degraded fold as the only fold there is, and search must still work.
  await initEngine().catch(() => {});
  const cards = await getCards();
  const terms = searchTokens(query);
  const lead = terms[0];
  if (!lead) return [];
  if (!cardTokens) cardTokens = new Map([...cards].map(([id, c]) => [id, tokensFor(c)]));

  const results: VtesCard[] = [];
  for (const card of cards.values()) {
    const tokens = cardTokens.get(card.id) ?? tokensFor(card);
    if (matchesAllTerms(tokens, terms)) results.push(card);
  }

  // Cards whose name opens with the query rank above ones merely containing a matching word. Keyed
  // up front: normalizing inside the comparator would redo the work O(n log n) times.
  return results
    .map((c) => ({ c, lead: normalizeSearch(c.unique_name).startsWith(lead) ? 0 : 1 }))
    .sort((a, b) => a.lead - b.lead || a.c.unique_name.localeCompare(b.c.unique_name))
    .slice(0, limit)
    .map((r) => r.c);
}
