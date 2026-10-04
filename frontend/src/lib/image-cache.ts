// Imported by the service worker: keep this module free of imports.
export const IMAGE_CACHE = 'images';
export const CARD_IMAGE_PREFIX = 'https://static.krcg.org/card/';

export function isPromoImage(url: URL): boolean {
  return url.pathname.startsWith('/api/promos/') && url.pathname.endsWith('/image');
}

export function isCardImage(url: URL): boolean {
  return url.href.startsWith(CARD_IMAGE_PREFIX);
}

/** Drops the entries `owns` claims whose absolute URL is not in `keep`. */
export async function pruneImages(owns: (url: URL) => boolean, keep: Set<string>): Promise<void> {
  const cache = await caches.open(IMAGE_CACHE);
  for (const request of await cache.keys()) {
    if (owns(new URL(request.url)) && !keep.has(request.url)) await cache.delete(request);
  }
}
