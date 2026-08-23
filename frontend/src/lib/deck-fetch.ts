// URL fetching routes through the backend `/fetch-deck` proxy — only the backend (via krcg) can map
// provider-native card ids to VEKN ids (notably Amaranth's), so every url/QR import goes server-side and needs a connection. Text parsing uses the WASM engine locally, offline-capable.

import { callEngine, initEngine } from './engine-instance';

export interface ParsedDeck {
  name: string;
  author: string;
  comments: string;
  cards: Record<string, number>;
  warnings?: string[];
}

/** URL import failed (bad link, unsupported provider, provider error). The server detail is developer
 * English — callers show one friendly localized message instead and nudge toward Paste, which always works. */
export class DeckFetchError extends Error {}

export async function fetchDeckFromUrl(url: string): Promise<ParsedDeck> {
  const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
  const { getAccessToken } = await import('./stores/auth.svelte');
  const token = getAccessToken();
  const resp = await fetch(
    `${API_URL}/api/tournaments/fetch-deck?url=${encodeURIComponent(url)}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} },
  );
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    // Keep the real cause findable without surfacing dev copy to the player.
    console.warn('[deck-fetch]', resp.status, data.detail);
    throw new DeckFetchError(data.detail || `Failed to fetch deck (${resp.status})`);
  }
  return resp.json();
}

export async function parseDeckText(text: string): Promise<ParsedDeck> {
  const engine = await initEngine();
  const { loadEngineCards } = await import('./cards');
  await loadEngineCards();

  const resultJson = callEngine(() => engine.parseDeck(text));
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
