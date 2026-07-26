/**
 * Service worker registration and update management.
 */
import { dev } from '$app/environment';
import { getMetadataByPrefix } from '$lib/db';

let updateAvailable = $state(false);
let waitingWorker: ServiceWorker | null = null;

// Guards the auto-apply path against a reload loop: if the new worker somehow never
// becomes the controller, we'd otherwise reload on every boot forever.
const AUTO_APPLIED_KEY = 'sw_auto_applied';

// How long after init a newly-installed worker still counts as "arrived at boot".
// On a first post-deploy visit the new worker reaches `waiting` via updatefound
// partway through page load, not before it — so keying auto-apply on `registration
// .waiting` alone would miss exactly the visit it exists for. Generous enough to
// cover precaching the asset set on a slow phone; past it, the hourly update poll
// is mid-session and must not reload the page under the user.
const BOOT_WINDOW_MS = 120_000;
let initAt = 0;

export function getUpdateAvailable(): boolean {
  return updateAvailable;
}

export function applyUpdate(): void {
  if (waitingWorker) {
    waitingWorker.postMessage({ type: 'SKIP_WAITING' });
    // Reload once the new SW takes over
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      window.location.reload();
    });
  }
}

/**
 * Apply a pending worker without waiting for the user to click the update banner,
 * when it became available around boot. The bundle in that worker may be the only one
 * that can read the current server's snapshot format, and a client running stale JS
 * can't tell a format it doesn't understand from a broken server — it just retries
 * forever with an empty IndexedDB after a resync, with no user-visible signal. Taking
 * the update at boot, when the user has nothing in flight, closes that window.
 *
 * Deliberately NOT applied while a tournament is locked offline: the same invariant
 * the banner already respects (+layout hides it when `hasOfflineLocked`). Never reload
 * out from under an organizer mid-event; they take the update when they go online.
 * Read from IndexedDB rather than the offline store's in-memory Set — nothing orders
 * initOfflineState() before initServiceWorker(), so that Set may still be empty here.
 */
async function maybeAutoApply(registration: ServiceWorkerRegistration): Promise<void> {
  if (!registration.waiting) return;
  if (sessionStorage.getItem(AUTO_APPLIED_KEY)) return;
  if (Date.now() - initAt > BOOT_WINDOW_MS) return;
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
      // Detect waiting worker from previous visit
      if (registration.waiting) {
        waitingWorker = registration.waiting;
        updateAvailable = true;
        void maybeAutoApply(registration);
      }

      // Detect new updates
      registration.addEventListener('updatefound', () => {
        const installing = registration.installing;
        if (!installing) return;

        installing.addEventListener('statechange', () => {
          if (installing.state === 'installed' && navigator.serviceWorker.controller) {
            // New SW installed while old one is still active = update available
            waitingWorker = installing;
            updateAvailable = true;
            // First post-deploy visit lands here, not in the `waiting` branch above.
            void maybeAutoApply(registration);
          }
        });
      });

      // Check for updates periodically (every hour)
      setInterval(() => {
        registration.update();
      }, 60 * 60 * 1000);
    })
    .catch((err) => {
      console.error('Service worker registration failed:', err);
    });
}
