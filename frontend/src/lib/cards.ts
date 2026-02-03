/**
 * VTES card database: fetch from API, cache in IndexedDB, load into memory.
 */

import type { VtesCard } from '$lib/types';
import { getDB } from './db';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/** In-memory card map: id → card */
let cardsMap: Map<number, VtesCard> | null = null;
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
 * Look up a card by ID.
 */
export async function getCard(id: number): Promise<VtesCard | undefined> {
  const cards = await getCards();
  return cards.get(id);
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

/**
 * Simple card search by name (for the card search component).
 * Returns up to `limit` matches.
 */
export async function searchCards(query: string, limit = 20): Promise<VtesCard[]> {
  if (!query || query.length < 2) return [];
  const cards = await getCards();
  const lower = query.toLowerCase();
  const results: VtesCard[] = [];

  for (const card of cards.values()) {
    if (results.length >= limit) break;
    if (
      card.name.toLowerCase().includes(lower) ||
      card.printed_name.toLowerCase().includes(lower)
    ) {
      results.push(card);
    }
  }

  // Sort: exact prefix matches first, then by name
  results.sort((a, b) => {
    const aStarts = a.name.toLowerCase().startsWith(lower) ? 0 : 1;
    const bStarts = b.name.toLowerCase().startsWith(lower) ? 0 : 1;
    return aStarts - bStarts || a.name.localeCompare(b.name);
  });

  return results;
}
