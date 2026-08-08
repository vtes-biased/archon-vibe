/**
 * VTES card database: fetch from API, cache in IndexedDB, load into memory.
 */

import type { VtesCard } from '$lib/types';
import { getDB } from './db';
import { normalizeSearch, searchTokens, matchesAllTerms } from './utils';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/** In-memory card map: id → card */
let cardsMap: Map<number, VtesCard> | null = null;
/** Word-prefix token cache, keyed by card id — see searchCards. */
let cardTokens: Map<number, string[]> | null = null;
/** ETag for cache validation */
let currentEtag: string | null = null;

/**
 * Get the in-memory cards map, loading from IDB or API as needed.
 */
export async function getCards(): Promise<Map<number, VtesCard>> {
  if (cardsMap && cardsMap.size > 0) return cardsMap;

  // Try loading from IndexedDB first
  const db = await getDB();
  const stored = await db.getAll('cards');
  if (stored.length > 0) {
    cardsMap = new Map(stored.map(c => [c.id, c]));
    cardTokens = null;
    // Trigger background refresh
    refreshCardsFromAPI().catch(() => {});
    return cardsMap;
  }

  // No cached data — fetch from API
  await refreshCardsFromAPI();
  if (!cardsMap || cardsMap.size === 0) {
    throw new Error('Failed to load card database');
  }
  return cardsMap;
}

/**
 * Get the cards as a JSON string (for passing to WASM engine).
 */
export async function getCardsJson(): Promise<string> {
  const cards = await getCards();
  const obj: Record<string, VtesCard> = {};
  for (const [id, card] of cards) {
    obj[id.toString()] = card;
  }
  return JSON.stringify(obj);
}


/**
 * Fetch fresh cards from the API, using ETag for caching.
 */
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

    // Update in-memory map
    cardsMap = new Map(cards.map(c => [c.id, c]));
    cardTokens = null;

    // Persist to IndexedDB
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

/**
 * Simple card search by name (for the card search component).
 * Returns up to `limit` matches.
 *
 * Word-prefix on every term, the same rule the member search uses. This was a
 * plain substring match, which made short queries mostly noise — "an" returned
 * 856 cards of which 728 matched only mid-word (Abandoning the Flesh, Agate
 * Talisman) and buried the ones actually named "An…". Multi-word queries still
 * work because each term is matched independently: "govern the unaligned"
 * matches all three.
 */
export async function searchCards(query: string, limit = 20): Promise<VtesCard[]> {
  if (!query || query.length < 2) return [];
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

  // Cards whose name opens with the query rank above ones merely containing a
  // matching word. Keyed up front: normalizing inside the comparator would redo
  // the work O(n log n) times.
  return results
    .map((c) => ({ c, lead: normalizeSearch(c.unique_name).startsWith(lead) ? 0 : 1 }))
    .sort((a, b) => a.lead - b.lead || a.c.unique_name.localeCompare(b.c.unique_name))
    .slice(0, limit)
    .map((r) => r.c);
}
