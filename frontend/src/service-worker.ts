/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />
/// <reference types="@sveltejs/kit" />

import { build, files, version } from '$service-worker';
import routes from '../../deploy/routes.json';
import { IMAGE_CACHE, isCardImage, isPromoImage } from '$lib/image-cache';

const sw = globalThis.self as unknown as ServiceWorkerGlobalScope;
const CACHE = `cache-${version}`;
const ASSETS = [...build, ...files];
// adapter-static writes the fallback after the build, so `build` never lists it;
// vite dev serves no such file, and one 404 fails the whole install.
const SHELL = '/200.html';
const BACKEND_PREFIXES = [...routes.backend_paths, routes.sse_path];
const BACKEND_PATTERNS = routes.backend_patterns.map((p) => new RegExp(p));

sw.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then(async (cache) => {
      await cache.addAll(ASSETS);
      if (!import.meta.env.DEV) await cache.add(new Request(SHELL, { cache: 'reload' }));
    })
  );
});

sw.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE && k !== IMAGE_CACHE).map((k) => caches.delete(k)))
    )
  );
});

sw.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  if (url.origin === location.origin) {
    if (isPromoImage(url)) {
      event.respondWith(cacheFirst(event.request));
      return;
    }
    if (ASSETS.includes(url.pathname)) {
      event.respondWith(fromPrecache(event.request, url));
      return;
    }
    if (event.request.mode === 'navigate' && !isBackend(url.pathname)) {
      event.respondWith(shell(event.request));
    }
    return;
  }

  if (isCardImage(url)) event.respondWith(networkFirst(event.request));
});

function isBackend(pathname: string): boolean {
  return (
    BACKEND_PREFIXES.some((p) => pathname.startsWith(p)) ||
    BACKEND_PATTERNS.some((re) => re.test(pathname))
  );
}

async function cacheFirst(request: Request): Promise<Response> {
  const cache = await caches.open(IMAGE_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}

async function fromPrecache(request: Request, url: URL): Promise<Response> {
  const cached = await (await caches.open(CACHE)).match(url.pathname);
  return cached ?? fetch(request);
}

async function shell(request: Request): Promise<Response> {
  const cached = await (await caches.open(CACHE)).match(SHELL);
  if (cached) return cached;
  try {
    return await fetch(request);
  } catch {
    return new Response('Offline', { status: 503 });
  }
}

async function networkFirst(request: Request): Promise<Response> {
  const cache = await caches.open(IMAGE_CACHE);
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
