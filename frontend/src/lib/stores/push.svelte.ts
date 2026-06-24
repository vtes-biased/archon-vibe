/**
 * Web Push subscription lifecycle (#314).
 *
 * The browser's `pushManager.getSubscription()` is the source of truth for whether this
 * device is subscribed; this store mirrors it reactively for the UI and drives the
 * subscribe/unsubscribe gestures. Subscribing must happen from a user gesture (iOS), and
 * on iOS only works for an installed (standalone) PWA — see `isIOS`/`isStandalone`.
 *
 * Lazy reconcile: after a `pushsubscriptionchange` the service worker re-subscribes
 * locally (it has no auth); `reconcilePush()` (called on app open while logged in)
 * re-POSTs the current subscription so the backend learns the new endpoint, and the
 * stale one is pruned server-side on its next 404/410.
 */
import {
  deletePushSubscription,
  getVapidPublicKey,
  isOnline,
  registerPushSubscription,
} from '$lib/api';

let permission = $state<NotificationPermission>(
  typeof Notification !== 'undefined' ? Notification.permission : 'default'
);
let subscribed = $state(false);
let busy = $state(false);

export function getPushPermission(): NotificationPermission {
  return permission;
}
export function isPushSubscribed(): boolean {
  return subscribed;
}
export function isPushBusy(): boolean {
  return busy;
}

/** True when this browser can do Web Push at all. */
export function pushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}

/** Running as an installed PWA (standalone display) rather than a browser tab. */
export function isStandalone(): boolean {
  if (typeof window === 'undefined') return false;
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    // iOS Safari predates display-mode and exposes navigator.standalone instead
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

/** iOS/iPadOS — where push needs A2HS and there's no beforeinstallprompt. */
export function isIOS(): boolean {
  if (typeof navigator === 'undefined') return false;
  return (
    /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    // iPadOS 13+ reports as desktop Safari; touch points disambiguate it
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  );
}

/**
 * True only for real iOS Safari — the ONLY iOS browser that can install a
 * push-capable PWA. Chrome (CriOS), Firefox (FxiOS), Edge (EdgiOS) and in-app
 * webviews (which lack the "Safari" token) can't Add-to-Home-Screen into a
 * standalone app, so those users must be told to open the page in Safari first.
 */
export function isIOSSafari(): boolean {
  if (!isIOS() || typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent;
  return /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS|OPiOS|GSA|mercury/i.test(ua);
}

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(b64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

async function currentSubscription(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  const reg = await navigator.serviceWorker.ready;
  return reg.pushManager.getSubscription();
}

/** Sync reactive state from the browser. Call on app open / when opening settings. */
export async function refreshPushState(): Promise<void> {
  if (!pushSupported()) return;
  permission = Notification.permission;
  subscribed = !!(await currentSubscription());
}

/**
 * Subscribe this browser (MUST be called from a user gesture). Requests permission,
 * subscribes via pushManager, and registers the subscription with the backend.
 * Returns true on success, false if denied/unsupported/failed.
 */
export async function enablePush(): Promise<boolean> {
  if (!pushSupported() || busy) return false;
  busy = true;
  try {
    permission = await Notification.requestPermission();
    if (permission !== 'granted') return false;
    const key = await getVapidPublicKey();
    const reg = await navigator.serviceWorker.ready;
    const sub =
      (await reg.pushManager.getSubscription()) ??
      (await reg.pushManager.subscribe({
        userVisibleOnly: true,
        // Cast: the Uint8Array IS a BufferSource, but TS's lib types widen .buffer to
        // ArrayBufferLike (incl. SharedArrayBuffer) which the param type rejects.
        applicationServerKey: urlBase64ToUint8Array(key) as BufferSource,
      }));
    await registerPushSubscription(sub.toJSON());
    subscribed = true;
    return true;
  } catch (e) {
    console.error('enablePush failed', e);
    return false;
  } finally {
    busy = false;
  }
}

/** Unsubscribe this browser (toggle off): drop it server-side then locally. */
export async function disablePush(): Promise<void> {
  if (!pushSupported() || busy) return;
  busy = true;
  try {
    const sub = await currentSubscription();
    if (sub) {
      // Best-effort server delete; if it fails the row is pruned on its next 404/410.
      try {
        await deletePushSubscription(sub.endpoint);
      } catch {
        /* offline / transient — server prunes lazily */
      }
      await sub.unsubscribe();
    }
    subscribed = false;
  } finally {
    busy = false;
  }
}

/**
 * Lazy reconcile after a key rotation or SW re-subscribe. Re-POSTs the current
 * subscription so the backend has the live endpoint. No-op when unsupported, offline,
 * permission not granted, or not subscribed. Call on app open while authenticated.
 */
export async function reconcilePush(): Promise<void> {
  if (!pushSupported() || !isOnline()) return;
  permission = Notification.permission;
  if (permission !== 'granted') {
    subscribed = false;
    return;
  }
  const sub = await currentSubscription();
  subscribed = !!sub;
  if (!sub) return;
  try {
    await registerPushSubscription(sub.toJSON());
  } catch {
    /* not logged in yet / offline — retried on next app open */
  }
}
