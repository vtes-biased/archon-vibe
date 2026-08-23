import type { VtesCard } from '$lib/types';
import { getDB } from './db';
import { callEngine, initEngine } from './engine-instance';
import { normalizeSearch, searchTokens, matchesAllTerms } from './utils';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const CARDS_ETAG_KEY = 'cards_etag';

let cardsMap: Map<number, VtesCard> | null = null;
/** Word-prefix token cache, keyed by card id — see searchCards. */
let cardTokens: Map<number, string[]> | null = null;
let currentEtag: string | null = null;
let engineCardsPromise: Promise<void> | null = null;
let engineCardsFor: Map<number, VtesCard> | null = null;

export async function getCards(): Promise<Map<number, VtesCard>> {
  if (cardsMap && cardsMap.size > 0) return cardsMap;

  const db = await getDB();
  const stored = await db.getAll('cards');
  if (stored.length > 0) {
    cardsMap = new Map(stored.map(c => [c.id, c]));
    cardTokens = null;
    currentEtag = (await db.get('metadata', CARDS_ETAG_KEY)) ?? null;
    refreshCardsFromAPI().catch(() => {});
    return cardsMap;
  }

  await refreshCardsFromAPI();
  if (!cardsMap || cardsMap.size === 0) {
    throw new Error('Failed to load card database');
  }
  return cardsMap;
}

/** Memoized on a promise, not a flag: the deck surfaces fire their validations concurrently. */
export async function loadEngineCards(): Promise<void> {
  const cards = await getCards();
  if (engineCardsPromise && engineCardsFor === cards) return engineCardsPromise;
  engineCardsFor = cards;
  engineCardsPromise = (async () => {
    const engine = await initEngine();
    const obj: Record<string, VtesCard> = {};
    for (const [id, card] of cards) {
      obj[id.toString()] = card;
    }
    callEngine(() => engine.loadCards(JSON.stringify(obj)));
  })().catch(e => {
    engineCardsFor = null;
    engineCardsPromise = null;
    throw e;
  });
  return engineCardsPromise;
}


async function refreshCardsFromAPI(): Promise<void> {
  try {
    const headers: Record<string, string> = {};
    // Only conditional when there is something to keep: a body that fails mid-download leaves
    // currentEtag set with no cards, and a 304 would then wedge getCards() into throwing for
    // the rest of the session.
    if (currentEtag && cardsMap?.size) {
      headers['If-None-Match'] = currentEtag;
    }

    const resp = await fetch(`${API_URL}/api/cards`, { headers });

    if (resp.status === 304) return; // Not modified
    if (!resp.ok) return;

    const etag = resp.headers.get('etag')?.replace(/"/g, '') ?? null;
    // The catalog is cacheable for an hour, so a cold page gets a 200 from the browser's
    // own cache and never revalidates. Compare versions rather than trust the status: a
    // fresh map would re-hand an identical catalog to the engine, growing its memory again.
    if (etag && etag === currentEtag && cardsMap?.size) return;
    currentEtag = etag;

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
    if (currentEtag) await db.put('metadata', currentEtag, CARDS_ETAG_KEY);
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
