import type { VtesCard } from '$lib/types';
import cardsUrl from '../../../engine/data/cards.json?url';
import { getDB } from './db';
import { callEngine, initEngine } from './engine-instance';
import { normalizeSearch, searchTokens, matchesAllTerms } from './utils';
import { isCardImage, pruneImages } from './image-cache';

const CARDS_URL_KEY = 'cards_url';

let cardsLoad: Promise<Map<number, VtesCard>> | null = null;
/** Word-prefix token cache, keyed by card id — see searchCards. */
let cardTokens: Map<number, string[]> | null = null;
let engineCardsPromise: Promise<void> | null = null;
let engineCardsFor: Map<number, VtesCard> | null = null;

export function getCards(): Promise<Map<number, VtesCard>> {
  cardsLoad ??= readCards().catch(e => {
    cardsLoad = null;
    throw e;
  });
  return cardsLoad;
}

async function readCards(): Promise<Map<number, VtesCard>> {
  const db = await getDB();
  const stored = await db.getAll('cards');
  if (stored.length === 0) return fetchCards();

  const current = !import.meta.env.DEV && (await db.get('metadata', CARDS_URL_KEY)) === cardsUrl;
  if (!current) fetchCards().catch(e => console.warn('Failed to refresh cards:', e));
  return new Map(stored.map(c => [c.id, c]));
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

async function fetchCards(): Promise<Map<number, VtesCard>> {
  const resp = await fetch(cardsUrl);
  if (!resp.ok) throw new Error(`Failed to load card database: ${resp.status}`);
  const cards = Object.values((await resp.json()) as Record<string, VtesCard>);

  const db = await getDB();
  const tx = db.transaction(['cards', 'metadata'], 'readwrite');
  const store = tx.objectStore('cards');
  await store.clear();
  for (const card of cards) {
    store.put(card);
  }
  tx.objectStore('metadata').put(cardsUrl, CARDS_URL_KEY);
  await tx.done;

  const map = new Map(cards.map(c => [c.id, c]));
  cardsLoad = Promise.resolve(map);
  cardTokens = null;
  pruneImages(isCardImage, new Set(cards.map(c => c.img))).catch(() => {});
  return map;
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
