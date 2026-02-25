/**
 * Client-side deck fetching and parsing.
 *
 * URL fetching: calls external deck APIs (VDB, VTESDecks, Amaranth) directly from the browser.
 * Text parsing: uses WASM engine's parse_deck function.
 */

import { initEngine } from './engine';

export interface ParsedDeck {
  name: string;
  author: string;
  comments: string;
  cards: Record<string, number>;
  warnings?: string[];
}

/**
 * Fetch a deck from a supported URL (VDB, VTESDecks, Amaranth).
 */
/**
 * Fetch a deck from a supported URL (VDB, VTESDecks, Amaranth).
 * Tries direct fetch first; falls back to backend proxy if CORS blocks.
 */
export async function fetchDeckFromUrl(url: string): Promise<ParsedDeck> {
  const parsed = new URL(url);

  // VDB inline decks (fragment-based) don't need network — parse locally
  if ((parsed.hostname === 'vdb.im' || parsed.hostname === 'vdb.smeea.casa') && parsed.hash) {
    return fetchVdb(parsed);
  }

  // Try direct fetch, fall back to backend proxy for CORS
  try {
    if (parsed.hostname === 'vdb.im' || parsed.hostname === 'vdb.smeea.casa') {
      return await fetchVdb(parsed);
    } else if (parsed.hostname === 'vtesdecks.com' || parsed.hostname === 'api.vtesdecks.com') {
      return await fetchVtesDecks(parsed);
    } else if (parsed.hostname === 'amaranth.vtes.co.nz') {
      return await fetchAmaranth(parsed);
    }
  } catch {
    // Direct fetch failed (likely CORS) — try backend proxy
    return fetchViaProxy(url);
  }

  // Unknown provider — try proxy
  return fetchViaProxy(url);
}

async function fetchViaProxy(url: string): Promise<ParsedDeck> {
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const { getAccessToken } = await import('./stores/auth.svelte');
  const token = getAccessToken();
  const resp = await fetch(
    `${API_URL}/api/tournaments/fetch-deck?url=${encodeURIComponent(url)}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `Failed to fetch deck (${resp.status})`);
  }
  return resp.json();
}

/**
 * Parse deck text using the WASM engine.
 */
export async function parseDeckText(text: string): Promise<ParsedDeck> {
  const engine = await initEngine();
  const { getCardsJson } = await import('./cards');
  const cardsJson = await getCardsJson();
  if (!cardsJson) throw new Error('Cards data not loaded');

  const resultJson = engine.parseDeck(text, cardsJson);
  const result = JSON.parse(resultJson);
  const warnings: string[] = [];
  if (result.unrecognized_lines?.length) {
    for (const line of result.unrecognized_lines) {
      warnings.push(`Could not identify card: "${line}"`);
    }
  }
  return {
    name: result.name || '',
    author: result.author || '',
    comments: result.comments || '',
    cards: result.cards || {},
    warnings: warnings.length ? warnings : undefined,
  };
}

async function fetchVdb(parsed: URL): Promise<ParsedDeck> {
  // Inline deck in URL fragment: #card_id=count;...
  if (parsed.hash) {
    const fragment = parsed.hash.slice(1);
    const cards: Record<string, number> = {};
    for (const item of fragment.split(';')) {
      if (!item.includes('=')) continue;
      const parts = item.split('=', 2);
      if (!parts[0] || !parts[1]) continue;
      const count = parseInt(parts[1], 10);
      if (count > 0) cards[parts[0]] = count;
    }
    const params = parsed.searchParams;
    return {
      name: params.get('name') || '',
      author: params.get('author') || '',
      comments: params.get('description') || '',
      cards,
    };
  }

  // API fetch
  let deckId = parsed.searchParams.get('id');
  if (!deckId && parsed.pathname.startsWith('/decks/')) {
    deckId = parsed.pathname.slice(7);
  }
  if (!deckId) throw new Error('Cannot extract VDB deck ID from URL');

  const resp = await fetch(`https://vdb.im/api/deck/${deckId}`);
  if (!resp.ok) throw new Error(`VDB API error: ${resp.status}`);
  const data = await resp.json();

  const cards: Record<string, number> = {};
  for (const [cid, count] of Object.entries(data.cards || {})) {
    if ((count as number) > 0) cards[cid] = count as number;
  }
  return {
    name: data.name || '',
    author: data.author || data.owner || '',
    comments: data.description || '',
    cards,
  };
}

async function fetchVtesDecks(parsed: URL): Promise<ParsedDeck> {
  if (!parsed.pathname.startsWith('/deck/')) {
    throw new Error('Unknown VTESDecks URL path');
  }
  const deckId = parsed.pathname.slice(6);

  const resp = await fetch(`https://api.vtesdecks.com/1.0/decks/${deckId}`);
  if (!resp.ok) throw new Error(`VTESDecks API error: ${resp.status}`);
  const data = await resp.json();

  const cards: Record<string, number> = {};
  for (const card of [...(data.crypt || []), ...(data.library || [])]) {
    const count = card.number || 0;
    if (count > 0) cards[String(card.id)] = count;
  }
  return {
    name: data.name || '',
    author: data.author || '',
    comments: data.description || '',
    cards,
  };
}

async function fetchAmaranth(parsed: URL): Promise<ParsedDeck> {
  if (!parsed.hash.startsWith('#deck/')) {
    throw new Error('Unknown Amaranth URL format');
  }
  const deckId = parsed.hash.slice(6);

  const resp = await fetch('https://amaranth.vtes.co.nz/api/deck', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `id=${deckId}`,
  });
  if (!resp.ok) throw new Error(`Amaranth API error: ${resp.status}`);
  const data = await resp.json();

  const result = data.result || {};
  const cards: Record<string, number> = {};
  for (const [cid, count] of Object.entries(result.cards || {})) {
    if ((count as number) > 0) cards[cid] = count as number;
  }
  return {
    name: result.title || '',
    author: result.author || '',
    comments: result.description || '',
    cards,
  };
}
