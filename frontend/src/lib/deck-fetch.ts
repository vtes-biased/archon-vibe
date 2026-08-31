// URL fetching routes through the backend `/fetch-deck` proxy — only the backend (via krcg) can map
// provider-native card ids to VEKN ids (notably Amaranth's), so every url/QR import goes server-side and needs a connection. Text parsing uses the WASM engine locally, offline-capable.

import { ApiError, apiRequest } from './api';
import { callEngine, initEngine } from './engine-instance';
import * as m from './paraglide/messages.js';

export interface ParsedDeck {
  name: string;
  author: string;
  comments: string;
  cards: Record<string, number>;
  warnings?: string[];
}

/** URL import failed. The message is already localized — the server's developer-English detail
 * goes to the console instead. */
export class DeckFetchError extends Error {}

export async function fetchDeckFromUrl(url: string): Promise<ParsedDeck> {
  try {
    return await apiRequest<ParsedDeck>(
      `/api/tournaments/fetch-deck?url=${encodeURIComponent(url)}`,
      {},
      { suppressErrorToast: true },
    );
  } catch (e) {
    // Status 0 (offline) and a transport failure already localize through `toUserMessage`.
    if (!(e instanceof ApiError) || e.status === 0) throw e;
    console.warn('[deck-fetch]', e.status, e.detail);
    // A 401 survived authorizedFetch's refresh-and-retry, so the refresh token is dead too.
    if (e.status === 401) throw new DeckFetchError(m.auth_error_session_expired());
    if (e.code === 'deck_fetch.provider_unavailable') {
      throw new DeckFetchError(m.deck_url_import_provider_down({ provider: e.params?.provider ?? '' }));
    }
    if (e.code === 'deck_fetch.bad_link') throw new DeckFetchError(m.deck_url_import_failed());
    throw new DeckFetchError(m.err_internal());
  }
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
