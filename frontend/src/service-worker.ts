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

  // Skip API calls and SSE stream — these are mutations/live connections
  if (url.pathname.startsWith('/api') || url.pathname === '/stream') return;

  event.respondWith(respond(event.request, url));
});

async function respond(request: Request, url: URL): Promise<Response> {
  const cache = await caches.open(CACHE);

  // Precached assets: serve from cache (cache-first)
  if (ASSETS.includes(url.pathname)) {
    const cached = await cache.match(url.pathname);
    if (cached) return cached;
  }

  // Navigation requests: serve SPA fallback (200.html) from cache
  if (request.mode === 'navigate') {
    const fallback = await cache.match('/200.html');
    if (fallback) return fallback;
  }

  // Everything else: network-first, cache fallback
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

// Listen for skip-waiting message from the app
sw.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') {
    sw.skipWaiting();
  }
});

// --- Web Push (#314) ---------------------------------------------------------
// Backend payload: { title, body, url, tag }. iOS revokes permission if a push
// doesn't show a notification, so this ALWAYS calls showNotification.
sw.addEventListener('push', (event) => {
  let data: { title?: string; body?: string; url?: string; tag?: string } = {};
  try {
    data = event.data?.json() ?? {};
  } catch {
    data = { body: event.data?.text() ?? '' };
  }
  event.waitUntil(
    sw.registration.showNotification(data.title || 'Archon', {
      body: data.body || '',
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      tag: data.tag, // collapse repeats (e.g. same round re-started)
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

// Browser rotated the subscription. Re-subscribe locally with the same server key so
// pushManager.getSubscription() is valid again; the app re-POSTs it on next open (lazy
// reconcile) and the stale endpoint is pruned server-side on its next 404/410.
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
