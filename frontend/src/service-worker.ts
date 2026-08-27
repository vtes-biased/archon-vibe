/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />
/// <reference types="@sveltejs/kit" />

import { build, files, version } from '$service-worker';

const sw = globalThis.self as unknown as ServiceWorkerGlobalScope;
const CACHE = `cache-${version}`;
const ASSETS = [...build, ...files];

sw.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS))
  );
});

sw.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
});

sw.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // Only handle http(s) requests — chrome-extension:// etc. can't be cached
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return;

  if (url.origin === location.origin) {
    // Promo images: unauthenticated by design, versioned/immutable URLs —
    // cache-first so they display during offline tournaments. Populated by
    // the catalog-sync prefetch (sync.ts).
    if (url.pathname.startsWith('/api/promos/') && url.pathname.endsWith('/image')) {
      event.respondWith(cacheFirst(event.request));
      return;
    }
    // Allow-list: only precached assets and SPA navigations use Cache Storage;
    // every other same-origin GET passes through untouched, so authenticated
    // responses never get cached.
    if (ASSETS.includes(url.pathname) || event.request.mode === 'navigate') {
      event.respondWith(respondFromCache(event.request, url));
    }
    return;
  }

  // Cross-origin (card images): network-first, cache fallback.
  event.respondWith(networkFirst(event.request));
});

// Versioned promo-image URLs are immutable content: a cache hit is always
// correct, and a re-upload changes the URL (new ?v=) so staleness can't occur.
async function cacheFirst(request: Request): Promise<Response> {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}

async function respondFromCache(request: Request, url: URL): Promise<Response> {
  const cache = await caches.open(CACHE);

  if (ASSETS.includes(url.pathname)) {
    const cached = await cache.match(url.pathname);
    if (cached) return cached;
  }

  if (request.mode === 'navigate') {
    const fallback = await cache.match('/200.html');
    if (fallback) return fallback;
  }

  return networkFirst(request);
}

async function networkFirst(request: Request): Promise<Response> {
  const cache = await caches.open(CACHE);
  try {
    const response = await fetch(request);
    if (response.status === 200) {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    return new Response('Offline', { status: 503 });
  }
}

sw.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    sw.skipWaiting();
  }
});

const beta = self.location.hostname === 'archon.krcg.org';

// Backend payload: { title, body, url, tag }. iOS revokes permission if a push
// doesn't show a notification, so this always calls showNotification.
sw.addEventListener('push', (event) => {
  let data: { title?: string; body?: string; url?: string; tag?: string; renotify?: boolean } = {};
  try {
    data = event.data?.json() ?? {};
  } catch {
    data = { body: event.data?.text() ?? '' };
  }
  event.waitUntil(
    sw.registration.showNotification(data.title || (beta ? 'Archon Beta' : 'Archon'), {
      body: data.body || '',
      icon: beta ? '/icon-192-beta.png' : '/icon-192.png',
      badge: beta ? '/icon-192-beta.png' : '/icon-192.png',
      tag: data.tag, // collapse repeats (e.g. same round re-started)
      // re-alert (sound/vibrate) on a collapsed tag — judge calls set this
      renotify: data.renotify === true,
      data: { url: data.url || '/' },
    })
  );
});

// Tap → focus an open tab (navigating it to the deep link), else open one. The deep
// link resolves offline (the app reads it from IndexedDB), so no network is required.
sw.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data?.url as string) || '/';
  event.waitUntil(
    sw.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((clients) => {
        for (const client of clients) {
          if ('focus' in client) {
            client.focus();
            if ('navigate' in client) client.navigate(url).catch(() => {});
            return undefined;
          }
        }
        return sw.clients.openWindow(url);
      })
  );
});

// Browser rotated the subscription: re-subscribe locally with the same server
// key so pushManager.getSubscription() is valid again; the app re-POSTs it on
// next open (lazy reconcile).
sw.addEventListener('pushsubscriptionchange', (event) => {
  const e = event as Event & {
    oldSubscription?: PushSubscription;
    newSubscription?: PushSubscription;
  };
  if (e.newSubscription) return; // browser already provided a replacement
  const appServerKey = e.oldSubscription?.options?.applicationServerKey;
  if (!appServerKey) return; // app will reconcile from scratch on next open
  event.waitUntil(
    sw.registration.pushManager
      .subscribe({ userVisibleOnly: true, applicationServerKey: appServerKey })
      .then(() => undefined)
      .catch(() => undefined)
  );
});
