import { dev } from '$app/environment';
import { getMetadataByPrefix } from '$lib/db';

let updateAvailable = $state(false);
let waitingWorker: ServiceWorker | null = null;

// Guards the auto-apply path against a reload loop: if the new worker somehow never
// becomes the controller, we'd otherwise reload on every boot forever.
const AUTO_APPLIED_KEY = 'sw_auto_applied';

// How long after init a newly-installed worker counts as "arrived at boot" — generous enough for slow-
// phone precaching; past it, the hourly poll is mid-session and must not reload the page under the user.
const BOOT_WINDOW_MS = 120_000;
let initAt = 0;

export function getUpdateAvailable(): boolean {
  return updateAvailable;
}

export function applyUpdate(): void {
  if (waitingWorker) {
    waitingWorker.postMessage({ type: 'SKIP_WAITING' });
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      window.location.reload();
    });
  }
}

/** Applies a pending update at boot, not waiting for the banner click: a stale client can't tell a new
 * snapshot format from a broken server, and would retry forever with an empty IndexedDB. Skipped while offline-locked — never reload out from under an organizer mid-event. */
async function maybeAutoApply(registration: ServiceWorkerRegistration): Promise<void> {
  if (!registration.waiting) return;
  if (sessionStorage.getItem(AUTO_APPLIED_KEY)) return;
  if (Date.now() - initAt > BOOT_WINDOW_MS) return;
  // Reads from IndexedDB, not the offline store's in-memory Set: initOfflineState() isn't ordered
  // before initServiceWorker(), so that Set may still be empty here.
  if ((await getMetadataByPrefix('offline_tournament:')).size > 0) return;
  sessionStorage.setItem(AUTO_APPLIED_KEY, '1');
  waitingWorker = registration.waiting;
  applyUpdate();
}

export function initServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return;
  initAt = Date.now();

  navigator.serviceWorker
    .register('/service-worker.js', { type: dev ? 'module' : 'classic' })
    .then((registration) => {
      if (registration.waiting) {
        waitingWorker = registration.waiting;
        updateAvailable = true;
        void maybeAutoApply(registration);
      }

      registration.addEventListener('updatefound', () => {
        const installing = registration.installing;
        if (!installing) return;

        installing.addEventListener('statechange', () => {
          if (installing.state === 'installed' && navigator.serviceWorker.controller) {
            waitingWorker = installing;
            updateAvailable = true;
            // First post-deploy visit lands here, not in the `waiting` branch above.
            void maybeAutoApply(registration);
          }
        });
      });

      setInterval(() => {
        registration.update();
      }, 60 * 60 * 1000);
    })
    .catch((err) => {
      console.error('Service worker registration failed:', err);
    });
}
