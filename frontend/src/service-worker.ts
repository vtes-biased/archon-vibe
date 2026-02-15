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
